from typing import Iterator, List, Optional, Tuple
from dataclasses import dataclass
import functools

from intervaltree import IntervalTree, Interval
from tqdm import tqdm
import numpy as np
from more_itertools import ichunked
import pandas as pd
from pandera.typing import DataFrame
from sklearn.preprocessing import normalize

from tidalsim.util.spike_log import SpikeTraceEntry
from tidalsim.bb.common import BasicBlocks
from tidalsim.modeling.schemas import *


def spike_trace_to_bbs(trace: Iterator[SpikeTraceEntry]) -> BasicBlocks:
    # Make initial pass through the Spike dump
    # A new interval is recorded when the PC changes by more than 4
    # The end of the previous Interval is the PC that was jumped from
    # The start of the next Interval is the PC that was jumped to
    # No data is stored, speeds up the lookup significantly
    start = None
    previous_inst: Optional[SpikeTraceEntry] = None
    intervals = IntervalTree()
    for trace_entry in tqdm(trace):
        if start is None:
            start = trace_entry.pc
        if trace_entry.is_control_inst():
            intervals[start:trace_entry.pc + 1] = None # Intervals are inclusive of the start, but exclusive of the end
            start = None
        if previous_inst and (abs(trace_entry.pc - previous_inst.pc) > 4) and not previous_inst.is_control_inst():
            raise RuntimeError(f"Control diverged from PC: {hex(previous_inst.pc)} \
                    to PC: {hex(trace_entry.pc)}, but the last instruction {previous_inst.decoded_inst} \
                    wasn't a control instruction")
        previous_inst = trace_entry
    if start is not None and previous_inst is not None:
        intervals[start:previous_inst.pc+1] = None

    # Ensures that PCs have a one-to-one mapping to an interval
    intervals.merge_equals()
    intervals.split_overlaps()

    # Assign each interval an index in the BBV vector
    # Easier to just instantiate a new tree for lookup later
    id = 0
    unique_intervals = IntervalTree()
    for interval in sorted(intervals.items()):
        unique_intervals.addi(interval.begin, interval.end, id)
        id += 1
    return BasicBlocks(pc_to_bb_id=unique_intervals)

def spike_trace_to_embedding_df(trace: Iterator[SpikeTraceEntry], bb: BasicBlocks, interval_length: int) -> DataFrame[EmbeddingSchema]:
    # Dimensions of dataframe
    # # rows = # of intervals = ceil( (length of trace) / interval_length )
    # # cols = # of features = # of elements in the intervaltree
    n_features = len(bb.pc_to_bb_id)

    # Use a cache to avoid querying the interval tree too often, queries should have good locality
    @functools.lru_cache(maxsize=128)
    def lookup_id_from_pc(pc: int) -> int:
        return bb.pc_to_bb_id[pc].pop().data

    def embed_interval(interval: Iterator[SpikeTraceEntry]) -> Tuple[np.ndarray, int]:
        instret = 0
        embedding = np.zeros(n_features)
        for trace_entry in interval:
            bb_id = lookup_id_from_pc(trace_entry.pc)
            embedding[bb_id] += 1
            instret += 1
        return embedding, instret

    # Group the trace into intervals of [interval_length] instructions
    trace_intervals = ichunked(trace, interval_length)
    df_list: List[Tuple[int, int, int, np.ndarray]] = []
    total_inst_count = 0
    for trace_interval in tqdm(trace_intervals):
        embedding, instret = embed_interval(trace_interval)
        # Embed each basic block by the *fraction* of the interval that ran that basic block
        embedding = np.divide(embedding, instret)
        # Furthermore, make sure the embedding vector has unit L2 norm
        embedding = np.divide(embedding, np.linalg.norm(embedding))
        df_list.append((instret, total_inst_count + instret, total_inst_count, embedding))
        total_inst_count += instret
    df = DataFrame[EmbeddingSchema](df_list, columns=['instret', 'inst_count', 'inst_start', 'embedding'])
    return df
