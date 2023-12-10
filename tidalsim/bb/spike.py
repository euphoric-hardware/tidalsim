import re
from typing import Iterator, List, Optional, Tuple
from dataclasses import dataclass

from tqdm import tqdm
import numpy as np
from more_itertools import ichunked
from pandera.typing import DataFrame

from tidalsim.bb.common import BasicBlocks, control_insts, intervals_to_markers
from tidalsim.modeling.schemas import *

# Regex patterns to extract instructions or symbols from Spike dump
instruction_pattern = re.compile(r"core\s*\d: 0x(?P<pc>\w+) \((?P<inst>\w+)\)")
name_pattern = re.compile(r"core\s*\d:\s*>>>>\s*(?P<name>\w+)")

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
            pc = int(s[2][2:], 16)
            decoded_inst = s[4]
            # Ignore spike trace outside DRAM
            if pc < 0x8000_0000:
                continue
            else:
                yield SpikeTraceEntry(pc, decoded_inst)

def spike_trace_to_bbs(trace: Iterator[SpikeTraceEntry]) -> BasicBlocks:
    # Make initial pass through the Spike dump
    # A new interval is recorded when the PC changes by more than 4
    # The end of the previous Interval is the PC that was jumped from
    # The start of the next Interval is the PC that was jumped to
    # No data is stored, speeds up the lookup significantly
    start = None
    previous_inst: Optional[SpikeTraceEntry] = None
    intervals: List[Tuple[int, int]] = []
    for trace_entry in tqdm(trace):
        if start is None:
            start = trace_entry.pc
        if trace_entry.decoded_inst in control_insts:
            intervals += [(start, trace_entry.pc+1)] # Intervals are inclusive of the start, but exclusive of the end
            start = None
        if previous_inst and (abs(trace_entry.pc - previous_inst.pc) > 4) and previous_inst.decoded_inst not in control_insts:
            raise RuntimeError(f"Control diverged from PC: {hex(previous_inst.pc)} \
                    to PC: {hex(trace_entry.pc)}, but the last instruction {previous_inst.decoded_inst} \
                    wasn't a control instruction")
        previous_inst = trace_entry

    if start is not None and previous_inst is not None:
       intervals += [(start, previous_inst.pc+1)]

    return BasicBlocks(markers=intervals_to_markers(intervals))

def spike_trace_to_embedding_df(trace: Iterator[SpikeTraceEntry], bb: BasicBlocks, interval_length: int) -> DataFrame[EmbeddingSchema]:
    # Dimensions of dataframe
    # # rows = # of intervals = ceil( (length of trace) / interval_length )
    # # cols = # of features = # of elements in the intervaltree
    n_features = len(bb)

    def embed_interval(interval: Iterator[SpikeTraceEntry]) -> Tuple[np.ndarray, int]:
        instret = 0
        embedding = np.zeros(n_features)
        for trace_entry in interval:
            bb_id = bb.pc_to_bb_id(trace_entry.pc)
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
