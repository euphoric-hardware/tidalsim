from typing import Iterator, TypeAlias, Dict, Optional, List
from dataclasses import dataclass, field
import copy

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
