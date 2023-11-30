from pathlib import Path
from typing import Tuple, List
import logging

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from tidalsim.util.pickle import load

def analyze_tidalsim_results(run_dir: Path, interval_length: int, clusters: int, elf: bool, detailed_warmup_insts: int) -> pd.DataFrame:
    interval_dir = run_dir / f"n_{interval_length}_{'elf' if elf else 'spike'}"
    cluster_dir = interval_dir / f"c_{clusters}"

    kmeans_model_file = cluster_dir / "kmeans.model"
    kmeans_model: KMeans
    checkpoint_idxs: np.ndarray
    checkpoint_insts: List[int]
    kmeans_model, checkpoint_idxs, checkpoint_insts = load(kmeans_model_file)

    # For every centroid, get its IPC
    perf_files = [cluster_dir / "checkpoints" / f"0x80000000.{x*interval_length}" / "perf.csv" for x in checkpoint_idxs]
    centroid_ipc = np.empty(len(perf_files))
    for i, perf_file in enumerate(perf_files):
        perf_data = pd.read_csv(perf_file)
        perf_data['ipc'] = perf_data['instret'] / perf_data['cycles']
        perf_data['inst_count'] = np.cumsum(perf_data['instret'].to_numpy())
        # Skip the first perf metric sample
        # TODO: generalize this with a detailed warmup argument specified in terms of instructions
        ipc = np.nanmean(perf_data['ipc'][1:])
        centroid_ipc[i] = ipc
    logging.info(f"IPC for each centroid: {centroid_ipc}")

    # Reconstruct the IPC trace of the entire program
    labels = kmeans_model.labels_ # each label maps an interval in the full program trace to its cluster
    perf_data = pd.DataFrame({'ipc' : centroid_ipc[labels], 'instret': np.repeat(interval_length, len(labels))})
    perf_data['inst_count'] = np.cumsum(perf_data['instret'].to_numpy())
    #perf_data_new = pd.DataFrame(np.repeat(perf_data.values, 2, axis=0))
    #perf_data_new.columns = perf_data.columns
    #perf_data_new['inst_count'][::2] = perf_data_new['inst_count'][::2]- interval_length
    return perf_data

def parse_reference_perf(perf_csv: Path, interval_length: int) -> pd.DataFrame:
    perf_data = pd.read_csv(perf_csv)
    perf_data['ipc'] = perf_data['instret'] / perf_data['cycles']
    perf_data['inst_count'] = np.cumsum(perf_data['instret'].to_numpy())
    perf_data_new = pd.DataFrame(np.repeat(perf_data.values, 2, axis=0))
    perf_data_new.columns = perf_data.columns
    perf_data_new['inst_count'][::2] = perf_data_new['inst_count'][::2]- interval_length
    return perf_data_new
