from pathlib import Path
from typing import Tuple, List, cast
import logging

import numpy as np
import pandas as pd
from pandera.typing import DataFrame

from tidalsim.util.pickle import load
from tidalsim.modeling.schemas import *

def analyze_tidalsim_results(run_dir: Path, interval_length: int, clusters: int, elf: bool, detailed_warmup_insts: int) -> DataFrame[EstimatedPerfSchema]:
    interval_dir = run_dir / f"n_{interval_length}_{'elf' if elf else 'spike'}"
    cluster_dir = interval_dir / f"c_{clusters}"

    clustering_df = load(cluster_dir / "clustering_df.pickle")
    simulated_points = clustering_df.loc[clustering_df['chosen_for_rtl_sim'] == True].groupby('cluster_id', as_index=False).nth(0).sort_values('cluster_id')
    ipcs = []
    for index, row in simulated_points.iterrows():
        perf_file = cluster_dir / "checkpoints" / f"0x80000000.{row['inst_count']}" / "perf.csv"
        perf_data = pd.read_csv(perf_file)
        perf_data['ipc'] = perf_data['instret'] / perf_data['cycles']
        perf_data['inst_count'] = np.cumsum(perf_data['instret'])
        # Find the first row where more than [detailed_warmup_insts] have elapsed, and only begin tracking IPC from that row onwards
        # mypy can't infer the type of [start_point] correctly
        start_point = (perf_data['inst_count'] > detailed_warmup_insts).idxmax()
        ipc = np.nanmean(perf_data[start_point:]['ipc'])
        ipcs.append(ipc)

    estimated_perf_df: DataFrame[EstimatedPerfSchema] = clustering_df.assign(
        est_ipc = np.array(ipcs)[clustering_df['cluster_id']],
        est_cycles = lambda x: np.round(x['instret'] * np.reciprocal(x['est_ipc']))
    )
    return estimated_perf_df

def parse_golden_perf(perf_csv: Path) -> DataFrame[GoldenPerfSchema]:
    perf_data = pd.read_csv(perf_csv)
    golden_perf_df = perf_data.assign(
        ipc = lambda x: x['instret'] / x['cycles'],
        inst_count = lambda x: np.cumsum(x['instret'].to_numpy())
    )
    return golden_perf_df
