from dataclasses import dataclass, field
from typing import List, Iterator, Iterable
from pathlib import Path
from math import ceil
from enum import IntEnum, Enum

from more_itertools import chunked

from tidalsim.util.random import clog2

# Coherency status, see ClientMetadata / ClientStates in rocket-chip
class CohStatus(IntEnum):
  Nothing = 0
  Branch  = 1
  Trunk   = 2
  Dirty   = 3

class Array(Enum):
  Tag = 0
  Data = 1

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
  tag_hex_chars: int = field(init=False)
  data_hex_chars: int = field(init=False)
  block_size_bits: int = field(init=False)
  tag_mask: int = field(init=False)
  coherency_mask: int = field(init=False)
  data_bus_bytes: int = 8  # this is the default in Rocket
  data_rows_per_set: int = field(init=False)

  def __post_init__(self) -> None:
    self.offset_bits = clog2(self.block_size_bytes)
    self.set_bits = clog2(self.n_sets)
    self.tag_bits = self.phys_addr_bits - self.set_bits - self.offset_bits
    self.tag_hex_chars = ceil(self.tag_bits / 4)
    self.data_hex_chars = self.block_size_bytes * 2
    self.block_size_bits = self.block_size_bytes * 8
    self.tag_mask = (1 << self.tag_bits) - 1
    self.coherency_mask = (1 << self.coherency_bits) - 1
    self.data_rows_per_set = self.block_size_bytes // self.data_bus_bytes

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

  def way_idx_iterator(self, reverse_ways: bool) -> Iterable[int]:
    return reversed(range(self.params.n_ways)) if reverse_ways else range(self.params.n_ways)

  def ways_str(self, reverse_ways: bool) -> str:
    return ', '.join([f"Way {i}" for i in self.way_idx_iterator(reverse_ways)])

  def array_pretty_str(self, array: Array, reverse_ways: bool = True) -> str:
    def inner() -> Iterator[str]:
      yield f"Ways: {self.ways_str(reverse_ways)}"
      for set_idx in range(self.params.n_sets):
        cache_blocks = [self.array[way_idx][set_idx] for way_idx in self.way_idx_iterator(reverse_ways)]
        if array == Array.Tag:
          # +2 tag_hex_chars to account for the leading '0x'
          tag_blocks = [f'{block.tag:#0{self.params.tag_hex_chars + 2}x} {block.coherency.name}' for block in cache_blocks]
          tag_str = ', '.join(tag_blocks)
          yield f"Set {set_idx:02d}: [{tag_str}]"
        else:
          assert array == Array.Data
          # +2 data_hex_chars to account for the leading '0x'
          data_blocks = [f'{block.data:#0{self.params.data_hex_chars + 2}x}' for block in cache_blocks]
          data_str = '\n'.join(data_blocks)
          yield f"Set {set_idx:02d}: [\n{data_str}\n]"
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
    with (dir / f"{prefix}.pretty").open('w') as f:
      f.write(self.array_pretty_str(Array.Tag))

  def data_array_binary_str(self, way_idx: int) -> str:
    rows_per_set = self.params.block_size_bytes // self.params.data_bus_bytes
    def inner() -> Iterator[str]:
      for set_idx in range(self.params.n_sets):
        cache_block = self.array[way_idx][set_idx]
        # data is params.block_size_bytes wide
        data = cache_block.data
        # The data array for a given way is 8B wide and has enough entries to hold n_sets sets
        # This means data must be split into 8B wide rows
        for i in range(rows_per_set):
          row = data & ((1 << (self.params.data_bus_bytes*8)) - 1)
          yield f"{{:0{self.params.data_bus_bytes*8}b}}".format(row)
          data = data >> (self.params.data_bus_bytes*8)
    return '\n'.join([x for x in inner()])

  def dump_data_arrays(self, dir: Path, prefix: str) -> None:
    for way_idx in range(self.params.n_ways):
      bin_for_way = self.data_array_binary_str(way_idx).split('\n')
      data_to_write: List[List[str]] = [[] for _ in range(self.params.data_bus_bytes)]
      for line in bin_for_way:
        # We must slice each line byte-wise since the L1d is made up of byte-wise RAMs
        line_bytes_chunked = [''.join(x) for x in list(chunked(line, 8, strict=True))]
        # Each line goes from MSB byte to LSB byte but the RAMs are from LSB byte to MSB byte
        line_bytes = list(reversed(line_bytes_chunked))
        for byte_idx in range(self.params.data_bus_bytes):
          data_to_write[byte_idx].append(line_bytes[byte_idx])
      for byte_idx in range(self.params.data_bus_bytes):
        with (dir / f"{prefix}{way_idx*self.params.data_bus_bytes + byte_idx}.bin").open('w') as f:
          f.write('\n'.join(data_to_write[byte_idx]))
    with (dir / f"{prefix}.pretty").open('w') as f:
      f.write(self.array_pretty_str(Array.Data))
