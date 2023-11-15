import argparse
from pathlib import Path
import logging

import pandas as pd

from tidalsim.util.cli import run_cmd, run_cmd_capture, run_cmd_pipe
from tidalsim.util.spike_ckpt import *
from tidalsim.bb.spike import parse_spike_log, spike_trace_to_bbs, spike_trace_to_bbvs, BasicBlocks
from tidalsim.util.pickle import dump, load
from tidalsim.modeling.clustering import *

def main():
    logging.basicConfig(format='%(levelname)s - %(filename)s:%(lineno)d - %(message)s', level=logging.INFO)

    parser = argparse.ArgumentParser(
                    prog='analyze',
                    description='Analyze the results from a sampled simulation run')
    parser.add_argument('--run-dir', type=str, required=True, help='Directory in which tidalsim results are stored')
    parser.add_argument('-n', '--interval-length', type=int, required=True, help='The interval length to analyze')
    parser.add_argument('-c', '--clusters', type=int, required=True, help='The number of clusters to analyze')
    parser.add_argument('--reference-perf-csv', type=str, required=False, help='A reference perf csv file to compare the extrapolated trace against')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    args = parser.parse_args()

    # Parse args
    run_dir = Path(args.run_dir).resolve()
    cwd = Path.cwd()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    logging.info(f"""Analyze called with:
    run_dir = {run_dir}
    interval_length = {args.interval_length}
    clusters = {args.clusters}""")
