import re
from typing import Iterator, List
from dataclasses import dataclass

from intervaltree import IntervalTree, Interval
from tqdm import tqdm
import numpy as np

# Regex patterns to extract instructions or symbols from Spike dump
instruction_pattern = re.compile(r"core\s*\d: 0x(?P<pc>\w+) \((?P<inst>\w+)\)")
name_pattern = re.compile(r"core\s*\d:\s*>>>>\s*(?P<name>\w+)")

@dataclass
class BasicBlocks:
    pc_to_bb_id: IntervalTree

@dataclass
class SpikeTraceEntry:
    pc: int
    raw_inst: int
    decoded_inst: str

def parse_spike_log(log_lines: Iterator[str]) -> Iterator[SpikeTraceEntry]:
    for line in log_lines:
        s = line.split()
        if s[2][0] == '>':
            # TODO: add the spike extracted section labels to SpikeTraceEntry
            continue
        else:
            yield SpikeTraceEntry(int(s[2][2:], 16), int(s[3][3:-1], 16), s[4])

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
control_insts = branches + jumps + syscalls

def spike_trace_to_bbs(trace: Iterator[SpikeTraceEntry]) -> BasicBlocks:
    # Make initial pass through the Spike dump
    # A new interval is recorded when the PC changes by more than 4
    # The end of the previous Interval is the PC that was jumped from
    # The start of the next Interval is the PC that was jumped to
    # No data is stored, speeds up the lookup significantly
    start = None
    previous_inst = None
    intervals = IntervalTree()
    for trace_entry in tqdm(trace):
        # if (abs(trace_entry.pc - previous) > 4):
        #     intervals[start:previous + 1] = None # Intervals are inclusive of the start, but exclusive of the end
        #     start = trace_entry.pc
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
    if start is not None:
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

def spike_log_to_bbvs(log_lines: Iterator[str], bb: BasicBlocks, interval_length: int) -> List[np.ndarray]:
    N = len(list(log_lines))  # TODO: this should be lazy
    ks = [100]

    # Make a second pass through and compute the BBV for each interval for each k
    # BBV shape is (basic block, interval) meaning the basic block vector is in the columns
    bbvs = [np.zeros((len(intervals), N // k + 1)) for k in ks]
    for (i, line) in tqdm(enumerate(lines)):
            if instruction := instruction_pattern.match(line):
                pc = int(instruction.group("pc"), 16)
                (interval,) = unique_intervals[pc]
                for (j, k) in enumerate(ks):
                    bbvs[j][interval.data, i // k] += 1
    return bbvs
