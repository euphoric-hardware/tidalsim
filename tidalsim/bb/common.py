from dataclasses import dataclass
import bisect
from typing import List, Tuple, Optional, cast

# Tuple of [left, right), where the left is inclusive and the right is not.
Interval = Tuple[int, int]

# Tuple of the location of the event (which starts a new basic block), and up to what non-inclusive location
# we consider it a valid code path. This is useful since if the location lies outside of the valid codepaths
# by the blocks that prcede it, we can mark it as being empty space rather than being a BasicBlock.
Event = Tuple[int, int]

# Tuple of the start of a basic block and the id it maps to. If the basic block id is None, then it is not
# really a basic block but empty space.
Marker = Tuple[int, int | None]

@dataclass
class BasicBlocks:
    markers: List[Marker]
    markers_idx: List[int]
    length: int

    def __init__(self, markers: List[Marker]):
        self.markers = markers
        self.markers_idx = list(map(lambda x: x[0], markers))
        self.length = len([bb_idx for _, bb_idx in self.markers if bb_idx is not None])

    def pc_to_bb_id(self, pc: int) -> Optional[int]:
        bisect_index = bisect.bisect(self.markers_idx, pc) - 1

        if bisect_index == len(self.markers):
            return None

        _, basic_block = self.markers[bisect_index]
        return basic_block

    def __len__(self):
        # Counts the number of markers that map to the start of a basic block
        return self.length

def intervals_to_events(intervals: List[Interval]) -> List[Event]:
    events: List[Tuple[int, int]] = []
    for start, end in intervals:
        events += [(start, end), (end, 0)]
    return events

def events_to_markers(events: List[Event]) -> List[Marker]:
    left = 0
    right = 0
    idx = 0
    markers: List[Marker] = []

    # We sort events from left-to-right, but only really care about the highest value at each location
    for pc, valid in sorted(events, key=lambda tup: (tup[0], -tup[1])):
        right = max(valid, right)

        # If pc <= left, we already processed this location and marked it as a basic block
        if pc <= left:
            continue
        # If pc < right, this block lies inside a valid code path and we assign it an id
        if pc < right:
            markers += [cast(Marker, (pc, idx))]
            idx += 1
        # If pc >= right, this block lies outside a valid code path and we assign it None
        else:
            markers += [cast(Marker, (pc, None))]

        left = pc

    return markers


def intervals_to_markers(intervals: List[Interval]) -> List[Marker]:
    events = intervals_to_events(intervals)
    markers = events_to_markers(events)
    return markers

# RISC-V Psuedoinstructions: https://github.com/riscv-non-isa/riscv-asm-manual/blob/master/riscv-asm.md#pseudoinstructions
branches = [
        # RV64I branches
        'beq', 'bge', 'bgeu', 'blt', 'bltu', 'bne',
        # RV64C branches
        'c.beqz', 'c.bnez',
        # Psuedo instructions
        'beqz', 'bnez', 'blez', 'bgez', 'bltz', 'bgtz', 'bgt', 'ble', 'bgtu', 'bleu'
        ]
jumps = ['j', 'jal', 'jr', 'jalr', 'ret', 'call', 'c.j', 'c.jal', 'c.jr', 'c.jalr', 'tail']
syscalls = ['ecall', 'ebreak', 'mret', 'sret', 'uret']
control_insts = set(branches + jumps + syscalls)

no_target_insts = set(syscalls + ['jr', 'jalr', 'c.jr', 'c.jalr', 'ret'])
