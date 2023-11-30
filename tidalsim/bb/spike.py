from typing import Iterator, List, Optional, Tuple
from dataclasses import dataclass
import functools

from intervaltree import IntervalTree, Interval
from tqdm import tqdm
import numpy as np
from more_itertools import ichunked
import pandas as pd
from pandera.typing import DataFrame

from tidalsim.bb.common import BasicBlocks, control_insts
from tidalsim.modeling.schemas import *

@dataclass
class SpikeTraceEntry:
    pc: int
    decoded_inst: str

def parse_spike_log(log_lines: Iterator[str]) -> Iterator[SpikeTraceEntry]:
    for line in log_lines:
        s = line.split()
        if s[2][0] == '>':
            # TODO: add the spike extracted section labels to SpikeTraceEntry
            continue
        else:
            # yield SpikeTraceEntry(int(s[2][2:], 16), int(s[3][3:-1], 16), s[4])
            yield SpikeTraceEntry(int(s[2][2:], 16), s[4])

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
        if trace_entry.decoded_inst in control_insts:
            intervals[start:trace_entry.pc + 1] = None # Intervals are inclusive of the start, but exclusive of the end
            start = None
        if previous_inst and (abs(trace_entry.pc - previous_inst.pc) > 4) and previous_inst.decoded_inst not in control_insts:
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

def spike_trace_to_bbvs(trace: Iterator[SpikeTraceEntry], bb: BasicBlocks, interval_length: int) -> DataFrame[EmbeddingSchema]:
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
    # For each interval, add the embedding and # of insts to the dataframe
    df_list: List[Tuple[int, np.ndarray]] = []
    for trace_interval in tqdm(trace_intervals):
        embedding, instret = embed_interval(trace_interval)
        # Normalize the embedding by the number of instructions in the interval
        df_list.append((instret, np.divide(embedding, instret)))
    df = DataFrame[EmbeddingSchema](df_list, columns=['instret', 'embedding'])
    return df
