import pytest
from pathlib import Path

from tidalsim.util.cli import run_rtl_sim_cmd


class TestUtilCli:
    def test_run_rtl_sim_cmd(self, tmp_path: Path) -> None:
        cmd = run_rtl_sim_cmd(
            simulator=(tmp_path / "simulator"),
            perf_file=(tmp_path / "perf.csv"),
            perf_sample_period=1000,
            max_instructions=None,
            chipyard_root=tmp_path,
            binary=(tmp_path / "binary"),
            loadarch=(tmp_path / "loadarch"),
            suppress_exit=True,
            checkpoint_dir=tmp_path,
            timeout_cycles=5000
        )
        print(cmd)
