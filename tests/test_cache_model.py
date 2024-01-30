import pytest

from tidalsim.cache_model.cache import *

class TestCacheModel:
    # Run these using pytest -rA to show the printed arrays for manual inspection
    def test_tag_array_pretty_printing(self) -> None:
        params = CacheParams(phys_addr_bits=32, block_size_bytes=64, n_sets=64, n_ways=4)
        # params = CacheParams(phys_addr_bits=32, block_size_bytes=64, n_sets=8, n_ways=4)
        state = CacheState(params)
        state.fill_with_structured_data()
        s = state.tag_array_pretty_str()
        print(state.params)
        print(s)

    def test_tag_array_bin(self) -> None:
        params = CacheParams(phys_addr_bits=32, block_size_bytes=64, n_sets=64, n_ways=4)
        state = CacheState(params)
        state.fill_with_structured_data()
        print(state.tag_array_binary_str(0))

    def test_dump_tag_arrays(self, tmp_path: Path) -> None:
        params = CacheParams(phys_addr_bits=32, block_size_bytes=64, n_sets=64, n_ways=4)
        state = CacheState(params)
        state.fill_with_structured_data()
        state.dump_tag_arrays(tmp_path, prefix="mem_0_")
