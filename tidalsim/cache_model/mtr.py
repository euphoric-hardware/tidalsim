from typing import Iterator, TypeAlias, Dict, Optional, List, Tuple, BinaryIO
from dataclasses import dataclass, field
import copy
import itertools
from pathlib import Path

from tidalsim.cache_model.cache import CacheParams, CacheState, CohStatus, Array
from tidalsim.util.spike_log import SpikeTraceEntry, SpikeCommitInfo, Op
from tidalsim.util.random import clog2, inst_points_to_inst_steps

# This "Memory Timestamp Record" data structure tracks memory accesses and at a given point
# can tell you which cache blocks will be resident for a particular cache configuration.
# Details here: http://scale.eecs.berkeley.edu/papers/mtr-ispass05-slides.pdf

CacheBlockAddr: TypeAlias = int

@dataclass
class MTREntry:
  last_readtime: Optional[int]  # will become a List[Optional[int]] in multicore MTR
  last_writetime: Optional[int]
  last_writer: Optional[int] = None  # only used in multicore MTR

  def get_last_touched_time(self) -> int:
    # Treat read and write access times identically for now
    last_writetime = self.last_writetime if self.last_writetime is not None else 0
    last_readtime = self.last_readtime if self.last_readtime is not None else 0
    return max(last_writetime, last_readtime)

  def __lt__(self, other) -> bool:
    # We want MTREntry's to be sorted from most recently touched to least recently touched
    return self.get_last_touched_time() > other.get_last_touched_time()


@dataclass
class MTR:
  block_size_bytes: int
  table: Dict[CacheBlockAddr, MTREntry] = field(default_factory=lambda: {})
  byte_offset_bits: int = field(init=False)

  def __post_init__(self) -> None:
    self.byte_offset_bits = clog2(self.block_size_bytes)

  def get_block_addr(self, byte_addr: int) -> CacheBlockAddr:
    return (byte_addr >> self.byte_offset_bits)

  def update(self, commit: SpikeCommitInfo, timestamp: int) -> None:
    block_addr = self.get_block_addr(commit.address)
    if block_addr not in self.table:
      mtr_entry = MTREntry(None, None)
      self.table[block_addr] = mtr_entry

    if commit.op is Op.Load:
      self.table[block_addr].last_readtime = timestamp
    else:
      self.table[block_addr].last_writetime = timestamp

  # Reconstruct the state of a particular cache configuration given by [params] and load
  # the cache with data from [dram_bin] which is a binary file containing DRAM contents and
  # assume the base of DRAM is at [dram_base]
  def as_cache(self, params: CacheParams, dram_bin: Optional[BinaryIO] = None, dram_base: int = 0x8000_0000) -> CacheState:
    def get_set_idx(block_addr: CacheBlockAddr) -> int:
      return (block_addr & ((1 << params.set_bits) - 1))

    def get_cache_block(byte_addr: int) -> int:
      if dram_bin is None:
        return 0
      else:
        dram_bin.seek(byte_addr - dram_base)
        data = dram_bin.read(params.block_size_bytes)
        return int.from_bytes(data, byteorder='little')

    assert params.block_size_bytes == self.block_size_bytes
    cache = CacheState(params)
    # Group block addresses by set
    block_addrs = sorted(self.table.keys(), key=get_set_idx)
    sets = itertools.groupby(block_addrs, key=get_set_idx)
    for set_idx, set_block_addrs in sets:
      set_mtr_entries: List[Tuple[CacheBlockAddr, MTREntry]] = [(a, self.table[a]) for a in set_block_addrs]
      # Figure out which addrs should be resident in this cache using LRU
      set_mtr_entries.sort(key=lambda x: x[1])
      resident_block_addrs = [x[0] for x in set_mtr_entries[:params.n_ways]]
      for way_idx, block_addr in enumerate(resident_block_addrs):
        # Shift away the set bits and mask the tag bits
        tag = (block_addr >> params.set_bits) & params.tag_mask
        cache_block = cache.array[way_idx][set_idx]
        cache_block.tag = tag
        cache_block.coherency = CohStatus.Dirty
        byte_address = (block_addr << params.offset_bits)
        cache_block.data = get_cache_block(byte_address)
    return cache

# Given a spike log, an initial MTR state and the number of instructions to pull from
# the spike log, return a *new* MTR state after consuming instructions from the log iterator
def mtr_ckpts_from_spike_log(spike_log: Iterator[SpikeTraceEntry], initial_mtr: MTR, insts_to_consume: int) -> MTR:
  new_mtr = copy.deepcopy(initial_mtr)
  for _ in range(insts_to_consume):
    inst = next(spike_log)
    if inst.commit_info:
      new_mtr.update(inst.commit_info, inst.inst_count)
  return new_mtr

def mtr_ckpts_from_inst_points(spike_log: Iterator[SpikeTraceEntry], block_size: int, inst_points: List[int]) -> List[MTR]:
  mtr = MTR(block_size)
  mtr_ckpts: List[MTR] = [mtr]
  inst_steps = inst_points_to_inst_steps(inst_points)
  for step in inst_steps:
    new_mtr = mtr_ckpts_from_spike_log(spike_log, mtr_ckpts[-1], step)
    mtr_ckpts.append(new_mtr)
  return mtr_ckpts[1:]
