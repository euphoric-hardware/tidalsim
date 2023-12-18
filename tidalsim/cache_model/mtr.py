from dataclasses import dataclass
from typing import Dict, Iterator, Tuple, Optional, List
from math import log2
from pathlib import Path
from tidalsim.util.pickle import dump, load
import logging
import re

commit_log_instruction_pattern = re.compile(r"core[^\S\r\n]+(?P<core_num>[0-9]+):[^\S\r\n]+(?P<addr>0x[0-9a-f]+)[^\S\r\n]+\((?P<instr_bits>0x[0-9a-f]+)\)[^\S\r\n]+(?P<instr>[A-Za-z.]+)[^\S\r\n]*(?P<reg_info>.*)")

store_instrs = (
  "sb", "sh", "sw", "sd", "fsw", "fsd" 
)

load_instrs = (
  "lb", "lbu",
  "lh", "lhu",
  "lw", "lwu",
  "ld",
  "flw", "fld"
)

@dataclass 
class MemoryTimestampRecordEntry:
  last_read_timestamp: int # this becomes a vector in the future for multiproc
  last_write_timstamp: int
  last_writer_id: int
  last_updated_value: str

@dataclass
class MemoryTimestampRecord:
  entries: Dict[int, MemoryTimestampRecordEntry]

@dataclass
class MemoryTimestampRecordUpdate:
  address: int
  timestamp: int
  data: str
  is_store: bool
  writer_id: Optional[int]

block_size_bytes: int = 8
mtr: MemoryTimestampRecord = None
commit_log_filename: str = None
checkpoints: List[int] = None

# Parses spile commit log to return address, instruction number (timestamp), value, is_store, writer_id? 
def parse_spike_commit_log(log_lines: Iterator[str]) -> Iterator[MemoryTimestampRecordUpdate]:
    
  mem_count = 0
  instr_count = 0
  
  prev_line = log_lines.readline()

  # Checkpoint at instr 0 is just empty
  if checkpoints[0] == 0:
    checkpoint_mtr(checkpoints.pop(0))

  # Correct count => avoid off-by-one
  match = commit_log_instruction_pattern.match(curr_line)
  if match:
    instr_count += 1

  while (curr_line := log_lines.readline()):

    # mem transaction commit 
    if curr_line.__contains__("mem"):
      mem_count += 1

      # TODO: SIMPLIFY

      prev_line_items = prev_line.split()
      curr_line_items = curr_line.split()

      logging.debug(prev_line_items)
      logging.debug(curr_line_items)
      
      if prev_line_items[4] in store_instrs:
        addr: int = int(curr_line_items[-2], 16)
        data: str = curr_line_items[-1][2:] # ignore 0x for str
        core_num: int = int(curr_line_items[1][:-1])
        logging.info(f"[{mem_count}] store : addr = {addr} : data = {data}")
        yield MemoryTimestampRecordUpdate(addr, instr_count, data, True, core_num)
      elif prev_line_items[4] in load_instrs:
        addr: int = int(curr_line_items[-3], 16)
        data: str = curr_line_items[-1][2:] # ignore 0x for str
        logging.info(f"[{mem_count}] load : addr = {addr} : data = {data}")
        yield MemoryTimestampRecordUpdate(addr, instr_count, data, False)
      else:
        logging.warning(f"[{mem_count}] misc: {prev_line} : {curr_line}")

  
    if len(checkpoints) and checkpoints[0] == instr_count:
      checkpoint_mtr(checkpoints.pop(0))
    
    match = commit_log_instruction_pattern.match(curr_line)
    if match:
      instr_count += 1
    
    prev_line = curr_line
  
  # If last instr is ckpt, we exit the loop without checkpointing
  if len(checkpoints) and checkpoints[0] == instr_count:
    checkpoint_mtr(checkpoints.pop(0))
      
# Update MTR by adding a new entry or editing an existing one
def update_mtr(update: MemoryTimestampRecordUpdate):

  block_addr: int = (update.address >> log2(block_size_bytes)) << log2(block_size_bytes)
  byte_offset: int = update.address % block_size_bytes
  nibble_offset = byte_offset * 2
  nibble_len = len(update.data)
  block_size_nibbles = block_size_bytes * 2
  start_index = block_size_nibbles - nibble_offset - nibble_len 

  if block_addr in mtr.entries:
    mtr_entry = mtr.entries[block_addr]
    if update.is_store:
      mtr_entry.last_write_timstamp = update.timestamp
      mtr_entry.last_writer_id = update.writer_id
      mtr_entry.last_updated_value[start_index:start_index+nibble_len] = update.data 
    else:
      mtr_entry.last_read_timestamp = update.timestamp
      if mtr_entry.last_updated_value[start_index:start_index+nibble_len] != update.data:
        logging.warning(f"load doesn't match mtr = external writer = {mtr_entry} : {update}")

  else:
    # create new entry
    if update.is_store:
      new_value = "0" * block_size_nibbles
      new_value[start_index:start_index+nibble_len] = update.data
      new_mtr_entry = MemoryTimestampRecordEntry(-1, update.timestamp, update.writer_id, new_value)
      mtr.entries[block_addr] = new_mtr_entry
    else:
      if int(update.data) != 0:
        logging.warning(f"non-zero load before store: {update}")
      new_value = "0" * block_size_nibbles
      new_value[start_index:start_index+nibble_len] = update.data
      new_mtr_entry = MemoryTimestampRecordEntry(update.timestamp, -1, -1, new_value)
      mtr.entries[block_addr] = new_mtr_entry
      
def checkpoint_mtr(checkpoint: int):
  dump(mtr, Path(commit_log_filename+f".{checkpoint}.mtr"))

def reconstruct_mtr_cache(checkpoint_filename: str, num_ways: int, num_sets: int):
  # loop over entire mtr, for each set, select top ways
  mtr: MemoryTimestampRecord = load(Path(checkpoint_filename))
  index_mtr_entry = {i : list() for i in range(num_sets)}
  map(lambda block_addr: index_mtr_entry[(block_addr >> log2(block_size_bytes)) % num_sets].append(block_addr), mtr.entries)
  
  for i in index_mtr_entry:
    blocks = index_mtr_entry[i].sort(key=lambda block_addr: max(mtr.entries[block_addr].last_read_timestamp, mtr.entries[block_addr].last_write_timstamp), reverse=True)[:num_ways]
    # TODO: handle returning each block

  pass

def set_global_parameters(block_size_bits: int, ckpts: List[int], commit_log_file: str) -> None:
  global block_size_bytes, mtr, commit_log_filename, checkpoints
  block_size_bytes = block_size_bits//8
  mtr.entries = dict()
  checkpoints = ckpts
  commit_log_filename = commit_log_file


def main():
  logging.basicConfig(format='%(levelname)s - %(filename)s:%(lineno)d - %(message)s', filename='testlog', level=logging.INFO)
  
  set_global_parameters(block_size_bits=64, ckpts=[0, 1000], commit_log_file='simple-mem-log')
  
  with open(commit_log_filename, 'r') as f:
    parse_spike_commit_log(f)


if __name__ == '__main__':
  main()
