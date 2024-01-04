from pathlib import Path
from typing import Tuple, List, cast, Tuple, Optional
import logging

import numpy as np
import pandas as pd
from pandera.typing import DataFrame

from tidalsim.util.pickle import load
from tidalsim.modeling.schemas import *

def analyze_tidalsim_results(run_dir: Path, interval_length: int, clusters: int, elf: bool, detailed_warmup_insts: int, interpolate_clusters: bool) -> Tuple[DataFrame[EstimatedPerfSchema], Optional[DataFrame[GoldenPerfSchema]]]:
    interval_dir = run_dir / f"n_{interval_length}_{'elf' if elf else 'spike'}"
    cluster_dir = interval_dir / f"c_{clusters}"

    clustering_df = load(cluster_dir / "clustering_df.pickle")
    simulated_points = clustering_df.loc[clustering_df['chosen_for_rtl_sim'] == True].groupby('cluster_id', as_index=False).nth(0).sort_values('cluster_id')
    ipcs = []
    for index, row in simulated_points.iterrows():
        perf_file = cluster_dir / "checkpoints" / f"0x80000000.{row['inst_start']}" / "perf.csv"
        perf_data = pd.read_csv(perf_file)
        perf_data['ipc'] = perf_data['instret'] / perf_data['cycles']
        perf_data['inst_count'] = np.cumsum(perf_data['instret'])
        # Find the first row where more than [detailed_warmup_insts] have elapsed, and only begin tracking IPC from that row onwards
        # mypy can't infer the type of [start_point] correctly
        start_point = (perf_data['inst_count'] > detailed_warmup_insts).idxmax()
        # mypy can't say that perf_data[start_point:] is a legal slice
        ipc: float = np.nanmean(perf_data[start_point:]['ipc'])  # type: ignore
        ipcs.append(ipc)

    if not interpolate_clusters:
        # If we don't interpolate, we just use the IPC of the simulated point for that cluster
        estimated_perf_df: DataFrame[EstimatedPerfSchema] = clustering_df.assign(
            est_ipc = np.array(ipcs)[clustering_df['cluster_id']],
            est_cycles = lambda x: np.round(x['instret'] * np.reciprocal(x['est_ipc']))
        )
    else:
        # If we do interpolate, we use a weighted (by inverse L2 norm) average of the IPCs of all simulated points
        kmeans_file = cluster_dir / "kmeans_model.pickle"
        kmeans = load(kmeans_file)

        # for all points, compute norms to all centroids and store as separate vecs
        norms: np.ndarray = clustering_df['embedding'].apply(lambda s: np.linalg.norm(kmeans.cluster_centers_ - s, axis=1))
        # combine vecs to speed up computation
        norms = np.stack(norms)
        # invert to weight closer points heigher, and normalize vecs to sum to 1
        norms = 1 / norms
        weight_vecs = norms / norms.sum(axis=1, keepdims=True)
        # multiply weight vecs by ips to get weighted average
        est_ipc = weight_vecs @ np.array(ipcs)
        # assign to df
        estimated_perf_df: DataFrame[EstimatedPerfSchema] = clustering_df.assign(
            est_ipc = est_ipc,
            est_cycles = lambda x: np.round(x['instret'] * np.reciprocal(x['est_ipc']))
        )

    golden_perf_file = run_dir / "golden" / "perf.csv"
    if golden_perf_file.exists():
        golden_perf_df = parse_golden_perf(golden_perf_file)
        return estimated_perf_df, golden_perf_df
    else:
        return estimated_perf_df, None

def parse_golden_perf(perf_csv: Path) -> DataFrame[GoldenPerfSchema]:
    perf_data = pd.read_csv(perf_csv)
    golden_perf_df: DataFrame[GoldenPerfSchema] = perf_data.assign(
        ipc = lambda x: x['instret'] / x['cycles'],
        inst_count = lambda x: np.cumsum(x['instret'].to_numpy())
    ) # type: ignore
    return golden_perf_df
