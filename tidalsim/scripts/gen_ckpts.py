import argparse
from pathlib import Path
import os
from tidalsim.util.cli import run_cmd, run_cmd_capture

def main():
    parser = argparse.ArgumentParser(
                    prog='gen_checkpoints',
                    description='Generate a bunch of checkpoints for a RISC-V binary')
    parser.add_argument('--binary', type=str, required=True)
    parser.add_argument('--dest-dir', type=str, required=True)
    args = parser.parse_args()
    binary = Path(args.binary)
    assert binary.is_file()
    dest_dir = Path(args.dest_dir)
    dest_dir.mkdir(exist_ok=True)
    cwd = Path.cwd()
    generate_ckpt_script = Path(os.getenv("CONDA_PREFIX")).parent / "scripts" / "generate-ckpt.sh"
    # for
    run_cmd(f"{generate_ckpt_script.absolute()} -b {binary.absolute()} -i 1000",cwd=dest_dir)
