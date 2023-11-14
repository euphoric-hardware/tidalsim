import argparse
from pathlib import Path
import logging

from tidalsim.util.spike_ckpt import *

# This is a rewrite of the script here: https://github.com/ucb-bar/chipyard/blob/main/scripts/generate-ckpt.sh

def main():
    logging.basicConfig(format='%(levelname)s - %(filename)s:%(lineno)d - %(message)s', level=logging.INFO)

    # Parse string into an int with automatic radix detection
    def auto_int(x):
        return int(x, 0)

    parser = argparse.ArgumentParser(
                    prog='gen-ckpt',
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

    # Store checkpoints in the base directory associated with the binary
    base_dir = dest_dir / f"{binary.name}.loadarch"
    base_dir.mkdir(exist_ok=True)
    gen_checkpoints(binary, args.pc, [int(x) for x in args.n_insts], base_dir, args.n_harts, args.isa)
