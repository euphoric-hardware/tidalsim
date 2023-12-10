import argparse
from pathlib import Path
import logging

import numpy as np

def main():
    logging.basicConfig(format='%(levelname)s - %(filename)s:%(lineno)d - %(message)s', level=logging.INFO)

    def clog2(x):
        """Ceiling of log2"""
        if x <= 0:
            raise ValueError("domain error")
        return (x-1).bit_length()

    parser = argparse.ArgumentParser(
                    prog='gen-cache-state',
                    description='Dump an example Dcache tag array')
    parser.add_argument('--phys-addr-bits', type=int, default=32, help='Number of physical address bits')
    parser.add_argument('--block-size', type=int, default=64, help='Block size in bytes')
    parser.add_argument('--n-sets', type=int, default=64, help='Number of sets')
    parser.add_argument('--cache-size', type=int, default=16384, help='Total cache size in bytes')
    args = parser.parse_args()

    ways = int(args.cache_size / (args.n_sets * args.block_size))
    assert ways == 4
    offset_bits = clog2(args.block_size)
    set_bits = clog2(args.n_sets)
    raw_tag_bits = args.phys_addr_bits - set_bits - offset_bits
    assert raw_tag_bits == 20
    tag_bits = raw_tag_bits + 2  # 2 bits for coherency metadata
    assert tag_bits == 22

    # Construct a tag array for each way
    tag_array = [np.zeros(args.n_sets, dtype=np.uint32) for _ in range(ways)]

    for way_idx, way in enumerate(tag_array):
        for i in range(len(way)):
            way[i] = 0x8000_0 + way_idx*args.n_sets + i

    # Print ways and sets in reverse order
    for set_idx in reversed(range(args.n_sets)):
        for way_idx in reversed(range(ways)):
            raw_tag = tag_array[way_idx][set_idx]
            full_tag = (0b11 << raw_tag_bits) | raw_tag  # simulate 'dirty' bits being set
            full_tag_formatted = f'{{:0{tag_bits}b}}'.format(full_tag)
            print(full_tag_formatted, end="")
        print("")
