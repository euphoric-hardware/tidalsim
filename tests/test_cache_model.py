import pytest

from tidalsim.cache_model.cache import *

class TestCacheModel:
    params = CacheParams(phys_addr_bits=32, block_size_bytes=64, n_sets=64, n_ways=4)
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
            s = self.state.data_array_binary_str(way_idx)
            s_split = s.split('\n')
            for set_idx in range(self.params.n_sets):
                data_from_bin = s_split[data_bus_bytes*set_idx:data_bus_bytes*(set_idx+1)]
                assert int(''.join(reversed(data_from_bin)), 2) == self.state.array[way_idx][set_idx].data
        print(self.state.data_array_binary_str(way_idx=0))

    def test_dump_data_arrays(self, tmp_path: Path) -> None:
        prefix = "dcache_data_array"
        self.state.dump_data_arrays(tmp_path, prefix)
        assert (tmp_path / f"{prefix}.pretty").exists()

        bin_files = [(tmp_path / f"{prefix}{i}.bin") for i in range(self.params.data_bus_bytes * self.params.n_ways)]
        assert all([x.exists() for x in bin_files])

        # Read every .bin file into a list that's first indexed by byte # then row #
        bin_file_data: List[List[str]] = []
        for filename in bin_files:
            with filename.open('r') as f:
                lines = [line.rstrip() for line in f]
                bin_file_data.append(lines)
        assert len(bin_file_data) == self.params.data_bus_bytes * self.params.n_ways

        # Read a 'data_bus_bytes' row from a particular way
        def read_row(way_idx: int, row_idx: int) -> str:
            start = way_idx * self.params.data_bus_bytes
            end = start + self.params.data_bus_bytes
            row = [bin_file_data[byte_idx][row_idx] for byte_idx in range(start, end)]
            row_str = ''.join(reversed(row))
            return row_str

        # Get out the full data word for a set
        def read_set(way_idx: int, set_idx: int) -> int:
            set_data = [read_row(way_idx, set_idx*self.params.data_rows_per_set + beat) for beat in range(self.params.data_bus_bytes)]
            return int(''.join(reversed(set_data)), 2)

        for way_idx in range(self.params.n_ways):
            for set_idx in range(self.params.n_sets):
                assert read_set(way_idx, set_idx) == self.state.array[way_idx][set_idx].data
