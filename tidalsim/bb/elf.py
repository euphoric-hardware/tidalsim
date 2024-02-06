from intervaltree import Interval, IntervalTree
from dataclasses import dataclass
from typing import List, Optional, Tuple, Match, TextIO
from itertools import count
from tqdm import tqdm
import re
import sys
import logging

from tidalsim.bb.common import BasicBlocks
from tidalsim.util.spike_log import control_insts, no_target_insts

# Match leading zeros, capture addr, match horizontal whitespace, capture <name> of fn, :, a bunch of chars, newline
function_header_pattern = re.compile(r"^0*(?P<addr>[0-9a-f]+)[^\S\r\n]+(?P<name><\S+>):.*\n$")

# Match leading horizontal whitespace, capture addr, match  :, match horizontal whitespace, capture instr bits, match horizontal whitespace, capture riscv instr, match horizontal whitespace, capture args+potential target info, newline
instruction_pattern = re.compile(r"^[^\S\r\n]+(?P<addr>[0-9a-f]+):[^\S\r\n]+(?P<instr_bits>[0-9a-f]+)[^\S\r\n]+(?P<instr>[A-Za-z.]+)[^\S\r\n]*(?P<potential_info>.*)\n$")

# Match 0 or more registers, capture target, match horizontal whitespace, capture any annotation
target_pattern = re.compile(r"(?:[a-z0-9]{2},){0,}(?P<target>[a-z0-9]+)[^\S\r\n]*(?P<annotation><\S+>)")


@dataclass
class ObjdumpInstrEntry:
    pc: int
    instr_bits: str
    instr: str
    target: Optional[int] = None
    annotation: Optional[str] = None

next_bbid = count(start=0, step=1).__next__

def get_next_pc(instr: ObjdumpInstrEntry) -> int:
    increment = len(instr.instr_bits)//2
    return instr.pc + increment

def parseFile(f: TextIO) -> Tuple[List[ObjdumpInstrEntry], IntervalTree]:

    basic_blocks = IntervalTree()
    all_control_instrs = []
    no_target_identified = 0

    def find_next_func(f: TextIO) -> Optional[int]:
        while l := f.readline():
            match = function_header_pattern.match(l)
            if match is not None:
                logging.info(f"{match.group('addr')}\t{match.group('name')}")
                pc = int(match.group('addr'), 16)
                return pc
        return None

    def parse_func(f: TextIO)-> int:
        last_instr = None

        while l := f.readline():
            match = instruction_pattern.match(l)
            if match is not None:
                last_instr = parse_instr(match)
            else:
                assert last_instr, f"function contains no instr on line {l}"
                return get_next_pc(last_instr)

        logging.info("Reached EOF")
        assert last_instr, f"function contains no instr on line {l}"
        return get_next_pc(last_instr)

    def parse_instr(match: Match) -> ObjdumpInstrEntry:
        if match.group('instr') in control_insts:
            target, annotation = get_target_from_control_instr(match)
            instr_entry = ObjdumpInstrEntry(pc = int(match.group('addr'), 16), \
                    instr_bits = match.group('instr_bits'), \
                    instr = match.group('instr'), \
                    target = target, \
                    annotation = annotation)
            all_control_instrs.append(instr_entry)
            return instr_entry
        else:
            return ObjdumpInstrEntry(pc = int(match.group('addr'), 16), \
                    instr_bits = match.group('instr_bits'), \
                    instr = match.group('instr'))


    def get_target_from_control_instr(match: Match) -> Tuple[Optional[int], Optional[str]]:
        nonlocal no_target_identified
        instr = match.group('instr')
        potential_info = match.group('potential_info')

        if instr in no_target_insts:
            no_target_identified += 1
            logging.debug(f"NOTE: dynamic jump\t{match.groups()}")
            anno_match = re.search("(<\S+>)", potential_info)
            if anno_match is not None:
                logging.info(f"NOTE: found an annotation\t{anno_match.group(1)} in \t{match.groups()}")
                return None, anno_match.group(1)

        else:
            target_match =  target_pattern.search(potential_info)
            if target_match is None:
                no_target_identified += 1
                logging.error(f"Can't identify target\t{match.groups()}")
            else:
                return int(target_match.group('target'), 16), target_match.group('annotation')

        return (None, None)

    while func_start_pc := find_next_func(f):
        func_end_pc = parse_func(f)
        basic_blocks.add(Interval(func_start_pc, func_end_pc, next_bbid()))

    logging.info(f"Found {len(all_control_instrs)} control instructions")
    logging.info(f"No target was identified for {no_target_identified} instructions")

    return all_control_instrs, basic_blocks

def get_split_bbid(iv: Interval, islower: bool) -> int:
    if islower:
        return iv.data
    else:
        return next_bbid()

# Splitting logic
def do_basic_block_analysis(all_control_instrs: List[ObjdumpInstrEntry], initial_basic_blocks: IntervalTree) -> IntervalTree:

    all_basic_blocks = initial_basic_blocks

    def start_block_at(pc: int) -> None:
        all_basic_blocks.slice(pc, get_split_bbid)

    def end_block_after(control_instr: ObjdumpInstrEntry) -> None:
        all_basic_blocks.slice(get_next_pc(control_instr), get_split_bbid)

    for control_instr in tqdm(all_control_instrs):
        if control_instr.target is None:
            end_block_after(control_instr)
            logging.debug(f"Handled dynamic jump by ending basic block at {control_instr.pc}")
        else:
            end_block_after(control_instr)
            start_block_at(control_instr.target)
            logging.debug(f"Handled {control_instr}")

    return all_basic_blocks

def objdump_to_bbs(f: TextIO) -> BasicBlocks:
    all_control_instrs, inital_basic_blocks = parseFile(f)
    final_basic_blocks = do_basic_block_analysis(all_control_instrs, inital_basic_blocks)
    return BasicBlocks(pc_to_bb_id=final_basic_blocks)
