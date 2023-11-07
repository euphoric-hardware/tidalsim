import pytest

from tidalsim.util.spike_ckpt import *

class TestSpikeCkpt:
    def test_dump_cmds(self) -> None:
        cmds = arch_state_dump_cmds(2)
        print(cmds)

    def test_n_insts_to_inst_steps(self) -> None:
        assert n_insts_to_inst_steps([100, 1000, 2000]) == [100, 900, 1000]
        assert n_insts_to_inst_steps([100]) == [100]
        with pytest.raises(Exception):
            n_insts_to_inst_steps([100, 1000, 900]) == [100, 900, 1000]
