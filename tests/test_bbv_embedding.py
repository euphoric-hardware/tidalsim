import pytest
from intervaltree import IntervalTree, Interval

from tidalsim.bb.spike import *

class TestBBVEmbedding:
    def test_embedding(self) -> None:
        trace = [
            SpikeTraceEntry(0x4, ""),
            SpikeTraceEntry(0x8, ""),
            SpikeTraceEntry(0xc, ""),
            SpikeTraceEntry(0x10, ""),
            SpikeTraceEntry(0x18, ""),
        ]
        extracted_bb = BasicBlocks(
            IntervalTree([Interval(0, 0x8+1, 0), Interval(0xc, 0x18+1, 1)])
        )
        matrix = spike_trace_to_bbvs(iter(trace), extracted_bb, 2)
        ref = np.array(
            [[2, 0], [0, 2], [0, 1]]
        , dtype=np.float64)
        assert (matrix == ref).all()
