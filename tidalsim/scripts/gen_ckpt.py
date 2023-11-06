import argparse
from pathlib import Path
import shutil
import stat
import sys

from tidalsim.util.cli import run_cmd, run_cmd_capture
from tidalsim.spike_ckpt import arch_state_dump_cmds

# This is a rewrite of the script here: https://github.com/ucb-bar/chipyard/blob/main/scripts/generate-ckpt.sh

class CkptStrategy:
    def spike_cmds_file(nharts: int) -> str:
        pass

# Take a single checkpoint after reaching `pc` and `n_insts` have committed from that point
class SinglePCCkpt(CkptStrategy):
    def __init__(self, pc: int, n_insts: int):
        self.pc = pc
        self.n_insts = n_insts

    def spike_cmds_file(nharts: int) -> str:
        # Run program until PC = self.pc
        return f"until pc 0 {hex(self.pc)}\n" + \
            # Run an additional n_insts instructions
            f"rs {self.n_insts}\n" + \
            # Dump arch state, with memory in mem.0x80000000.bin
            arch_state_dump_cmds(f, nharts) + \
            # Exit spike
            "quit\n"

# Take multiple checkpoints after reaching `pc` at every instruction commit point in `n_insts`
# n_insts = [100, 1000, 2000] means
# Take snapshots at the points where 100/1000/2000 instructions have committed
class MultiPCCkpt(CkptStrategy):
    def __init__(self, pc: int, n_insts: List[int]):
        self.pc = pc
        self.n_insts = n_insts

    def spike_cmds_file(nharts: int) -> str:
        n_insts
        pass


def gen_checkpoints(binary: Path, nharts: int, isa: str, strategy: CkptStrategy, dest_dir: Path) -> None:
    dram_base = 0x8000_0000
    dram_size = 0x1000_0000
    basemem = f"{dram_base}:{dram_size}"
    # TODO: add pmp CSR dumping commands to spike
    spike_flags = f"-p{nharts} --pmpregions=0 --isa={isa} -m{basemem}"
    basename = binary.name
    checkpoint_dir = dest_dir / f"{basename}.{hex(strategy.pc)}.{strategy.n_insts}.loadarch"
    if checkpoint_dir.exists():
        shutil.rmtree(checkpoint_dir)
    checkpoint_dir.mkdir(exist_ok=True)

    loadarch_file = checkpoint_dir / "loadarch"
    rawmem_elf = checkpoint_dir / "raw.elf"
    loadmem_elf = checkpoint_dir / "mem.elf"
    cmds_file = checkpoint_dir / "cmds_tmp.txt"
    spikecmd_file = checkpoint_dir / "spikecmd.sh"

    print(f"Generating state capture spike interactive commands in {cmds_file}")
    with open(cmds_file, 'w') as f:
        f.write(f"until pc 0 {hex(strategy.pc)}\n")
        f.write(f"rs {strategy.n_insts}\n")
        arch_state_dump(f, nharts)
        f.write("quit\n")

    spikecmd = f"spike -d --debug-cmd={cmds_file.absolute()} {spike_flags} {binary.absolute()}"
    with open(spikecmd_file, 'w') as f:
        f.write(spikecmd)
    spikecmd_file.chmod(spikecmd_file.stat().st_mode | stat.S_IEXEC)

    print(f"Capturing state at checkpoint to {loadarch_file.absolute()}")
    run_cmd(f"{spikecmd} 2> {loadarch_file.absolute()}", cwd=checkpoint_dir)

    tohost = int(run_cmd_capture(f"riscv64-unknown-elf-nm {binary.absolute()} | grep tohost | head -c 16", Path.cwd()), 16)
    fromhost = int(run_cmd_capture(f"riscv64-unknown-elf-nm {binary.absolute()} | grep fromhost | head -c 16", Path.cwd()), 16)
    print(f"Found tohost/fromhost in elf file, tohost: {hex(tohost)}, fromhost: {hex(fromhost)}")

    print(f"Compiling memory to elf")
    spike_mem_out = checkpoint_dir / "mem.0x80000000.bin"
    # NOTE: objcopy and ld produce different elfs when given absolute paths vs relative paths! So I give them relative paths
    # here to maintain consistency with the original generate-ckpt.sh script
    run_cmd(f"riscv64-unknown-elf-objcopy -I binary -O elf64-littleriscv {spike_mem_out.name} {rawmem_elf.name}", cwd=checkpoint_dir)
    spike_mem_out.unlink()
    run_cmd(f"riscv64-unknown-elf-ld -Tdata=0x80000000 -nmagic --defsym tohost={'0x%016x' % tohost} --defsym fromhost={'0x%016x' % fromhost} -o {loadmem_elf.name} {rawmem_elf.name}", cwd=checkpoint_dir)
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
