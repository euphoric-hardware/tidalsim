import pytest
import numpy as np
from intervaltree import IntervalTree, Interval

from tidalsim.bb.spike import *

class TestBBVEmbedding:
    def test_embedding(self) -> None:
        trace = [
            SpikeTraceEntry(0x4,  "", 0),
            SpikeTraceEntry(0x8,  "", 1),
            SpikeTraceEntry(0xc,  "", 2),
            SpikeTraceEntry(0x10, "", 3),
            SpikeTraceEntry(0x18, "", 4),
            SpikeTraceEntry(0x4,  "", 5),
            SpikeTraceEntry(0x8,  "", 6),
        ]
        extracted_bb = BasicBlocks(
            IntervalTree([Interval(0, 0x8+1, 0), Interval(0xc, 0x18+1, 1)])
        )
        df = spike_trace_to_embedding_df(iter(trace), extracted_bb, 2)
        ref = DataFrame[EmbeddingSchema]({
            'instret': [2, 2, 2, 1],
            'inst_count': [2, 4, 6, 7],
            'inst_start': [0, 2, 4, 6],
            'embedding': [
                np.array([1., 0.]),
                np.array([0., 1.]),
                np.array([0.5, 0.5]),
                np.array([1., 0.])
            ]
        })
        # [spike_trace_to_embedding_df] returns the embedding already with unit L2 norm per row
        ref['embedding'] = ref['embedding'].transform(lambda x: x / np.linalg.norm(x))
        assert ref.equals(df)
