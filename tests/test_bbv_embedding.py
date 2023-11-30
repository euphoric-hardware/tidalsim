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
            SpikeTraceEntry(0x4, ""),
            SpikeTraceEntry(0x8, ""),
        ]
        extracted_bb = BasicBlocks(
            IntervalTree([Interval(0, 0x8+1, 0), Interval(0xc, 0x18+1, 1)])
        )
        df = spike_trace_to_bbvs(iter(trace), extracted_bb, 2)
        ref = DataFrame[EmbeddingSchema]({
            'instret': [2, 2, 2, 1],
            'embedding': [
                np.array([1., 0.]),
                np.array([0., 1.]),
                np.array([0.5, 0.5]),
                np.array([1., 0.])
            ],
            'inst_count': [2, 4, 6, 7]
        })
        assert ref.equals(df)
