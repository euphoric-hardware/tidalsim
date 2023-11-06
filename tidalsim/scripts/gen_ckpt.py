import argparse
from pathlib import Path
import shutil
import stat
import sys

from tidalsim.util.cli import run_cmd, run_cmd_capture
from tidalsim.util.spike_ckpt import *

# This is a rewrite of the script here: https://github.com/ucb-bar/chipyard/blob/main/scripts/generate-ckpt.sh


def gen_checkpoints(binary: Path, nharts: int, isa: str, strategy: CkptStrategy, dest_dir: Path) -> None:
    base_dir = get_base_dir(dest_dir, binary)
    print(f"Placing checkpoints in {base_dir}")
    base_dir.mkdir(exist_ok=True)
    assert isinstance(strategy, SinglePCCkpt)
    ckpt_dir = get_ckpt_dir(dest_dir, binary, strategy.pc, strategy.n_insts)
    print(f"Taking checkpoint in {ckpt_dir}")
    if ckpt_dir.exists():
        shutil.rmtree(ckpt_dir)
    ckpt_dir.mkdir(exist_ok=True)

    # Commands for spike to run in debug mode
    spike_cmds_file = base_dir / "spike_cmds.txt"
    print(f"Generating state capture spike interactive commands in {spike_cmds_file}")
    with spike_cmds_file.open('w') as f:
        f.write(strategy.spike_cmds(nharts))

    # The spike invocation command itself
    spike_cmd = get_spike_cmd(spike_cmds_file, isa, nharts, binary)
    run_spike_cmd_file = base_dir / "run_spike.sh"
    with run_spike_cmd_file.open('w') as f:
        f.write(spike_cmd)
    run_spike_cmd_file.chmod(run_spike_cmd_file.stat().st_mode | stat.S_IEXEC)


    # Actually run spike
    print(f"Running spike")
    run_cmd(f"{spike_cmd} 2> {(ckpt_dir / 'loadarch').absolute()}", cwd=ckpt_dir)

    tohost = int(run_cmd_capture(f"riscv64-unknown-elf-nm {binary.absolute()} | grep tohost | head -c 16", Path.cwd()), 16)
    fromhost = int(run_cmd_capture(f"riscv64-unknown-elf-nm {binary.absolute()} | grep fromhost | head -c 16", Path.cwd()), 16)
    print(f"Found tohost/fromhost in binary elf file, tohost: {hex(tohost)}, fromhost: {hex(fromhost)}")

    print(f"Compiling memory to elf")
    spike_mem_out = ckpt_dir / "mem.0x80000000.bin"
    rawmem_elf = ckpt_dir / "raw.elf"
    loadmem_elf = ckpt_dir / "mem.elf"
    # NOTE: objcopy and ld produce different elfs when given absolute paths vs relative paths! So I give them relative paths
    # here to maintain consistency with the original generate-ckpt.sh script
    run_cmd(f"riscv64-unknown-elf-objcopy -I binary -O elf64-littleriscv {spike_mem_out.name} {rawmem_elf.name}", cwd=ckpt_dir)
    spike_mem_out.unlink()
    run_cmd(f"riscv64-unknown-elf-ld -Tdata=0x80000000 -nmagic --defsym tohost={'0x%016x' % tohost} --defsym fromhost={'0x%016x' % fromhost} -o {loadmem_elf.name} {rawmem_elf.name}", cwd=ckpt_dir)
    rawmem_elf.unlink()

def main():
    def auto_int(x):
        return int(x, 0)

    parser = argparse.ArgumentParser(
                    prog='dump_spike_checkpoint',
                    description='Run the given binary in spike and generate checkpoints as requested')
    parser.add_argument('--nharts', type=int, default=1, help='Number of harts')
    parser.add_argument('--binary', type=str, required=True, help='Binary to run in spike')
    parser.add_argument('--isa', type=str, help='ISA to pass to spike for checkpoint generation [default rv64gc]', default='rv64gc')
    parser.add_argument('--dest-dir', type=str, required=True)
    parser.add_argument('--pc', type=auto_int, default=0x80000000, help='PC to take checkpoint at [default 0x80000000]')
    parser.add_argument('--n-insts', type=auto_int, default=0, help='Instructions after PC to take checkpoint at [default 0]')
    args = parser.parse_args()
    assert args.pc is not None and args.n_insts is not None
    dest_dir = Path(args.dest_dir)
    dest_dir.mkdir(exist_ok=True)
    binary = Path(args.binary)
    assert binary.is_file()
    strategy = SinglePCCkpt(args.pc, args.n_insts)
    gen_checkpoints(binary, args.nharts, args.isa, strategy, dest_dir)
