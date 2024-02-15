import pytest

from tidalsim.bb.spike import *

class TestSpikeBBExtraction:
    def test_single_large_block_bbs(self) -> None:
        # A single large block
        result = spike_trace_to_bbs(iter([
            SpikeTraceEntry(0x4, "c.addi", 0),
            SpikeTraceEntry(0x6, "c.addi", 1),
            SpikeTraceEntry(0x8, "li",     2),
            SpikeTraceEntry(0xc, "jal",    3),
        ]))
        assert result == BasicBlocks(markers=[(0x4, 0), (0xd, None)])
        assert result.pc_to_bb_id(0x4) == result.pc_to_bb_id(0x8)
        assert not result.pc_to_bb_id(0xe)
        assert not result.pc_to_bb_id(0x10)

    def test_two_blocks_bbs(self) -> None:
        # Two blocks
        result = spike_trace_to_bbs(iter([
            SpikeTraceEntry(0x4,  "li",  0),
            SpikeTraceEntry(0x8,  "li",  1),
            SpikeTraceEntry(0xc,  "jal", 2),
            SpikeTraceEntry(0x20, "add", 3),
            SpikeTraceEntry(0x24, "add", 4),
        ]))
        assert result == BasicBlocks(markers=[
            (0x4, 0),
            (0xc+1, None),
            (0x20, 1),
            (0x24+1, None),
        ])
        assert result.pc_to_bb_id(0x8) == 0
        assert result.pc_to_bb_id(0xc) == 0
        assert result.pc_to_bb_id(0x10) == None
        assert result.pc_to_bb_id(0x20) == 1
        assert result.pc_to_bb_id(0x24) == 1
        assert result.pc_to_bb_id(0x26) == None

    def test_block_splitting(self) -> None:
        # Splitting larger blocks into smaller ones
        result = spike_trace_to_bbs(iter([
            SpikeTraceEntry(0x4,  "li",  0), # Initially a single block from 0x4-0xc
            SpikeTraceEntry(0x8,  "li",  1),
            SpikeTraceEntry(0xc,  "jal", 2),
            SpikeTraceEntry(0x20, "add", 3), # The second block from 0x20-0x28
            SpikeTraceEntry(0x24, "add", 4),
            SpikeTraceEntry(0x28, "beq", 5),
            SpikeTraceEntry(0x8,  "li",  6), # The first block is now split into 2
            SpikeTraceEntry(0xc,  "jal", 7),
            SpikeTraceEntry(0x20, "add", 8),
            SpikeTraceEntry(0x24, "add", 9),
            SpikeTraceEntry(0x28, "beq", 10),
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
            SpikeTraceEntry(0x4,  "li",  0),
            SpikeTraceEntry(0x8,  "li",  1),
            SpikeTraceEntry(0xc,  "jal", 2),
            SpikeTraceEntry(0x20, "jal", 3), # This instruction is one basic block alone
            SpikeTraceEntry(0x30, "add", 4),
            SpikeTraceEntry(0x34, "sub", 5),
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
            SpikeTraceEntry(0x4,  "li",  0),
            SpikeTraceEntry(0x8,  "li",  1),
            SpikeTraceEntry(0xc,  "jal", 2), # Jumps to PC + 4, but technically creates a new basic block
            SpikeTraceEntry(0x10, "add", 3),
            SpikeTraceEntry(0x14, "add", 4),
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
                SpikeTraceEntry(0x4,  "li",  0),
                SpikeTraceEntry(0x8,  "li",  1),
                SpikeTraceEntry(0xc,  "???", 2),  # We saw a PC break, but not a known control instruction
                SpikeTraceEntry(0x14, "add", 3),
            ]))

    # TODO: Dealing with compressed instructions (are there any caveats here?)
