import argparse
from pathlib import Path
import shutil
import stat
import sys
from joblib import Parallel, delayed
import logging
import pdb
import pprint
from pandera.typing import DataFrame
import numpy as np

from tidalsim.util.cli import run_cmd, run_cmd_capture, run_cmd_pipe, run_cmd_pipe_stdout
from tidalsim.util.spike_ckpt import *
from tidalsim.util.spike_log import parse_spike_log
from tidalsim.bb.spike import spike_trace_to_bbs, spike_trace_to_embedding_df, BasicBlocks
from tidalsim.bb.elf import objdump_to_bbs
from tidalsim.util.pickle import dump, load
from tidalsim.util.random import inst_points_to_inst_steps
from tidalsim.modeling.clustering import *
from tidalsim.modeling.schemas import *
from tidalsim.cache_model.mtr import mtr_ckpts_from_inst_points, MTR


def run_rtl_sim(
    simulator: Path,
    perf_file: Path,
    perf_sample_period: int,
    max_instructions: Optional[int],
    chipyard_root: Path,
    binary: Path,
    loadarch: Path,
    cwd: Path,
    suppress_exit: bool,
    checkpoint_dir: Optional[Path],
    timeout_cycles: int = 10_000_000,
) -> None:
    max_insts_str = f"+max-instructions={max_instructions}" if max_instructions is not None else ""
    checkpoint_dir_str = (
        f"+checkpoint-dir={checkpoint_dir.resolve()}" if checkpoint_dir is not None else ""
    )
    # +no_hart0_msip = with loadarch, the target should begin execution immediately without
    #   an interrupt required to jump out of the bootrom
    rtl_sim_cmd = (
        f"{simulator}             +permissive             +dramsim            "
        f" +dramsim_ini_dir={chipyard_root.resolve()}/generators/testchipip/src/main/resources/dramsim2_ini"
        "             +no_hart0_msip             +ntb_random_seed_automatic            "
        f" +max-cycles={timeout_cycles}             +perf-sample-period={perf_sample_period}       "
        f"      +perf-file={perf_file.resolve()}             {max_insts_str}            "
        f" +loadmem={binary.resolve()}             +loadarch={loadarch.resolve()}            "
        f" {checkpoint_dir_str}             +permissive-off            "
        f" {'+suppress-exit' if suppress_exit else ''}             {binary.resolve()}"
    )
    run_cmd(rtl_sim_cmd, cwd)


