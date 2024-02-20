from dataclasses import dataclass
from typing import Iterator, Optional, List, Iterable
from enum import IntEnum
from more_itertools import chunked
import logging

# RISC-V Psuedoinstructions: https://github.com/riscv-non-isa/riscv-asm-manual/blob/master/riscv-asm.md#pseudoinstructions
branches = [
    # RV64I branches
    "beq",
    "bge",
    "bgeu",
    "blt",
    "bltu",
    "bne",
    # RV64C branches
    "c.beqz",
    "c.bnez",
    # Psuedo instructions
    "beqz",
    "bnez",
    "blez",
    "bgez",
    "bltz",
    "bgtz",
    "bgt",
    "ble",
    "bgtu",
    "bleu",
]
jumps = ["j", "jal", "jr", "jalr", "ret", "call", "c.j", "c.jal", "c.jr", "c.jalr", "tail"]
syscalls = ["ecall", "ebreak", "mret", "sret", "uret"]
control_insts = set(branches + jumps + syscalls)
no_target_insts = set(syscalls + ["jr", "jalr", "c.jr", "c.jalr", "ret"])


class Op(IntEnum):
    Store = 0
    Load = 1


@dataclass
class SpikeCommitInfo:
    address: int
    data: int
    op: Op


@dataclass
class SpikeTraceEntry:
    pc: int
    # the raw decoded instruction from spike
    decoded_inst: str
    # the absolute dynamic instruction count. [inst_count] is zero-indexed
    inst_count: int
    # if the spike log was collected with --log-commits and this trace entry is a memory operation,
    #   [commit_info] will contain the memory operation
    commit_info: Optional[SpikeCommitInfo] = None

    def is_control_inst(self) -> bool:
        return self.decoded_inst in control_insts


# [full_commit_log] = True if spike was ran with '-l --log-commits', False if spike is only run with '-l'
def parse_spike_log(log_lines: Iterator[str], full_commit_log: bool) -> Iterator[SpikeTraceEntry]:
    inst_count = 0
    for line in log_lines:
        # Example of first line (regular commit log)
        # core   0: 0x0000000080001a8e (0x00009522) c.add   a0, s0
        s = line.split()
        if s[2][0] == ">":
            continue  # this is a spike-decoded label, ignore it
        pc = int(s[2][2:], 16)
        decoded_inst = s[4]
        # Ignore spike trace outside DRAM
        if pc < 0x8000_0000:
            if full_commit_log:
                next(log_lines, None)
            continue
        commit_info: Optional[SpikeCommitInfo] = None
        if full_commit_log:
            # If the current line is a valid instruction, then we can be sure the next line
            # will contain the commit info
            line2 = next(log_lines, None)
            # Examples of line2 (only seen in full commit log)

            # Regular instruction (single writeback)
            # core   0: 3 0x0000000080001310 (0x832a) x6  0x0000000080023000
            # <hartid>: <priv>          <PC> <inst> <rd>  <writeback data>

            # Store instruction
            # core   0: 3 0x0000000080001bf4 (0xe11c) mem 0x0000000080002050 0x0000000080002060
            # <hartid>: <priv>          <PC>   <inst>           <store addr>       <store data>

            # Load instruction
            # core   0: 3 0x0000000080000250 (0x638c) x11 0x0000000080001d68 mem 0x0000000080001d90
            # <hartid>: <priv>          <PC>   <inst> <rd>       <load data>            <load addr>
            assert line2 is not None
            s2 = line2.split()
            s2_len = len(s2)
            if s2_len == 8 and s2[5] == "mem":  # store instruction
                commit_info = SpikeCommitInfo(
                    address=int(s2[6][2:], 16), data=int(s2[7][2:], 16), op=Op.Store
                )
            elif s2_len == 9 and s2[7] == "mem":  # load instruction
                commit_info = SpikeCommitInfo(
                    address=int(s2[8][2:], 16), data=int(s2[6][2:], 16), op=Op.Load
                )
        yield SpikeTraceEntry(pc, decoded_inst, inst_count, commit_info)
        inst_count += 1
