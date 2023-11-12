import argparse
from pathlib import Path
import shutil
import stat
import sys
from joblib import Parallel, delayed
import pickle
import logging

from tidalsim.util.cli import run_cmd, run_cmd_capture, run_cmd_pipe
from tidalsim.util.spike_ckpt import *
from tidalsim.bb.spike import parse_spike_log, spike_trace_to_bbs, spike_trace_to_bbvs, BasicBlocks

# Runs directory structure
# dest-dir
#   - binary_name-hash
#     - spike.trace (full spike commit log)
#     - spike.bb (pickled BasicBlocks extracted from spike trace)
#     - elf.bb (pickled BasicBlocks extracted from elf analysis)

def main():
    logging.basicConfig(format='%(levelname)s - %(filename)s:%(lineno)d - %(message)s', level=logging.INFO)

    parser = argparse.ArgumentParser(
                    prog='tidalsim',
                    description='Sampled simulation')
    parser.add_argument('--binary', type=str, required=True, help='RISC-V binary to run')
    parser.add_argument('-n', '--interval-length', type=int, required=True, help='Length of a program interval in instructions')
    # parser.add_argument('--n-harts', type=int, default=1, help='Number of harts [default 1]')
    n_harts = 1 # hardcode this for now
    # parser.add_argument('--isa', type=str, help='ISA to pass to spike [default rv64gc]', default='rv64gc')
    isa = "rv64gc" # hardcode this for now
    parser.add_argument('--dest-dir', type=str, required=True, help='Directory in which checkpoints are dumped')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    args = parser.parse_args()
    binary = Path(args.binary).resolve()
    binary_name = binary.name
    dest_dir = Path(args.dest_dir).resolve()
    dest_dir.mkdir(exist_ok=True)
    cwd = Path.cwd()
    assert args.interval_length > 1
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    logging.info(f"""Tidalsim called with:
    binary = {binary}
    interval_length = {args.interval_length}
    dest_dir = {dest_dir}""")

    # Create the binary directory if it doesn't exist
    # Ignore the possibility of hash collisions as these can only happen for binaries that have the same name and the same first 8 hex characters of their hash
    binary_hash = run_cmd_capture(f"sha256sum {binary.absolute()} | cut -d ' ' --fields 1", cwd=dest_dir)
    binary_dir = dest_dir / f"{binary_name}-{binary_hash[:8]}"
    binary_dir.mkdir(exist_ok=True)
    logging.info(f"Working directory set to {binary_dir}")

    # Create the spike commit log if it doesn't already exist
    spike_trace_file = binary_dir / "spike.trace"
    if spike_trace_file.exists():
        assert spike_trace_file.is_file()
        logging.info(f"Spike trace file already exists in {spike_trace_file}, not rerunning spike")
    else:
        logging.info(f"Spike trace doesn't exist at {spike_trace_file}, running spike")
        spike_cmd = get_spike_cmd(binary, n_harts, isa, debug_file=None, extra_args = "-l")
        run_cmd_pipe(spike_cmd, cwd=dest_dir, stderr=spike_trace_file)

    # Construct basic blocks from spike commit log if it doesn't already exist
    bb: BasicBlocks
    spike_bb_file = binary_dir / "spike.bb"
    if not spike_bb_file.exists():
        logging.info(f"Running spike commit log based BB extraction")
        with spike_trace_file.open('r') as f:
            spike_trace_log = parse_spike_log(f)
            bb = spike_trace_to_bbs(spike_trace_log)
            with spike_bb_file.open('wb') as bb_file:
                pickle.dump(bb, bb_file)
            logging.info(f"Spike commit log based BB extraction results saved to {spike_bb_file}")
    else:
        logging.info(f"Spike commit log based BB extraction already run, loading results from {spike_bb_file}")
        with spike_bb_file.open('rb') as bb_file:
            bb = pickle.load(bb_file)
    logging.debug(f"Basic blocks: {bb}")

    # Given an interval length, compute the BBV-based interval embedding
    embedding_dir = binary_dir / str(args.interval_length)
    embedding_dir.mkdir(exist_ok=True)
    embedding_matrix = embedding_dir / "bbv.matrix"
    matrix: np.ndarray
    if not embedding_matrix.exists():
        logging.info(f"Computing BBV embedding in {embedding_matrix}")
        with spike_trace_file.open('r') as spike_trace:
            spike_trace_log = parse_spike_log(spike_trace)
            matrix = spike_trace_to_bbvs(spike_trace_log, bb, args.interval_length)
            with embedding_matrix.open('wb') as matrix_file:
                pickle.dump(matrix, matrix_file)
    else:
        logging.info(f"BBV embedding already computed in {embedding_matrix}, loading")
        with embedding_matrix.open('rb') as matrix_file:
            matrix = pickle.load(matrix_file)
    logging.debug(f"Embedding matrix:\n{matrix}")
    logging.info(f"Embedding matrix shape: {matrix.shape}")

    # Perform clustering and select centroids
    


    # Capture arch checkpoints from spike
