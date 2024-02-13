import pytest

from tidalsim.cache_model.cache import *
from tidalsim.cache_model.mtr import *
from tidalsim.util.spike_log import SpikeTraceEntry, SpikeCommitInfo, Op

class TestMTR:
    byte_offset_bits = 6
    block_size = 2**byte_offset_bits
    log = [
        SpikeTraceEntry(0x0, 'lw', 0, SpikeCommitInfo(address=0, data=0, op=Op.Load)),
        SpikeTraceEntry(0x4, 'lw', 1, SpikeCommitInfo(address=1, data=0, op=Op.Load)),
        SpikeTraceEntry(0x8, 'lw', 2, SpikeCommitInfo(address=2, data=0, op=Op.Load)),
        SpikeTraceEntry(0xc, 'sw', 3, SpikeCommitInfo(address=(1 << byte_offset_bits), data=0, op=Op.Store)),
        SpikeTraceEntry(0x10, 'sw', 4, SpikeCommitInfo(address=6, data=0, op=Op.Store)),
        SpikeTraceEntry(0x14, 'sw', 5, SpikeCommitInfo(address=(1 << byte_offset_bits)*2, data=0, op=Op.Store)),
    ]

    def test_mtr_ckpt_generation(self) -> None:
        mtr = MTR(block_size_bytes=self.block_size)
        log_iter = iter(self.log)
        new_mtr = mtr_ckpts_from_spike_log(log_iter, mtr, 3)
        assert new_mtr == MTR(block_size_bytes=self.block_size, table={
            0: MTREntry(2, None)
        })
        new_mtr = mtr_ckpts_from_spike_log(log_iter, new_mtr, 3)
        assert new_mtr == MTR(block_size_bytes=self.block_size, table={
            0: MTREntry(2, 4),
            1: MTREntry(None, 3),
            2: MTREntry(None, 5)
        })

    def test_mtr_ckpt_from_inst_points(self) -> None:
        mtr = MTR(block_size_bytes=self.block_size)
        log_iter = iter(self.log)
        mtr_ckpts = mtr_ckpts_from_inst_points(log_iter, self.block_size, [0, 3, 6])
        assert mtr_ckpts == [
            MTR(block_size_bytes=self.block_size, table={}),
            MTR(block_size_bytes=self.block_size, table={
                0: MTREntry(2, None)
            }),
            MTR(block_size_bytes=self.block_size, table={
                0: MTREntry(2, 4),
                1: MTREntry(None, 3),
                2: MTREntry(None, 5)
            })
        ]

    def test_mtr_cache_reconstruction_1_way(self) -> None:
        mtr = MTR(self.block_size, {
            # Map of block address -> MTREntry
            # Set 0
            0: MTREntry(10, 3),
            4: MTREntry(None, 5),
            8: MTREntry(11, 5),
            12: MTREntry(3, 9),
            # Set 1
            1: MTREntry(None, 4),
            # Set 3
            7: MTREntry(None, 8),
        })
        cache_params = CacheParams(32, self.block_size, n_sets=4, n_ways=1)
        cache = mtr.as_cache(cache_params)
        print(cache.array_pretty_str(Array.Tag))
        # cache[way_idx][set_idx]
        expected = {
            (0, 0): ((8 >> cache_params.set_bits), CohStatus.Dirty),
            (0, 1): ((1 >> cache_params.set_bits), CohStatus.Dirty),
            (0, 2): (0, CohStatus.Nothing),
            (0, 3): ((7 >> cache_params.set_bits), CohStatus.Dirty)
        }
        for ((way_idx, set_idx), (tag, coh)) in expected.items():
            block = cache.array[way_idx][set_idx]
            assert block.tag == tag
            assert block.coherency == coh

    # TODO: test 2+ ways
