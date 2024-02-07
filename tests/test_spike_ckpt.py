import pytest

from tidalsim.util.spike_ckpt import *

class TestSpikeCkpt:
    def test_get_spike_cmd(self) -> None:
        assert get_spike_cmd(Path.cwd(), 1, 'rv64gc', Path.cwd() / "cmds.txt", inst_log=True, commit_log=True, suppress_exit=True) == \
                f"spike -d --debug-cmd={Path.cwd() / 'cmds.txt'} -p1 --pmpregions=0 --isa=rv64gc -m{0x8000_0000}:{0x1000_0000} -l --log-commits +suppress-exit {Path.cwd().resolve()}"

    def test_arch_state_dump_cmds(self) -> None:
        cmds = arch_state_dump_cmds(2, Path.cwd() / "mem")
        assert f"dump {(Path.cwd() / 'mem').resolve()}" in cmds
        assert "pc 0" in cmds
        assert "reg 0 31" in cmds

    def test_spike_cmds(self) -> None:
        cmds = spike_cmds(0x8000_0000, [100, 2000, 3000], 1, ckpt_base_dir=Path.cwd())
        assert f"until pc 0 0x80000000" in cmds
        assert "rs 100" in cmds
        assert "rs 1900" in cmds
        assert "rs 1000" in cmds
        assert f"dump {Path.cwd() / '0x80000000.100'}" in cmds
        assert f"dump {Path.cwd() / '0x80000000.2000'}" in cmds
        assert f"dump {Path.cwd() / '0x80000000.3000'}" in cmds
        assert cmds.split('\n')[-1] == "quit"

    def test_get_ckpt_dirs(self) -> None:
        dirs = get_ckpt_dirs(Path.cwd(), 0x8000_0000, [0, 100, 2000])
        assert dirs == [
            Path.cwd() / "0x80000000.0",
            Path.cwd() / "0x80000000.100",
            Path.cwd() / "0x80000000.2000",
        ]
