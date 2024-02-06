from dataclasses import dataclass
from intervaltree import IntervalTree, Interval

@dataclass
class BasicBlocks:
    pc_to_bb_id: IntervalTree
