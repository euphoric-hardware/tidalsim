from typing import List, Optional, Iterator
from pathlib import Path
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import logging
import stat
import shutil
import itertools

from joblib import Parallel, delayed

from tidalsim.util.cli import run_cmd, run_cmd_capture
from tidalsim.util.random import inst_points_to_inst_steps
from tidalsim.cache_model.mtr import MTR
from tidalsim.cache_model.cache import CacheParams, CacheState, CohStatus

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

@dataclass
class SpikeCmdBlock:
    # List of commands to run in spike debug mode
    cmds: List[str]
    # The number of lines of output we expect on stdout from running the above commands
    expected_lines: int

def combine_cmd_blocks(cmd_blocks: List[SpikeCmdBlock]) -> SpikeCmdBlock:
    cmds = [block.cmds for block in cmd_blocks]
    expected_lines = [block.expected_lines for block in cmd_blocks]
    return SpikeCmdBlock(cmds=list(itertools.chain(*cmds)), expected_lines=sum(expected_lines))

# Spike commands for dumping all register state for hart [h]
def reg_dump(h: int) -> SpikeCmdBlock:
    special_reg_dump = [
        f'pc {h}',
        f'priv {h}',
        f'reg {h} fcsr',
        f'reg {h} vstart',
        f'reg {h} vxsat',
        f'reg {h} vxrm',
        f'reg {h} vcsr',
        f'reg {h} vtype',
        f'reg {h} stvec',
        f'reg {h} sscratch',
        f'reg {h} sepc',
        f'reg {h} scause',
        f'reg {h} stval',
        f'reg {h} satp',
        f'reg {h} mstatus',
        f'reg {h} medeleg',
        f'reg {h} mideleg',
        f'reg {h} mie',
        f'reg {h} mtvec',
        f'reg {h} mscratch',
        f'reg {h} mepc',
        f'reg {h} mcause',
        f'reg {h} mtval',
        f'reg {h} mip',
        f'reg {h} mcycle',
        f'reg {h} minstret',
        f'mtime',
        f'mtimecmp {h}'
    ]
    fpr_dump = [f"freg {h} {fr}" for fr in range(32)]
    xpr_dump = [f"reg {h} {xr}" for xr in range(32)]
    vreg_dump = [f"vreg {h}"]
    return SpikeCmdBlock(
        cmds=special_reg_dump + fpr_dump + xpr_dump + vreg_dump,
        expected_lines=len(special_reg_dump) + 32 + 32 + 33
    )

# Spike commands to dump all arch state for [n_harts] harts
# DRAM contents are dumped to the binary file in [mem_dump_dir] if provided, otherwise dumped into spike's cwd
def arch_state_dump(n_harts: int, mem_dump_dir: Optional[Path]) -> SpikeCmdBlock:
    mem_dump: SpikeCmdBlock
    if mem_dump_dir is None:
        mem_dump = SpikeCmdBlock(["dump"], 0)
    else:
        mem_dump = SpikeCmdBlock([f"dump {mem_dump_dir.resolve()}"], 0)

    reg_dumps: List[SpikeCmdBlock] = [reg_dump(h) for h in range(n_harts)]
    return combine_cmd_blocks([mem_dump] + reg_dumps)

# Spike commands to dump all arch state for every instruction commit point in [inst_points].
# [inst_points] are relative to the instruction at which PC = [start_pc]
def inst_points_dump(start_pc: int, inst_points: List[int], n_harts: int, ckpt_base_dir: Path) -> SpikeCmdBlock:
    inst_steps = inst_points_to_inst_steps(inst_points)
    # Run spike until PC = start_pc
    wait_for_pc = SpikeCmdBlock([f"until pc 0 {hex(start_pc)}"], 0)

    def per_interval_cmds() -> Iterator[SpikeCmdBlock]:
        for inst_num, inst_step in zip(inst_points, inst_steps):
            # Run [inst_step] instructions
            run_n_insts = SpikeCmdBlock([f"rs {inst_step}"], 1)  # spike will emit a ':' after executing an 'rs' command
            # Dump arch state, with memory in [ckpt_base_dir]/[start_pc].[inst_num]/mem.0x80000000.bin
            dump_arch_state = arch_state_dump(n_harts, ckpt_base_dir / f"{hex(start_pc)}.{inst_num}")
            yield combine_cmd_blocks([run_n_insts, dump_arch_state])
    exit_spike = SpikeCmdBlock(["quit"], 0)
    return combine_cmd_blocks([wait_for_pc] + list(per_interval_cmds()) + [exit_spike])

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
        ckpt_dir.mkdir(exist_ok=True)

    # Delete old artifacts if they exist
    for artifact in ['loadarch', 'run_spike.sh', 'spike_cmds.txt']:
        (ckpt_base_dir / artifact).unlink(missing_ok=True)
    for ckpt_dir in ckpt_dirs:
        (ckpt_dir / 'loadarch').unlink(missing_ok=True)
        (ckpt_dir / 'mem.elf').unlink(missing_ok=True)

    # Commands for spike to run in debug mode
    spike_cmds_file = ckpt_base_dir / "spike_cmds.txt"
    logging.info(f"Generating spike interactive commands in {spike_cmds_file}")
    cmd_block: SpikeCmdBlock
    with spike_cmds_file.open('w') as f:
        cmd_block = inst_points_dump(start_pc, inst_points, n_harts, ckpt_base_dir)
        f.write('\n'.join(cmd_block.cmds))

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
    assert cmd_block.expected_lines % len(inst_points) == 0
    lines_per_loadarch = cmd_block.expected_lines // len(inst_points)
    if len(loadarch_lines) != cmd_block.expected_lines:
        raise RuntimeError(f"Expected the loadarch file {loadarch_file} to contain {cmd_block.expected_lines} lines, but it actually contained {len(loadarch_lines)} lines")
    for i, ckpt_dir in enumerate(ckpt_dirs):
        with (ckpt_dir / "loadarch").open('w') as f:
            lines = loadarch_lines[lines_per_loadarch*i:lines_per_loadarch*(i+1)]
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
        # preserve the spike mem bin file for cache state reconstruction
        # spike_mem_out.unlink()
        run_cmd(f"riscv64-unknown-elf-ld -Tdata=0x80000000 -nmagic --defsym tohost={'0x%016x' % tohost} --defsym fromhost={'0x%016x' % fromhost} -o {loadmem_elf.name} {rawmem_elf.name}", cwd=ckpt_dir)
        rawmem_elf.unlink()

    Parallel(n_jobs=-1)(delayed(convert_spike_mems)(ckpt_dir) for ckpt_dir in ckpt_dirs)
