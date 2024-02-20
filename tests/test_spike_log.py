import pytest

from tidalsim.util.spike_log import *


class TestSpikeLog:
    def test_parse_spike_log(self) -> None:
        lines = """core   0: 0x0000000080000104 (0x30529073) csrw    mtvec, t0
core   0: 0x0000000080000108 (0x169010ef) jal     pc + 0x1968
core   0: >>>>  __init_tls
core   0: 0x0000000080001a70 (0x00001141) c.addi  sp, -16
core   0: 0x0000000080001a72 (0x00000613) li      a2, 0""".split("\n")
        result = list(parse_spike_log(iter(lines), False))
        assert result == [
            SpikeTraceEntry(0x8000_0104, "csrw", 0),
            SpikeTraceEntry(0x8000_0108, "jal", 1),
            SpikeTraceEntry(0x8000_1A70, "c.addi", 2),
            SpikeTraceEntry(0x8000_1A72, "li", 3),
        ]

    def test_spike_log_ignore_bootrom(self) -> None:
        lines = """core   0: 0x0000000000001000 (0x00000297) auipc   t0, 0x0
core   0: 0x0000000000001004 (0x02028593) addi    a1, t0, 32
core   0: 0x0000000000001008 (0xf1402573) csrr    a0, mhartid
core   0: 0x000000000000100c (0x0182b283) ld      t0, 24(t0)
core   0: 0x0000000000001010 (0x00028067) jr      t0
core   0: >>>>  _start
core   0: 0x0000000080000000 (0x00004081) c.li    ra, 0
core   0: 0x0000000080000002 (0x00004101) c.li    sp, 0""".split("\n")
        result = list(parse_spike_log(iter(lines), False))
        assert result == [
            SpikeTraceEntry(0x8000_0000, "c.li", 0),
            SpikeTraceEntry(0x8000_0002, "c.li", 1),
        ]

    def test_spike_log_stores(self) -> None:
        lines = """core   0: 0x0000000080001a7e (0x00008512) c.mv    a0, tp
core   0: 3 0x0000000080001a7e (0x8512) x10 0x0000000080023000
core   0: 0x0000000080001a80 (0x0000e022) c.sdsp  s0, 0(sp)
core   0: 3 0x0000000080001a80 (0xe022) mem 0x000000008002aff0 0x0000000000000000
core   0: 0x0000000080001a82 (0x0000e406) c.sdsp  ra, 8(sp)
core   0: 3 0x0000000080001a82 (0xe406) mem 0x000000008002aff8 0x000000008000010c
core   0: 0x0000000080001a84 (0x00008412) c.mv    s0, tp
core   0: 3 0x0000000080001a84 (0x8412) x8  0x0000000080023000""".split("\n")
        result = list(parse_spike_log(iter(lines), True))
        assert result == [
            SpikeTraceEntry(0x8000_1A7E, "c.mv", 0, None),
            SpikeTraceEntry(0x8000_1A80, "c.sdsp", 1, SpikeCommitInfo(0x8002_AFF0, 0x0, Op.Store)),
            SpikeTraceEntry(
                0x8000_1A82, "c.sdsp", 2, SpikeCommitInfo(0x8002_AFF8, 0x8000_010C, Op.Store)
            ),
            SpikeTraceEntry(0x8000_1A84, "c.mv", 3, None),
        ]

    def test_spike_log_loads(self) -> None:
        lines = """core   0: 0x000000008000043e (0x8201b483) ld      s1, -2016(gp)
core   0: 3 0x000000008000043e (0x8201b483) x9  0x0000000080001f50 mem 0x0000000080002020
core   0: 0x0000000080000442 (0x0000589c) c.lw    a5, 48(s1)
core   0: 3 0x0000000080000442 (0x589c) x15 0x0000000000000001 mem 0x0000000080001f80""".split("\n")
        result = list(parse_spike_log(iter(lines), True))
        assert result == [
            SpikeTraceEntry(
                0x8000_043E, "ld", 0, SpikeCommitInfo(0x8000_2020, 0x8000_1F50, Op.Load)
            ),
            SpikeTraceEntry(0x8000_0442, "c.lw", 1, SpikeCommitInfo(0x8000_1F80, 0x1, Op.Load)),
        ]

    def test_spike_log_etc(self) -> None:
        # Other instructions should not have any commit info
        lines = """core   0: 0x0000000080000048 (0x09028293) addi    t0, t0, 144
core   0: 3 0x0000000080000048 (0x09028293) x5  0x00000000800000d4
core   0: 0x000000008000004c (0x30529073) csrw    mtvec, t0
core   0: 3 0x000000008000004c (0x30529073) c773_mtvec 0x00000000800000d4
core   0: 0x0000000080000050 (0x00301073) csrw    fcsr, zero
core   0: 3 0x0000000080000050 (0x00301073) c1_fflags 0x0000000000000000 c2_frm 0x0000000000000000""".split(
            "\n"
        )
        result = list(parse_spike_log(iter(lines), True))
        assert result == [
            SpikeTraceEntry(0x8000_0048, "addi", 0),
            SpikeTraceEntry(0x8000_004C, "csrw", 1),
            SpikeTraceEntry(0x8000_0050, "csrw", 2),
        ]

    def test_spike_log_disasm_labels(self) -> None:
        # A label between two instructions shouldn't break the parser
        lines = """core   0: 0x0000000000001008 (0xf1402573) csrr    a0, mhartid
core   0: 3 0x0000000000001008 (0xf1402573) x10 0x0000000000000000
core   0: 0x000000000000100c (0x0182b283) ld      t0, 24(t0)
core   0: 3 0x000000000000100c (0x0182b283) x5  0x0000000080000000 mem 0x0000000000001018
core   0: 0x0000000000001010 (0x00028067) jr      t0
core   0: 3 0x0000000000001010 (0x00028067)
core   0: >>>>  _start
core   0: 0x0000000080000000 (0x00004081) c.li    ra, 0
core   0: 3 0x0000000080000000 (0x4081) x1  0x0000000000000000
core   0: 0x0000000080000002 (0x00004101) c.li    sp, 0
core   0: 3 0x0000000080000002 (0x4101) x2  0x0000000000000000""".split("\n")
        result = list(parse_spike_log(iter(lines), True))
        assert result == [
            SpikeTraceEntry(0x8000_0000, "c.li", 0),
            SpikeTraceEntry(0x8000_0002, "c.li", 1),
        ]
