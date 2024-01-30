from dataclasses import dataclass, field
from typing import List, Iterator
from pathlib import Path
from math import ceil
from enum import IntEnum

def clog2(x):
  """Ceiling of log2"""
  if x <= 0:
    raise ValueError("domain error")
  return (x-1).bit_length()

# Coherency status, see ClientMetadata / ClientStates in rocket-chip
class CohStatus(IntEnum):
  Nothing = 0
  Branch  = 1
  Trunk   = 2
  Dirty   = 3

@dataclass
class CacheBlock:
  data: int
  tag: int
  coherency: CohStatus

@dataclass
class CacheParams:
  phys_addr_bits: int
  block_size_bytes: int
  n_sets: int
  n_ways: int
  offset_bits: int = field(init=False)
  set_bits: int = field(init=False)
  tag_bits: int = field(init=False)
  coherency_bits: int = 2  # see CohStatus
  tag_bits: int = field(init=False)
  tag_bits_hex_chars: int = field(init=False)
  block_size_bits: int = field(init=False)
  tag_mask: int = field(init=False)
  coherency_mask: int = field(init=False)

  def __post_init__(self) -> None:
    self.offset_bits = clog2(self.block_size_bytes)
    self.set_bits = clog2(self.n_sets)
    self.tag_bits = self.phys_addr_bits - self.set_bits - self.offset_bits
    self.tag_bits_hex_chars = ceil(self.tag_bits / 4)
    self.block_size_bits = self.block_size_bytes * 8
    self.tag_mask = (1 << self.tag_bits) - 1
    self.coherency_mask = (1 << self.coherency_bits) - 1

@dataclass
class CacheState:
  params: CacheParams
  # the cache array is first indexed by way, then by set
  array: List[List[CacheBlock]] = field(init=False)

  def __post_init__(self) -> None:
    self.array = [[CacheBlock(0, 0, CohStatus.Nothing) for _ in range(self.params.n_sets)] for _ in range(self.params.n_ways)]

  def fill_with_structured_data(self) -> None:
    for way_idx, way in enumerate(self.array):
      for set_idx in range(self.params.n_sets):
        tag_bottom_bits = (way_idx * self.params.n_sets) + set_idx
        # put a '1' in the top bit of the tag, just to make sure we can set it during injection
        tag = (1 << (self.params.tag_bits - 1)) | tag_bottom_bits
        # Fill data array with unique data in every byte position
        data_bytes = [way_idx*self.params.block_size_bytes + set_idx*self.params.block_size_bytes + i + 1 for i in range(self.params.block_size_bytes)]
        data = 0
        for i, byte in enumerate(data_bytes):
          data = data | ((byte & 0xff) << (i*8))
        self.array[way_idx][set_idx] = CacheBlock(data, tag, CohStatus.Dirty)

  def way_idx_iterator(self, reverse_ways: bool) -> Iterator[int]:
    return reversed(range(self.params.n_ways)) if reverse_ways else range(self.params.n_ways)

  def ways_str(self, reverse_ways: bool) -> str:
    return ', '.join([f"Way {i}" for i in self.way_idx_iterator(reverse_ways)])

  def tag_array_pretty_str(self, reverse_ways: bool = True) -> str:
    def inner() -> Iterator[str]:
      yield f"Ways: {self.ways_str(reverse_ways)}"
      for set_idx in range(self.params.n_sets):
        cache_blocks = [self.array[way_idx][set_idx] for way_idx in self.way_idx_iterator(reverse_ways)]
        tags_str = ', '.join([f'{{:#0{self.params.tag_bits_hex_chars}x}} {{}}'.format(block.tag, block.coherency.name) for block in cache_blocks])
        yield f"Set {set_idx:02d}: [{tags_str}]"
    return '\n'.join([x for x in inner()])

  def tag_array_binary_str(self, way_idx: int) -> str:
    def inner() -> Iterator[str]:
      for set_idx in range(self.params.n_sets):
        cache_block = self.array[way_idx][set_idx]
        tag = cache_block.tag & self.params.tag_mask
        coherency = int(cache_block.coherency) & self.params.coherency_mask
        tag_array_data = (coherency << self.params.tag_bits) | tag
        yield f"{{:0{self.params.tag_bits + self.params.coherency_bits}b}}".format(tag_array_data)
    return '\n'.join([x for x in inner()])

  def dump_tag_arrays(self, dir: Path, prefix: str) -> None:
    for way_idx in range(self.params.n_ways):
      tag_array_bin = self.tag_array_binary_str(way_idx)
      with (dir / f"{prefix}{way_idx}.bin").open('w') as f:
        f.write(tag_array_bin)
    with (dir / f"tag_array.pretty").open('w') as f:
      f.write(self.tag_array_pretty_str())

  def data_array_pretty_str(self, reverse_ways: bool = True) -> Iterator[str]:
    yield f"Ways: {self.ways_str(reverse_ways)}"
