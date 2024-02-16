import time
from pathlib import Path
from tidalsim.bb.spike import spike_trace_to_bbs
from tidalsim.util.spike_log import parse_spike_log
import sys

def main():
    if len(sys.argv) < 2:
        raise RuntimeError("Usage: bench-spike-bb-extraction <path to spike log>")
    with Path(sys.argv[1]).open('r') as f:
        lines = list(f)
        for i in range(10):
            parse_start = time.time()
            spike_trace_log = list(parse_spike_log(lines, False))
            parse_end = time.time()

            bb_build_start = time.time()
            bb = spike_trace_to_bbs(spike_trace_log)
            bb_build_end = time.time()

            bb_query_start = time.time()
            for entry in spike_trace_log:
                bb.pc_to_bb_id(entry.pc)
            bb_query_end = time.time()

            print("parse:", parse_end - parse_start)
            print("bb build:", bb_build_end - bb_build_start)
            print("bb query:", bb_query_end - bb_query_start)
