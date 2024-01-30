import argparse
from pathlib import Path
import logging
from typing import Iterator
from enum import Enum
import functools

import numpy as np

from tidalsim.cache_model.cache import *

def main():
    logging.basicConfig(format='%(levelname)s - %(filename)s:%(lineno)d - %(message)s', level=logging.INFO)

    parser = argparse.ArgumentParser(
                    prog='gen-cache-state',
                    description='Dump Dcache tag and data arrays filled with dummy data')
    parser.add_argument('--phys-addr-bits', type=int, default=32, help='Number of physical address bits')
    parser.add_argument('--block-size', type=int, default=64, help='Block size in bytes')
    parser.add_argument('--n-sets', type=int, default=64, help='Number of sets')
    parser.add_argument('--n-ways', type=int, default=4, help='Number of ways')
    parser.add_argument('--dir', type=str, required=True, help='Directory in which to dump things')
    args = parser.parse_args()
    data_dir = Path(args.dir)
    data_dir.mkdir(exist_ok=True)

    params = CacheParams(args.phys_addr_bits, args.block_size, args.n_sets, args.n_ways)
    state = CacheState(params)
    state.fill_with_structured_data()
    state.dump_tag_arrays(data_dir, "dcache_tag_array")