def main():
    logging.basicConfig(
        format="%(levelname)s - %(filename)s:%(lineno)d - %(message)s", level=logging.INFO
    )

    parser = argparse.ArgumentParser(prog="tidalsim", description="Sampled simulation")
    parser.add_argument("--binary", type=str, required=True, help="RISC-V binary to run")
    parser.add_argument(
        "-n",
        "--interval-length",
        type=int,
        required=True,
        help="Length of a program interval in instructions",
    )
    parser.add_argument("-c", "--clusters", type=int, required=True, help="Number of clusters")
    # parser.add_argument('--n-harts', type=int, default=1, help='Number of harts [default 1]')
    n_harts = 1  # hardcode this for now
    # parser.add_argument('--isa', type=str, help='ISA to pass to spike [default rv64gc]', default='rv64gc')
    isa = "rv64gc"  # hardcode this for now
    parser.add_argument(
        "--simulator",
        type=str,
        required=True,
        help="Path to the RTL simulator binary with state injection support",
    )
    parser.add_argument(
        "--chipyard-root", type=str, required=True, help="Path to the base of Chipyard"
    )
    parser.add_argument(
        "--dest-dir", type=str, required=True, help="Directory in which checkpoints are dumped"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument(
        "-e", "--elf", action="store_true", help="Run ELF-based basic block extraction"
    )
    parser.add_argument(
        "--golden-sim",
        action="store_true",
        help="Run full RTL simulation of the binary and save performance metrics",
    )
    parser.add_argument(
        "--cache-warmup",
        action="store_true",
        help=(
            "Use functional warmup to initialize the L1d cache at the start of each RTL simulation"
        ),
    )
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
    binary_hash = run_cmd_capture(
        f"sha256sum {binary.resolve()} | cut -d ' ' --fields 1", cwd=dest_dir
    )
    binary_dir = dest_dir / f"{binary_name}-{binary_hash[:8]}"
    binary_dir.mkdir(exist_ok=True)
    logging.info(f"Working directory set to {binary_dir}")

    # Create the spike commit log if it doesn't already exist
    spike_trace_file = (
        (binary_dir / "spike.full_trace") if args.cache_warmup else (binary_dir / "spike.trace")
    )
    full_commit_log = args.cache_warmup
    if spike_trace_file.exists():
        assert spike_trace_file.is_file()
        logging.info(f"Spike trace file already exists in {spike_trace_file}, not rerunning spike")
    else:
        logging.info(f"Spike trace doesn't exist at {spike_trace_file}, running spike")
        spike_cmd = get_spike_cmd(
            binary,
            n_harts,
            isa,
            debug_file=None,
            inst_log=True,
            commit_log=full_commit_log,
            suppress_exit=False,
        )
        run_cmd_pipe(spike_cmd, cwd=dest_dir, stderr=spike_trace_file)

    if args.golden_sim:
        golden_sim_dir = binary_dir / "golden"
        golden_sim_dir.mkdir(exist_ok=True)
        golden_perf_file = golden_sim_dir / "perf.csv"
        logging.info(f"Running full RTL simulation of {binary} in {golden_sim_dir}")

        if golden_perf_file.exists() and golden_perf_file.is_file():
            logging.info(
                f"Golden performance results already exist in {golden_sim_dir}, not-rerunning RTL"
                " simulation"
            )
        else:
            logging.info(f"Taking spike checkpoint at instruction 0 to inject into RTL simulation")
            gen_checkpoints(
                binary,
                start_pc=0x8000_0000,
                inst_points=[0],
                ckpt_base_dir=golden_sim_dir,
                n_harts=n_harts,
                isa=isa,
            )
            inst_0_ckpt = golden_sim_dir / "0x80000000.0"
            run_rtl_sim(
                simulator=simulator,
                perf_file=golden_perf_file,
                perf_sample_period=args.interval_length,
                max_instructions=None,
                chipyard_root=chipyard_root,
                binary=(inst_0_ckpt / "mem.elf"),
                loadarch=(inst_0_ckpt / "loadarch"),
                suppress_exit=False,
                checkpoint_dir=None,
                cwd=golden_sim_dir,
            )
        sys.exit(0)

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

            with objdump_file.open("r") as f:
                bb = objdump_to_bbs(f)
                dump(bb, elf_bb_file)
            logging.info(f"ELF-based BB extraction results saved to {elf_bb_file}")
    else:
        # Construct basic blocks from spike commit log if it doesn't already exist
        spike_bb_file = binary_dir / "spike_basicblocks.pickle"
        if spike_bb_file.exists():
            logging.info(
                "Spike commit log based BB extraction already run, loading results from"
                f" {spike_bb_file}"
            )
            bb = load(spike_bb_file)
        else:
            logging.info(f"Running spike commit log based BB extraction")
            with spike_trace_file.open("r") as f:
                spike_trace_log = parse_spike_log(f, full_commit_log)
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
        with spike_trace_file.open("r") as spike_trace:
            spike_trace_log = parse_spike_log(spike_trace, args.cache_warmup)
            embedding_df = spike_trace_to_embedding_df(spike_trace_log, bb, args.interval_length)
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
        matrix = np.vstack(embedding_df["embedding"].to_numpy())  # type: ignore
        kmeans = KMeans(n_clusters=args.clusters, n_init="auto", verbose=100, random_state=100).fit(
            matrix
        )
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
            cluster_id=kmeans.labels_,
            dist_to_centroid=lambda x: np.linalg.norm(np.vstack(embedding_df["embedding"].to_numpy()) - kmeans.cluster_centers_[x["cluster_id"]], axis=1),  # type: ignore
            chosen_for_rtl_sim=lambda x: x.groupby("cluster_id")["dist_to_centroid"].transform(
                lambda dists: dists == np.min(dists)
            ),
        )
        dump(clustering_df, clustering_df_file)
        logging.info(f"Saving clustering DF to {clustering_df_file}")

    logging.info(f"Clustering DF\n{clustering_df}")

    to_simulate = (
        clustering_df.loc[clustering_df["chosen_for_rtl_sim"] == True]
        .groupby("cluster_id", as_index=False)
        .nth(0)
    )
    logging.info(f"The following rows are closest to the cluster centroids\n{to_simulate}")

    # Create the directories for each interval we want to simulate in RTL simulation
    checkpoint_insts: List[int] = to_simulate["inst_start"].tolist()
    checkpoint_dir = cluster_dir / "checkpoints"
    checkpoint_dir.mkdir(exist_ok=True)
    checkpoints = [checkpoint_dir / f"0x80000000.{i}" for i in checkpoint_insts]
    for c in checkpoints:
        c.mkdir(exist_ok=True)

    # Construct MTR checkpoints for the L1d cache
    mtr_ckpts: Optional[List[MTR]] = None
    if args.cache_warmup:
        mtr_ckpts_exist = [(c / "mtr.pickle").exists() for c in checkpoints]
        if all(mtr_ckpts_exist):
            logging.info(f"MTR checkpoints already exist for each interval to simulate")
            mtr_ckpts = [load(c / "mtr.pickle") for c in checkpoints]
        else:
            logging.info(f"Generating MTR checkpoints at inst points {checkpoint_insts}")
            with spike_trace_file.open("r") as f:
                spike_trace_log = parse_spike_log(f, full_commit_log)
                mtr_ckpts = mtr_ckpts_from_inst_points(
                    spike_trace_log, block_size=64, inst_points=checkpoint_insts
                )
            for mtr_ckpt, ckpt_dir in zip(mtr_ckpts, checkpoints):
                dump(mtr_ckpt, ckpt_dir / "mtr.pickle")
                with (ckpt_dir / "mtr.pretty").open("w") as f:
                    pprint.pprint(mtr_ckpt, stream=f)

    # Capture arch checkpoints from spike
    # Cache this result if all the checkpoints are already available
    checkpoints_exist = [
        (c / "loadarch").exists() and (c / "mem.elf").exists() for c in checkpoints
    ]
    if all(checkpoints_exist):
        logging.info("Checkpoints already exist, not rerunning spike")
    else:
        logging.info("Generating arch checkpoints with spike")
        gen_checkpoints(
            binary,
            start_pc=0x8000_0000,
            inst_points=checkpoint_insts,
            ckpt_base_dir=checkpoint_dir,
            n_harts=n_harts,
            isa=isa,
        )

    # TODO: Reconstruct cache states using the MTR checkpoints and the memory bin files dumped from spike
    if args.cache_warmup:
        assert mtr_ckpts
        cache_params = CacheParams(phys_addr_bits=32, block_size_bytes=64, n_sets=64, n_ways=4)
        for mtr, ckpt_dir in zip(mtr_ckpts, checkpoints):
            cache_state: CacheState
            with (ckpt_dir / "mem.0x80000000.bin").open("rb") as f:
                cache_state = mtr.as_cache(cache_params, f, dram_base=0x8000_0000)
            cache_state.dump_data_arrays(ckpt_dir, "dcache_data_array")
            cache_state.dump_tag_arrays(ckpt_dir, "dcache_tag_array")

    # Run each checkpoint in RTL sim and extract perf metrics
    perf_files_exist = all([(c / "perf.csv").exists() for c in checkpoints])
    if perf_files_exist:
        logging.info(
            "Performance metrics for checkpoints already collected, skipping RTL simulation"
        )
    else:
        logging.info(
            "Running parallel RTL simulations to collect performance metrics for checkpoints"
        )

        def run_checkpoint_rtl_sim(checkpoint_dir: Path) -> None:
            run_rtl_sim(
                simulator=simulator,
                perf_file=(checkpoint_dir / "perf.csv"),
                perf_sample_period=int(args.interval_length / 10),
                max_instructions=args.interval_length,
                chipyard_root=chipyard_root,
                binary=(checkpoint_dir / "mem.elf"),
                loadarch=(checkpoint_dir / "loadarch"),
                suppress_exit=True,
                checkpoint_dir=(checkpoint_dir if args.cache_warmup else None),
                cwd=checkpoint_dir,
            )

        Parallel(n_jobs=-1)(
            delayed(run_checkpoint_rtl_sim)(checkpoint) for checkpoint in checkpoints
        )
