from pathlib import Path
from typing import Tuple, List
import logging

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from tidalsim.util.pickle import load

def analyze_tidalsim_results(run_dir: Path, interval_length: int, clusters: int) -> Tuple[np.ndarray, np.ndarray]:
    interval_dir = run_dir / f"n_{interval_length}"
    cluster_dir = interval_dir / f"c_{clusters}"

    kmeans_model_file = cluster_dir / "kmeans.model"
    kmeans_model: KMeans
    checkpoint_idxs: np.ndarray
    checkpoint_insts: List[int]
    kmeans_model, checkpoint_idxs, checkpoint_insts = load(kmeans_model_file)

    # For every centroid, get its IPC
    perf_files = [cluster_dir / "checkpoints" / f"0x80000000.{x*interval_length}" / "perf.csv" for x in checkpoint_idxs]
    sample_ipc = []
    for perf_file in perf_files:
        perf_data = pd.read_csv(perf_file)
        # Skip the first perf metric sample
        # TODO: generalize this with a detailed warmup argument specified in terms of instructions
        ipc = np.nanmean(perf_data['instret'][1:] / perf_data['cycles'][1:])
        sample_ipc.append(ipc)
    logging.info(f"IPC for each centroid: {sample_ipc}")

    # Reconstruct the IPC trace of the entire program
    labels = kmeans_model.labels_ # each label maps an interval in the full program trace to its cluster
    x = np.empty(len(labels)*2)
    y = np.empty(len(labels)*2)
    i = 0
    inst = 0
    for label in labels:
        x[i] = inst
        x[i+1] = inst + interval_length - 1
        ipc = sample_ipc[label]
        y[i] = ipc
        y[i+1] = ipc
        i += 2
        inst += interval_length
    return x, y

def parse_reference_perf(perf_csv: Path) -> Tuple[np.ndarray, np.ndarray]:
    perf_data = pd.read_csv(perf_csv)
    x = np.empty(len(perf_data)*2)
    y = np.empty(len(perf_data)*2)
    i = 0
    inst = 0
    for cycles in perf_data['cycles']:
        gold_x.append(i)
        gold_y.append(1000 / cycles)
        gold_x.append(i+1000-1)
        gold_y.append(1000 / cycles)
        i = i + 1000
    return x, y
