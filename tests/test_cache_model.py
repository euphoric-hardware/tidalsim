import pytest

from tidalsim.cache_model.cache import *

class TestCacheModel:
    params = CacheParams(phys_addr_bits=32, block_size_bytes=64, n_sets=64, n_ways=4)
    # params = CacheParams(phys_addr_bits=32, block_size_bytes=64, n_sets=8, n_ways=4)
    state = CacheState(params)
    state.fill_with_structured_data()

    def check_tag_bin_file(self, file_contents: List[str], way_idx: int) -> None:
        for set_idx in range(self.params.n_sets):
            assert (int(file_contents[set_idx], 2) & self.params.tag_mask) == self.state.array[way_idx][set_idx].tag

    # Run these using pytest -rA to show the printed arrays for manual inspection
    def test_tag_array_pretty_printing(self) -> None:
        s = self.state.array_pretty_str(Array.Tag)
        print(s)

    def test_tag_array_bin(self) -> None:
        for way_idx in range(self.params.n_ways):
            s = self.state.tag_array_binary_str(way_idx)
            s_split = s.split('\n')
            self.check_tag_bin_file(list(s.split('\n')), way_idx)
        print(self.state.tag_array_binary_str(0))

    def test_dump_tag_arrays(self, tmp_path: Path) -> None:
        prefix = "dcache_tag_array"
        self.state.dump_tag_arrays(tmp_path, prefix)
        assert (tmp_path / f"{prefix}.pretty").exists()
        for way_idx in range(self.params.n_ways):
            bin_file = tmp_path / f'{prefix}{way_idx}.bin'
            assert bin_file.exists()
            with bin_file.open('r') as f:
                lines = [line.rstrip() for line in f]
                self.check_tag_bin_file(lines, way_idx)

    def test_data_array_pretty_printing(self) -> None:
        s = self.state.array_pretty_str(Array.Data)
        print(s)

    def test_data_array_bin(self) -> None:
        data_bus_bytes = 8
        for way_idx in range(self.params.n_ways):
            s = self.state.data_array_binary_str(way_idx, data_bus_bytes)
            s_split = s.split('\n')
            for set_idx in range(self.params.n_sets):
                data_from_bin = s_split[data_bus_bytes*set_idx:data_bus_bytes*(set_idx+1)]
                assert int(''.join(reversed(data_from_bin)), 2) == self.state.array[way_idx][set_idx].data
        print(self.state.data_array_binary_str(way_idx=0, data_bus_bytes=data_bus_bytes))

    def test_dump_data_arrays(self, tmp_path: Path) -> None:
        prefix = "dcache_data_array"
        self.state.dump_data_arrays(tmp_path, prefix)
        assert (tmp_path / f"{prefix}.pretty").exists()
