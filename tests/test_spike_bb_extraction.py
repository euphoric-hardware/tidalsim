import pytest

from tidalsim.bb.spike import *

class TestSpikeBBExtraction:
    def test_parse_spike_log(self) -> None:
        lines = """core   0: 0x0000000080000104 (0x30529073) csrw    mtvec, t0
core   0: 0x0000000080000108 (0x169010ef) jal     pc + 0x1968
core   0: >>>>  __init_tls
core   0: 0x0000000080001a70 (0x00001141) c.addi  sp, -16
core   0: 0x0000000080001a72 (0x00000613) li      a2, 0""".split('\n')
        result = list(parse_spike_log(iter(lines)))
        assert result == [
            SpikeTraceEntry(0x8000_0104, "csrw"),
            SpikeTraceEntry(0x8000_0108, "jal"),
            SpikeTraceEntry(0x8000_1a70, "c.addi"),
            SpikeTraceEntry(0x8000_1a72, "li"),
        ]

    def test_spike_log_ignore_bootrom(self) -> None:
        lines="""core   0: 0x0000000000001000 (0x00000297) auipc   t0, 0x0
core   0: 0x0000000000001004 (0x02028593) addi    a1, t0, 32
core   0: 0x0000000000001008 (0xf1402573) csrr    a0, mhartid
core   0: 0x000000000000100c (0x0182b283) ld      t0, 24(t0)
core   0: 0x0000000000001010 (0x00028067) jr      t0
core   0: >>>>  _start
core   0: 0x0000000080000000 (0x00004081) c.li    ra, 0
core   0: 0x0000000080000002 (0x00004101) c.li    sp, 0""".split('\n')
        result = list(parse_spike_log(iter(lines)))
        assert result == [
            SpikeTraceEntry(0x8000_0000, "c.li"),
            SpikeTraceEntry(0x8000_0002, "c.li"),
        ]

    def test_single_large_block_bbs(self) -> None:
        # A single large block
        result = spike_trace_to_bbs(iter([
            SpikeTraceEntry(0x4, "c.addi"),
            SpikeTraceEntry(0x6, "c.addi"),
            SpikeTraceEntry(0x8, "li"),
            SpikeTraceEntry(0xc, "jal"),
        ]))
        assert result == BasicBlocks(markers=[(0x4, 0), (0xd, None)])
        assert result.pc_to_bb_id(0x4) == result.pc_to_bb_id(0x8)
        assert not result.pc_to_bb_id(0xe)
        assert not result.pc_to_bb_id(0x10)

    def test_two_blocks_bbs(self) -> None:
        # Two blocks
        result = spike_trace_to_bbs(iter([
            SpikeTraceEntry(0x4, "li"),
            SpikeTraceEntry(0x8, "li"),
            SpikeTraceEntry(0xc, "jal"),
            SpikeTraceEntry(0x20, "add"),
            SpikeTraceEntry(0x24, "add"),
        ]))
        assert result == BasicBlocks(markers=[
            (0x4, 0),
            (0xc+1, None),
            (0x20, 1),
            (0x24+1, None),
        ])
        assert result.pc_to_bb_id(0x8) == 0
        assert result.pc_to_bb_id(0x10) == None # Note 2 is not a real basic block, since it's empty dead space
        assert result.pc_to_bb_id(0x20) == 1
        assert result.pc_to_bb_id(0x24) == 1
        assert result.pc_to_bb_id(0x26) == None

    def test_block_splitting(self) -> None:
        # Splitting larger blocks into smaller ones
        result = spike_trace_to_bbs(iter([
            SpikeTraceEntry(0x4, "li"), # Initially a single block from 0x4-0xc
            SpikeTraceEntry(0x8, "li"),
            SpikeTraceEntry(0xc, "jal"),
            SpikeTraceEntry(0x20, "add"), # The second block from 0x20-0x28
            SpikeTraceEntry(0x24, "add"),
            SpikeTraceEntry(0x28, "beq"),
            SpikeTraceEntry(0x8, "li"), # The first block is now split into 2
            SpikeTraceEntry(0xc, "jal"),
            SpikeTraceEntry(0x20, "add"),
            SpikeTraceEntry(0x24, "add"),
            SpikeTraceEntry(0x28, "beq"),
        ]))
        assert result == BasicBlocks(markers=[
            (0x4, 0),
            (0x8, 1),
            (0xc+1, None),
            (0x20, 2),
            (0x28+1, None),
        ])

    def test_single_inst_bb(self) -> None:
        # Basic block that is just one instruction
        result = spike_trace_to_bbs(iter([
            SpikeTraceEntry(0x4, "li"),
            SpikeTraceEntry(0x8, "li"),
            SpikeTraceEntry(0xc, "jal"),
            SpikeTraceEntry(0x20, "jal"), # This instruction is one basic block alone
            SpikeTraceEntry(0x30, "add"),
            SpikeTraceEntry(0x34, "sub"),
        ]))
        assert result == BasicBlocks(markers=[
            (0x4, 0),
            (0xc+1, None),
            (0x20, 1),
            (0x20+1, None),
            (0x30, 2),
            (0x34+1, None),
        ])

    # Instructions that are control insts (branches or immediate jumps) but don't cause PC divergence
    def test_immediate_jumps(self) -> None:
        # Jumps that jump to PC + 4 don't cause PC breaks but are the end of the current basic block
        result = spike_trace_to_bbs(iter([
            SpikeTraceEntry(0x4, "li"),
            SpikeTraceEntry(0x8, "li"),
            SpikeTraceEntry(0xc, "jal"), # Jumps to PC + 4, but technically creates a new basic block
            SpikeTraceEntry(0x10, "add"),
            SpikeTraceEntry(0x14, "add"),
        ]))
        assert result == BasicBlocks(markers=[
            (0x4, 0),
            (0xc+1, None),
            (0x10, 1),
            (0x14+1, None),
        ])

    def test_uncaught_control_insts(self) -> None:
        with pytest.raises(RuntimeError):
            spike_trace_to_bbs(iter([
                SpikeTraceEntry(0x4, "li"),
                SpikeTraceEntry(0x8, "li"),
                SpikeTraceEntry(0xc, "???"),  # We saw a PC break, but not a known control instruction
                SpikeTraceEntry(0x14, "add"),
            ]))

    # TODO: Dealing with compressed instructions (are there any caveats here?)
