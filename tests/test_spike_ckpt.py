from tidalsim.util.spike_ckpt import arch_state_dump_cmds

class TestSpikeCkpt:
    def test_dump_cmds(self) -> None:
        cmds = arch_state_dump_cmds(2)
        print(cmds)
