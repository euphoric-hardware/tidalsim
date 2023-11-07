import argparse
from pathlib import Path
import shutil
import stat
import sys

from tidalsim.util.cli import run_cmd, run_cmd_capture
from tidalsim.util.spike_ckpt import *

# This is a rewrite of the script here: https://github.com/ucb-bar/chipyard/blob/main/scripts/generate-ckpt.sh


def gen_checkpoints(strategy: CkptStrategy) -> None:
    # TODO: refactor this (if) we have multiple checkpointing strategies
    assert isinstance(strategy, StartPCAndInstPoints)

    # Store checkpoints in the base directory associated with the strategy and binary
    base_dir = strategy.get_base_dir()
    print(f"Placing checkpoints in {base_dir}")
    base_dir.mkdir(exist_ok=True)

    # Store each checkpoint in a subdirectory underneath [base_dir]
    ckpt_dirs = strategy.get_ckpt_dirs()
    print(f"Taking checkpoints in {ckpt_dirs}")
    for ckpt_dir in ckpt_dirs:
        if ckpt_dir.exists():
            shutil.rmtree(ckpt_dir)
        ckpt_dir.mkdir(exist_ok=True)

    # Commands for spike to run in debug mode
    spike_cmds_file = strategy.cmds_file
    print(f"Generating state capture spike interactive commands in {spike_cmds_file}")
    with spike_cmds_file.open('w') as f:
        f.write(strategy.spike_cmds())

    # The spike invocation command itself
    spike_cmd = strategy.get_spike_cmd()
    run_spike_cmd_file = base_dir / "run_spike.sh"
    with run_spike_cmd_file.open('w') as f:
        f.write(spike_cmd)
    run_spike_cmd_file.chmod(run_spike_cmd_file.stat().st_mode | stat.S_IEXEC)

    # Actually run spike
    print(f"Running spike")
    loadarch_file = base_dir / 'loadarch'
    run_cmd(f"{spike_cmd} 2> {loadarch_file.absolute()}", cwd=base_dir)

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
    tohost = int(run_cmd_capture(f"riscv64-unknown-elf-nm {strategy.binary.absolute()} | grep tohost | head -c 16", Path.cwd()), 16)
    fromhost = int(run_cmd_capture(f"riscv64-unknown-elf-nm {strategy.binary.absolute()} | grep fromhost | head -c 16", Path.cwd()), 16)
    print(f"Found tohost/fromhost in binary elf file, tohost: {hex(tohost)}, fromhost: {hex(fromhost)}")

    for ckpt_dir in ckpt_dirs:
        print(f"Compiling memory to elf in {ckpt_dir}")
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
    # Parse string into an int with automatic radix detection
    def auto_int(x):
        return int(x, 0)

    parser = argparse.ArgumentParser(
                    prog='dump_spike_checkpoint',
                    description='Run the given binary in spike and generate checkpoints as requested')
    parser.add_argument('--n-harts', type=int, default=1, help='Number of harts [default 1]')
    parser.add_argument('--isa', type=str, help='ISA to pass to spike for checkpoint generation [default rv64gc]', default='rv64gc')
    parser.add_argument('--pc', type=auto_int, default=0x80000000, help='Advance to this PC before taking any checkpoints [default 0x80000000]')
    parser.add_argument('--binary', type=str, required=True, help='Binary to run in spike')
    parser.add_argument('--dest-dir', type=str, required=True, help='Directory in which checkpoints are dumped')
    parser.add_argument('--n-insts', required=True, nargs='+', help='Take checkpoints after n_insts have committed after advancing to the PC. This can be a list e.g. --n-insts 100 1000 2000')
    args = parser.parse_args()
    assert args.pc is not None and args.n_insts is not None
    dest_dir = Path(args.dest_dir)
    dest_dir.mkdir(exist_ok=True)
    binary = Path(args.binary)
    assert binary.is_file()
    strategy = StartPCAndInstPoints(args.pc, [int(x) for x in args.n_insts], dest_dir, binary, args.n_harts, args.isa)
    gen_checkpoints(strategy)
