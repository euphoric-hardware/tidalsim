from typing import List, Optional
from pathlib import Path
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import logging
import stat
import shutil

from joblib import Parallel, delayed

from tidalsim.util.cli import run_cmd, run_cmd_capture
from tidalsim.util.random import inst_points_to_inst_steps

def get_spike_cmd(binary: Path, n_harts: int, isa: str, debug_file: Optional[Path], inst_log: bool, commit_log: bool, suppress_exit: bool) -> str:
    # TODO: add pmp CSR dumping commands to spike
    debug_flags = "" if debug_file is None else f"-d --debug-cmd={debug_file.resolve()}"
    dram_base = 0x8000_0000
    dram_size = 0x1000_0000
    basemem = f"{dram_base}:{dram_size}"
    spike_flags = f"-p{n_harts} --pmpregions=0 --isa={isa} -m{basemem}"
    inst_log_flag = "-l" if inst_log else ""
    commit_log_flag = "--log-commits" if commit_log else ""
    suppress_exit_flag = "+suppress-exit" if suppress_exit else ""  # This is an HTIF flag and must be passed last!
    return f"spike {debug_flags} {spike_flags} {inst_log_flag} {commit_log_flag} {suppress_exit_flag} {binary.resolve()}"

# Returns a string of commands for spike's interactive (debug) mode that will print
# all the non-DRAM architectural state of a hart to stdout
def arch_state_dump_cmds(nharts: int, mem_dump_dir: Optional[Path]) -> str:
    mem_dump = "dump\n" if mem_dump_dir is None else f"dump {mem_dump_dir.resolve()}\n"
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

# Returns a string of commands for spike debug mode that will execute the binary until
# PC = [start_pc], then take checkpoints at the total instruction commit points in [inst_points]
def spike_cmds(start_pc: int, inst_points: List[int], n_harts: int, ckpt_base_dir: Path) -> str:
    inst_steps = inst_points_to_inst_steps(inst_points)
    # Run program until PC = start_pc
    wait_for_pc = f"until pc 0 {hex(start_pc)}\n"

    def per_interval_cmds():
        for inst_num, inst_step in zip(inst_points, inst_steps):
            # Run [inst_step] instructions
            run_n_insts = f"rs {inst_step}\n"
            # Dump arch state, with memory in [ckpt_base_dir]/[start_pc].[inst_num]/mem.0x80000000.bin
            dump_arch_state = arch_state_dump_cmds(n_harts, ckpt_base_dir / f"{hex(start_pc)}.{inst_num}")
            yield run_n_insts + dump_arch_state
    exit_spike = "quit"
    return wait_for_pc + ''.join(list(per_interval_cmds())) + exit_spike

def get_ckpt_dirs(ckpt_base_dir: Path, start_pc: int, inst_points: List[int]) -> List[Path]:
    return [ckpt_base_dir / f"{hex(start_pc)}.{i}" for i in inst_points]

# Take checkpoints after reaching [pc] at every instruction commit point in [inst_points]
# inst_points = [100, 1000, 2000] means
# Take snapshots at the points where 100/1000/2000 instructions have committed
def gen_checkpoints(binary: Path, start_pc: int, inst_points: List[int], ckpt_base_dir: Path, n_harts: int = 1, isa: str = 'rv64gc') -> None:
    logging.info(f"Placing checkpoints in {ckpt_base_dir}")

    # Store each checkpoint in a subdirectory underneath [ckpt_base_dir]
    ckpt_dirs = get_ckpt_dirs(ckpt_base_dir, start_pc, inst_points)
    logging.info(f"Creating checkpoint directories: {ckpt_dirs}")
    for ckpt_dir in ckpt_dirs:
        if ckpt_dir.exists():
            shutil.rmtree(ckpt_dir)
        ckpt_dir.mkdir(exist_ok=True)

    # Commands for spike to run in debug mode
    spike_cmds_file = ckpt_base_dir / "spike_cmds.txt"
    logging.info(f"Generating spike interactive commands in {spike_cmds_file}")
    with spike_cmds_file.open('w') as f:
        f.write(spike_cmds(start_pc, inst_points, n_harts, ckpt_base_dir))

    # The spike invocation command itself
    spike_cmd = get_spike_cmd(binary, n_harts, isa, spike_cmds_file, inst_log=False, commit_log=False, suppress_exit=True)
    run_spike_cmd_file = ckpt_base_dir / "run_spike.sh"
    with run_spike_cmd_file.open('w') as f:
        f.write(spike_cmd)
    run_spike_cmd_file.chmod(run_spike_cmd_file.stat().st_mode | stat.S_IEXEC)

    # Actually run spike
    logging.info(f"Running spike")
    loadarch_file = ckpt_base_dir / 'loadarch'
    run_cmd(f"{spike_cmd} 2> {loadarch_file.resolve()}", cwd=ckpt_base_dir)

    # Spike emits a single loadarch file which needs to be split among the multiple checkpoints
    loadarch_lines = loadarch_file.open('r').readlines()
    split_idxs = [i for i, x in enumerate(loadarch_lines) if x == ':\n'] + [len(loadarch_lines)]
    diffs = [(split_idxs[i] - split_idxs[i-1]) for i in range(1, len(split_idxs))]
    assert all([x == diffs[0] for x in diffs]), "different number of lines per loadarch! something is wrong."
    for i, ckpt_dir in enumerate(ckpt_dirs):
        with (ckpt_dir / "loadarch").open('w') as f:
            lines = loadarch_lines[split_idxs[i]:split_idxs[i+1]]
            f.write(''.join(lines))
    # loadarch_file.unlink()

    # Capture tohost/fromhost memory addresses from original binary
    tohost = int(run_cmd_capture(f"riscv64-unknown-elf-nm {binary.resolve()} | grep tohost | head -c 16", Path.cwd()), 16)
    fromhost = int(run_cmd_capture(f"riscv64-unknown-elf-nm {binary.resolve()} | grep fromhost | head -c 16", Path.cwd()), 16)
    logging.info(f"Found tohost/fromhost in binary elf file, tohost: {hex(tohost)}, fromhost: {hex(fromhost)}")

    def convert_spike_mems(ckpt_dir: Path) -> None:
        logging.info(f"Compiling memory to elf in {ckpt_dir}")
        spike_mem_out = ckpt_dir / "mem.0x80000000.bin"
        rawmem_elf = ckpt_dir / "raw.elf"
        loadmem_elf = ckpt_dir / "mem.elf"
        # NOTE: objcopy and ld produce different elfs when given absolute paths vs relative paths!
        # So I give them relative paths here to maintain consistency with the original generate-ckpt.sh script
        run_cmd(f"riscv64-unknown-elf-objcopy -I binary -O elf64-littleriscv {spike_mem_out.name} {rawmem_elf.name}", cwd=ckpt_dir)
        spike_mem_out.unlink()
        run_cmd(f"riscv64-unknown-elf-ld -Tdata=0x80000000 -nmagic --defsym tohost={'0x%016x' % tohost} --defsym fromhost={'0x%016x' % fromhost} -o {loadmem_elf.name} {rawmem_elf.name}", cwd=ckpt_dir)
        rawmem_elf.unlink()

    Parallel(n_jobs=-1)(delayed(convert_spike_mems)(ckpt_dir) for ckpt_dir in ckpt_dirs)
