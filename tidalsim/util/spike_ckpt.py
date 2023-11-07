from typing import List, Optional
from pathlib import Path
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

@dataclass
class CkptStrategy(ABC):
    @abstractmethod
    def spike_cmds(self, nharts: int, dest_dir: Path, binary: Path) -> str:
        return NotImplemented

# Take checkpoints after reaching `pc` at every instruction commit point in `n_insts`
# n_insts = [100, 1000, 2000] means
# Take snapshots at the points where 100/1000/2000 instructions have committed
@dataclass
class StartPCAndInstPoints(CkptStrategy):
    pc: int
    n_insts: List[int]
    dest_dir: Path
    binary: Path
    n_harts: int
    isa: str
    inst_steps: List[int] = field(init=False)
    cmds_file: Path = field(init=False)

    def __post_init__(self):
        self.inst_steps = n_insts_to_inst_steps(self.n_insts)
        self.cmds_file = self.get_base_dir() / "spike_cmds.txt"

    def get_base_dir(self) -> Path:
        return self.dest_dir / f"{self.binary.name}.loadarch"

    def get_ckpt_dir(self, n_insts: int) -> Path:
        return self.get_base_dir() / f"{hex(self.pc)}.{n_insts}"

    def get_ckpt_dirs(self) -> List[Path]:
        return [self.get_ckpt_dir(inst_num) for inst_num in self.n_insts]

    def spike_cmds(self) -> str:
        # Run program until PC = self.pc
        wait_for_pc = f"until pc 0 {hex(self.pc)}\n"

        def per_interval_cmds():
            for inst_num, inst_step in zip(self.n_insts, self.inst_steps):
                # Run [inst_step] instructions
                run_n_insts = f"rs {inst_step}\n"
                # Dump arch state, with memory in [ckpt_dir]/mem.0x80000000.bin
                dump_arch_state = arch_state_dump_cmds(self.n_harts, self.get_ckpt_dir(inst_num))
                yield run_n_insts + dump_arch_state
        exit_spike = "quit\n"
        return wait_for_pc + ''.join(list(per_interval_cmds())) + exit_spike

    def get_spike_flags(self, dram_size: int = 0x1000_0000) -> str:
        dram_base = 0x8000_0000
        basemem = f"{dram_base}:{dram_size}"
        # TODO: add pmp CSR dumping commands to spike
        spike_flags = f"-p{self.n_harts} --pmpregions=0 --isa={self.isa} -m{basemem}"
        return spike_flags

    def get_spike_cmd(self) -> str:
        spike_flags = self.get_spike_flags()
        return f"spike -d --debug-cmd={self.cmds_file.absolute()} {spike_flags} {self.binary.absolute()}"

def n_insts_to_inst_steps(n_insts: List[int]) -> List[int]:
    inst_steps = [n_insts[0]] + [(n_insts[i] - n_insts[i-1]) for i in range(1, len(n_insts))]
    assert all(step > 0 for step in inst_steps)
    return inst_steps

def arch_state_dump_cmds(nharts: int, mem_dump_dir: Optional[Path]) -> str:
    mem_dump = "dump\n" if mem_dump_dir is None else f"dump {mem_dump_dir.absolute()}\n"
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
