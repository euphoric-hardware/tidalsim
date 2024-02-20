import pytest

from tidalsim.util.spike_ckpt import *


class TestSpikeCkpt:
    def test_get_spike_cmd(self) -> None:
        assert (
            get_spike_cmd(
                Path.cwd(),
                1,
                "rv64gc",
                Path.cwd() / "cmds.txt",
                inst_log=True,
                commit_log=True,
                suppress_exit=True,
            )
            == f"spike -d --debug-cmd={Path.cwd() / 'cmds.txt'} -p1 --pmpregions=0 --isa=rv64gc"
            f" -m{0x8000_0000}:{0x1000_0000} -l --log-commits +suppress-exit"
            f" {Path.cwd().resolve()}"
        )

    def test_reg_dump(self) -> None:
        cmd_block = reg_dump(0)
        assert "pc 0" in cmd_block.cmds
        assert "mtime" in cmd_block.cmds
        assert "reg 0 31" in cmd_block.cmds
        assert "freg 0 31" in cmd_block.cmds

    def test_arch_state_dump(self) -> None:
        cmd_block = arch_state_dump(2, Path.cwd() / "mem")
        assert f"dump {(Path.cwd() / 'mem').resolve()}" in cmd_block.cmds
        assert "reg 0 31" in cmd_block.cmds
        assert "reg 1 31" in cmd_block.cmds

    def test_inst_points_dump(self) -> None:
        cmd_block = inst_points_dump(
            0x8000_0000, [100, 2000, 3000], n_harts=1, ckpt_base_dir=Path.cwd()
        )
        assert "until pc 0 0x80000000" in cmd_block.cmds
        assert "rs 100" in cmd_block.cmds
        assert "rs 1900" in cmd_block.cmds
        assert "rs 1000" in cmd_block.cmds
        assert f"dump {Path.cwd() / '0x80000000.100'}" in cmd_block.cmds
        assert f"dump {Path.cwd() / '0x80000000.2000'}" in cmd_block.cmds
        assert f"dump {Path.cwd() / '0x80000000.3000'}" in cmd_block.cmds
        assert cmd_block.cmds[-1] == "quit"

    def test_get_ckpt_dirs(self) -> None:
        dirs = get_ckpt_dirs(Path.cwd(), 0x8000_0000, [0, 100, 2000])
        assert dirs == [
            Path.cwd() / "0x80000000.0",
            Path.cwd() / "0x80000000.100",
            Path.cwd() / "0x80000000.2000",
        ]
