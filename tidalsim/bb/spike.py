import re
from typing import Iterator, List, Optional
from dataclasses import dataclass
import functools

from intervaltree import IntervalTree, Interval
from tqdm import tqdm
import numpy as np
from more_itertools import ichunked
from joblib import Parallel, delayed

# Regex patterns to extract instructions or symbols from Spike dump
instruction_pattern = re.compile(r"core\s*\d: 0x(?P<pc>\w+) \((?P<inst>\w+)\)")
name_pattern = re.compile(r"core\s*\d:\s*>>>>\s*(?P<name>\w+)")

@dataclass
class BasicBlocks:
    pc_to_bb_id: IntervalTree

@dataclass
class SpikeTraceEntry:
    pc: int
    decoded_inst: str

def parse_spike_log(log_lines: Iterator[str]) -> Iterator[SpikeTraceEntry]:
    for line in log_lines:
        s = line.split()
        if s[2][0] == '>':
            # TODO: add the spike extracted section labels to SpikeTraceEntry
            continue
        else:
            # yield SpikeTraceEntry(int(s[2][2:], 16), int(s[3][3:-1], 16), s[4])
            yield SpikeTraceEntry(int(s[2][2:], 16), s[4])

# RISC-V Psuedoinstructions: https://github.com/riscv-non-isa/riscv-asm-manual/blob/master/riscv-asm.md#pseudoinstructions
branches = [
        # RV64I branches
        'beq', 'bge', 'bgeu', 'blt', 'bltu', 'bne',
        # RV64C branches
        'c.beqz', 'c.bnez',
        # Psuedo instructions
        'beqz', 'bnez', 'blez', 'bgez', 'bltz', 'bgtz', 'bgt', 'ble', 'bgtu', 'bleu'
        ]
jumps = ['j', 'jal', 'jr', 'jalr', 'ret', 'call', 'c.j', 'c.jal', 'c.jr', 'c.jalr']
syscalls = ['ecall', 'ebreak', 'mret', 'sret', 'uret']
control_insts = set(branches + jumps + syscalls)

def spike_trace_to_bbs(trace: Iterator[SpikeTraceEntry]) -> BasicBlocks:
    # Make initial pass through the Spike dump
    # A new interval is recorded when the PC changes by more than 4
    # The end of the previous Interval is the PC that was jumped from
    # The start of the next Interval is the PC that was jumped to
    # No data is stored, speeds up the lookup significantly
    start = None
    previous_inst: Optional[SpikeTraceEntry] = None
    intervals = IntervalTree()
    for trace_entry in tqdm(trace):
        if start is None:
            start = trace_entry.pc
        if trace_entry.decoded_inst in control_insts:
            intervals[start:trace_entry.pc + 1] = None # Intervals are inclusive of the start, but exclusive of the end
            start = None
        if previous_inst and (abs(trace_entry.pc - previous_inst.pc) > 4) and previous_inst.decoded_inst not in control_insts:
            raise RuntimeError(f"Control diverged from PC: {hex(previous_inst.pc)} \
                    to PC: {hex(trace_entry.pc)}, but the last instruction {previous_inst.decoded_inst} \
                    wasn't a control instruction")
        previous_inst = trace_entry
    if start is not None and previous_inst is not None:
        intervals[start:previous_inst.pc+1] = None

    # Ensures that PCs have a one-to-one mapping to an interval
    intervals.merge_equals()
    intervals.split_overlaps()

    # Assign each interval an index in the BBV vector
    # Easier to just instantiate a new tree for lookup later
    id = 0
    unique_intervals = IntervalTree()
    for interval in sorted(intervals.items()):
        unique_intervals.addi(interval.begin, interval.end, id)
        id += 1
    return BasicBlocks(pc_to_bb_id=unique_intervals)

def spike_trace_to_bbvs(trace: Iterator[SpikeTraceEntry], bb: BasicBlocks, interval_length: int) -> np.ndarray:
    # Dimensions of matrix
    # # rows = # of intervals = ceil( (length of trace) / interval_length )
    # # cols = # of features = # of elements in the intervaltree
    n_features = len(bb.pc_to_bb_id)
    matrix: List[np.ndarray] = []
    trace_intervals = ichunked(trace, interval_length)

    # Provide some speedup to avoid querying the interval tree too often
    @functools.lru_cache(maxsize=128)
    def lookup_id_from_pc(pc: int) -> int:
        return bb.pc_to_bb_id[pc].pop().data

    def embed_interval(interval: Iterator[SpikeTraceEntry]) -> np.ndarray:
        embedding = np.zeros(n_features)
        for trace_entry in interval:
            bb_id = lookup_id_from_pc(trace_entry.pc)
            embedding[bb_id] += 1
        return embedding

    for trace_interval in tqdm(trace_intervals):
        matrix.append(embed_interval(trace_interval))
    return np.vstack(matrix)
