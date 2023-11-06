from typing import List
from pathlib import Path
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class CkptStrategy(ABC):
    @abstractmethod
    def spike_cmds(self, nharts: int) -> str:
        return NotImplemented

# Take a single checkpoint after reaching `pc` and `n_insts` have committed from that point
@dataclass
class SinglePCCkpt(CkptStrategy):
    pc: int
    n_insts: int

    def spike_cmds(self, nharts: int) -> str:
        # Run program until PC = self.pc
        wait_for_pc = f"until pc 0 {hex(self.pc)}\n"
        # Run an additional n_insts instructions
        run_n_insts = f"rs {self.n_insts}\n"
        # Dump arch state, with memory in mem.0x80000000.bin
        dump_arch_state = arch_state_dump_cmds(nharts)
        # Exit spike
        exit_spike = "quit\n"
        return wait_for_pc + run_n_insts + dump_arch_state + exit_spike

# Take multiple checkpoints after reaching `pc` at every instruction commit point in `n_insts`
# n_insts = [100, 1000, 2000] means
# Take snapshots at the points where 100/1000/2000 instructions have committed
@dataclass
class MultiPCCkpt(CkptStrategy):
    pc: int
    n_insts: List[int]

    def spike_cmds(self, nharts: int) -> str:
        return NotImplemented

def get_base_dir(dest_dir: Path, binary: Path) -> Path:
    return dest_dir / f"{binary.name}.loadarch"

def get_ckpt_dir(dest_dir: Path, binary: Path, pc: int, n_insts: int) -> Path:
    return get_base_dir(dest_dir, binary) / f"{hex(pc)}.{n_insts}"

def get_spike_flags(nharts: int, dram_size: int = 0x1000_0000, isa: str = 'rv64gc') -> str:
    dram_base = 0x8000_0000
    basemem = f"{dram_base}:{dram_size}"
    # TODO: add pmp CSR dumping commands to spike
    spike_flags = f"-p{nharts} --pmpregions=0 --isa={isa} -m{basemem}"
    return spike_flags

def get_spike_cmd(cmds_file: Path, isa: str, nharts: int, binary: Path) -> str:
    spike_flags = get_spike_flags(nharts, isa=isa)
    return f"spike -d --debug-cmd={cmds_file.absolute()} {spike_flags} {binary.absolute()}"

def arch_state_dump_cmds(nharts: int) -> str:
    mem_dump = "dump\n"
    def reg_dump(h: int):
        return f"""pc {h}
priv {h}
reg {h} fcsr
reg {h} vstart
reg {h} vxsat
reg {h} vxrm
reg {h} vcsr
reg {h} vtype
reg {h} stvec
reg {h} sscratch
reg {h} sepc
reg {h} scause
reg {h} stval
reg {h} satp
reg {h} mstatus
reg {h} medeleg
reg {h} mideleg
reg {h} mie
reg {h} mtvec
reg {h} mscratch
reg {h} mepc
reg {h} mcause
reg {h} mtval
reg {h} mip
reg {h} mcycle
reg {h} minstret
mtime
mtimecmp {h}\n""" \
        + ''.join([f"freg {h} {fr}\n" for fr in range(32)]) \
        + ''.join([f"reg {h} {xr}\n" for xr in range(32)]) \
        + f"vreg {h}\n"

    return mem_dump + ''.join([reg_dump(h) for h in range(nharts)])
