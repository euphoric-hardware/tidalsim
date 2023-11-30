import argparse
from pathlib import Path
import shutil
import stat
import sys
from joblib import Parallel, delayed
import logging
import pdb
from pandera.typing import DataFrame
import numpy as np

from tidalsim.util.cli import run_cmd, run_cmd_capture, run_cmd_pipe, run_cmd_pipe_stdout
from tidalsim.util.spike_ckpt import *
from tidalsim.bb.spike import parse_spike_log, spike_trace_to_bbs, spike_trace_to_bbvs, BasicBlocks
from tidalsim.bb.elf import objdump_to_bbs
from tidalsim.util.pickle import dump, load
from tidalsim.modeling.clustering import *
from tidalsim.modeling.schemas import *

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
    parser.add_argument('-c', '--clusters', type=int, required=True, help='Number of clusters')
    # parser.add_argument('--n-harts', type=int, default=1, help='Number of harts [default 1]')
    n_harts = 1 # hardcode this for now
    # parser.add_argument('--isa', type=str, help='ISA to pass to spike [default rv64gc]', default='rv64gc')
    isa = "rv64gc" # hardcode this for now
    parser.add_argument('--simulator', type=str, required=True, help='Path to the RTL simulator binary with state injection support')
    parser.add_argument('--chipyard-root', type=str, required=True, help='Path to the base of Chipyard')
    parser.add_argument('--dest-dir', type=str, required=True, help='Directory in which checkpoints are dumped')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('-e', '--elf', action='store_true', help='Run ELF-based basic block extraction')
    args = parser.parse_args()

    # Parse args
    binary = Path(args.binary).resolve()
    binary_name = binary.name
    simulator = Path(args.simulator).resolve()
    assert simulator.exists() and simulator.is_file()
    chipyard_root = Path(args.chipyard_root).resolve()
    assert chipyard_root.is_dir()
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
    binary_hash = run_cmd_capture(f"sha256sum {binary.resolve()} | cut -d ' ' --fields 1", cwd=dest_dir)
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

    bb: BasicBlocks

    if args.elf:
        # Construct basic blocks from elf if it doesn't already exist
        elf_bb_file = binary_dir / "elf_basicblocks.pickle"
        if elf_bb_file.exists():
            logging.info(f"ELF-based BB extraction already run, loading results from {elf_bb_file}")
            bb = load(elf_bb_file)
        else:
            logging.info(f"Running ELF-based BB extraction")
            # Check if objdump file exists, else run objdump
            objdump_file = binary_dir / f"{binary_name}.objdump"
            if objdump_file.exists():
                logging.info(f"Using objdump file found at {objdump_file}")
            else:
                objdump_cmd = f"riscv64-unknown-elf-objdump -d {str(binary)}"
                logging.info(f"Running {objdump_cmd} to generate objdump from riscv binary")
                run_cmd_pipe_stdout(objdump_cmd, cwd=dest_dir, stdout=objdump_file)

            with objdump_file.open('r') as f:
                bb = objdump_to_bbs(f)
                dump(bb, elf_bb_file)
            logging.info(f"ELF-based BB extraction results saved to {elf_bb_file}")
    else:
        # Construct basic blocks from spike commit log if it doesn't already exist
        spike_bb_file = binary_dir / "spike_basicblocks.pickle"
        if spike_bb_file.exists():
            logging.info(f"Spike commit log based BB extraction already run, loading results from {spike_bb_file}")
            bb = load(spike_bb_file)
        else:
            logging.info(f"Running spike commit log based BB extraction")
            with spike_trace_file.open('r') as f:
                spike_trace_log = parse_spike_log(f)
                bb = spike_trace_to_bbs(spike_trace_log)
                dump(bb, spike_bb_file)
            logging.info(f"Spike commit log based BB extraction results saved to {spike_bb_file}")

    logging.debug(f"Basic blocks: {bb}")

    # Given an interval length, compute the BBV-based interval embedding

    if args.elf:
        embedding_dir = binary_dir / f"n_{args.interval_length}_elf"
    else:
        embedding_dir = binary_dir / f"n_{args.interval_length}_spike"

    embedding_dir.mkdir(exist_ok=True)
    embedding_df_file = embedding_dir / "embedding_df.pickle"
    embedding_df: DataFrame[EmbeddingSchema]
    if embedding_df_file.exists():
        logging.info(f"BBV embedding dataframe exists in {embedding_df_file}, loading")
        embedding_df = load(embedding_df_file)
    else:
        logging.info(f"Computing BBV embedding dataframe")
        with spike_trace_file.open('r') as spike_trace:
            spike_trace_log = parse_spike_log(spike_trace)
            embedding_df = spike_trace_to_bbvs(spike_trace_log, bb, args.interval_length)
            dump(embedding_df, embedding_df_file)
        logging.info(f"Saving BBV embedding dataframe to {embedding_df_file}")
    logging.info(f"BBV embedding dataframe:\n{embedding_df}")
    logging.info(f"BBV embedding # of features: {embedding_df['embedding'][0].size}")

    # Perform clustering and select centroids
    cluster_dir = embedding_dir / f"c_{args.clusters}"
    cluster_dir.mkdir(exist_ok=True)
    logging.info(f"Storing clustering for clusters = {args.clusters} in: {cluster_dir}")

    # TODO: standardize features and see if that makes a difference for clustering
    from sklearn.cluster import KMeans
    kmeans_file = cluster_dir / "kmeans_model.pickle"
    keams: KMeans
    if kmeans_file.exists():
        logging.info(f"Loading k-means model from {kmeans_file}")
        kmeans = load(kmeans_file)
    else:
        logging.info(f"Performing k-means clustering with {args.clusters} clusters")
        matrix = np.vstack(embedding_df['embedding'].to_numpy()) # type: ignore
        kmeans = KMeans(n_clusters=args.clusters, n_init="auto", verbose=100, random_state=100).fit(matrix)
        logging.info(f"Saving k-means model to {kmeans_file}")
        dump(kmeans, kmeans_file)

    # Augment the dataframe with the cluster label, distances, and whether a given sample should be simulated
    clustering_df_file = cluster_dir / "clustering_df.pickle"
    clustering_df: DataFrame[ClusteringSchema]
    if clustering_df_file.exists():
        logging.info(f"Loading clustering DF from {clustering_df_file}")
        clustering_df = load(clustering_df_file)
    else:
        clustering_df = embedding_df.assign(
            cluster_id = kmeans.labels_,
            dist_to_centroid = lambda x: np.linalg.norm(np.vstack(embedding_df['embedding'].to_numpy()) - kmeans.cluster_centers_[x['cluster_id']], axis=1), # type: ignore
            chosen_for_rtl_sim = lambda x: x.groupby('cluster_id')['dist_to_centroid'].transform(lambda dists: dists == np.min(dists))
        )
        dump(clustering_df, clustering_df_file)
        logging.info(f"Saving clustering DF to {clustering_df_file}")

    logging.info(f"Clustering DF\n{clustering_df}")

    to_simulate = clustering_df.loc[clustering_df['chosen_for_rtl_sim'] == True].groupby('cluster_id', as_index=False).nth(0)
    logging.info(f"The following rows are closest to the cluster centroids\n{to_simulate}")

    # Capture arch checkpoints from spike
    # Cache this result if all the checkpoints are already available
    checkpoint_insts: List[int] = to_simulate['inst_count'].tolist()
    checkpoint_dir = cluster_dir / "checkpoints"
    checkpoint_dir.mkdir(exist_ok=True)
    checkpoints = [checkpoint_dir / f"0x80000000.{i}" for i in checkpoint_insts]
    checkpoints_exist = [(c / "loadarch").exists() and (c / "mem.elf").exists() for c in checkpoints]
    if all(checkpoints_exist):
        logging.info("Checkpoints already exist, not rerunning spike")
    else:
        logging.info("Generating arch checkpoints with spike")
        gen_checkpoints(binary, start_pc=0x8000_0000, n_insts=checkpoint_insts, ckpt_base_dir=checkpoint_dir, n_harts=n_harts, isa=isa)

    # Run each checkpoint in RTL sim and extract perf metrics
    perf_files_exist = all([(c / "perf.csv").exists() for c in checkpoints])
    if perf_files_exist:
        logging.info("Performance metrics for checkpoints already collected, skipping RTL simulation")
    else:
        logging.info("Running parallel RTL simulations to collect performance metrics for checkpoints")
        def run_rtl_sim(checkpoint_dir: Path) -> None:
            rtl_sim_cmd = f"{simulator} \
                    +permissive \
                    +dramsim \
                    +dramsim_ini_dir={chipyard_root}/generators/testchipip/src/main/resources/dramsim2_ini \
                    +max-cycles=10000000 +no_hart0_msip \
                    +perf-sample-period={int(args.interval_length / 10)} \
                    +perf-file={(checkpoint_dir / 'perf.csv').resolve()} \
                    +max-instructions={args.interval_length} \
                    +ntb_random_seed_automatic \
                    +loadmem={checkpoint_dir / 'mem.elf'} \
                    +loadarch={checkpoint_dir / 'loadarch'} \
                    +permissive-off \
                    {checkpoint_dir / 'mem.elf'}"
                    # +verbose \
            run_cmd(rtl_sim_cmd, cwd=checkpoint_dir)
        Parallel(n_jobs=-1)(delayed(run_rtl_sim)(checkpoint) for checkpoint in checkpoints)
