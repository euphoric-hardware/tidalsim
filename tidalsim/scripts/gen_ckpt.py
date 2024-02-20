import argparse
from pathlib import Path
import logging

from tidalsim.util.spike_ckpt import *
from tidalsim.util.cli import *
from tidalsim.util.spike_log import parse_spike_log
from tidalsim.cache_model.mtr import MTR, mtr_ckpts_from_inst_points

# This is a rewrite of the script here: https://github.com/ucb-bar/chipyard/blob/main/scripts/generate-ckpt.sh


def main():
    logging.basicConfig(
        format="%(levelname)s - %(filename)s:%(lineno)d - %(message)s", level=logging.INFO
    )

    # Parse string into an int with automatic radix detection
    def auto_int(x):
        return int(x, 0)

    parser = argparse.ArgumentParser(
        prog="gen-ckpt",
        description="Run the given binary in spike and generate checkpoints as requested",
    )
    parser.add_argument("--n-harts", type=int, default=1, help="Number of harts [default 1]")
    parser.add_argument(
        "--isa",
        type=str,
        help="ISA to pass to spike for checkpoint generation [default rv64gc]",
        default="rv64gc",
    )
    parser.add_argument(
        "--pc",
        type=auto_int,
        default=0x80000000,
        help="Advance to this PC before taking any checkpoints [default 0x80000000]",
    )
    parser.add_argument("--binary", type=str, required=True, help="Binary to run in spike")
    parser.add_argument(
        "--dest-dir", type=str, required=True, help="Directory in which checkpoints are dumped"
    )
    parser.add_argument(
        "--inst-points",
        required=True,
        nargs="+",
        help=(
            "Take checkpoints after [inst_points] have committed after advancing to the PC. This"
            " can be a list e.g. --inst-points 100 1000 2000"
        ),
    )
    parser.add_argument(
        "--cache-warmup", action="store_true", help="Generate checkpoints for L1d warmup too"
    )
    args = parser.parse_args()
    assert args.pc is not None and args.inst_points is not None
    dest_dir = Path(args.dest_dir)
    dest_dir.mkdir(exist_ok=True)
    binary = Path(args.binary)
    assert binary.is_file()
    inst_points = [int(x) for x in args.inst_points]

    # Store checkpoints in the base directory associated with the binary
    base_dir = dest_dir / f"{binary.name}.loadarch"
    base_dir.mkdir(exist_ok=True)

    mtr_ckpts: Optional[List[MTR]] = None
    if args.cache_warmup:
        # Run spike to get a full commit log
        spike_cmd = get_spike_cmd(
            binary,
            args.n_harts,
            args.isa,
            debug_file=None,
            inst_log=True,
            commit_log=True,
            suppress_exit=False,
        )
        spike_trace_file = base_dir / "spike.full_trace"
        run_cmd_pipe(spike_cmd, cwd=base_dir, stderr=spike_trace_file)
        # Generate MTR checkpoints which will be converted into cache checkpoints later
        with spike_trace_file.open("r") as f:
            spike_trace_log = parse_spike_log(f, full_commit_log=True)
            mtr_ckpts = mtr_ckpts_from_inst_points(
                spike_trace_log, block_size=64, inst_points=inst_points
            )

    # Generate all the architectural checkpoints with loadarch + DRAM content files
    gen_checkpoints(binary, args.pc, inst_points, base_dir, int(args.n_harts), args.isa)
    ckpt_dirs: List[Path] = get_ckpt_dirs(base_dir, args.pc, inst_points)

    if args.cache_warmup:
        cache_params = CacheParams(phys_addr_bits=32, block_size_bytes=64, n_sets=64, n_ways=4)
        assert mtr_ckpts
        for mtr, ckpt_dir in zip(mtr_ckpts, ckpt_dirs):
            cache_state: CacheState
            with (ckpt_dir / "mem.0x80000000.bin").open("rb") as f:
                cache_state = mtr.as_cache(cache_params, f, dram_base=0x8000_0000)
            cache_state.dump_data_arrays(ckpt_dir, "dcache_data_array")
            cache_state.dump_tag_arrays(ckpt_dir, "dcache_tag_array")
