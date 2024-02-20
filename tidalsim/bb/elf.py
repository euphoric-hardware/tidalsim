from dataclasses import dataclass
from typing import List, Optional, Tuple, Match, TextIO
from itertools import count
from tqdm import tqdm
import re
import logging

from tidalsim.bb.common import (
    Marker,
    control_insts,
    events_to_markers,
    intervals_to_events,
    no_target_insts,
    BasicBlocks,
    Interval,
)

# Match leading zeros, capture addr, match horizontal whitespace, capture <name> of fn, :, a bunch of chars, newline
function_header_pattern = re.compile(r"^0*(?P<addr>[0-9a-f]+)[^\S\r\n]+(?P<name><\S+>):.*\n$")

# Match leading horizontal whitespace, capture addr, match  :, match horizontal whitespace, capture instr bits, match horizontal whitespace, capture riscv instr, match horizontal whitespace, capture args+potential target info, newline
instruction_pattern = re.compile(
    r"^[^\S\r\n]+(?P<addr>[0-9a-f]+):[^\S\r\n]+(?P<instr_bits>[0-9a-f]+)[^\S\r\n]+(?P<instr>[A-Za-z.]+)[^\S\r\n]*(?P<potential_info>.*)\n$"
)

# Match 0 or more registers, capture target, match horizontal whitespace, capture any annotation
target_pattern = re.compile(
    r"(?:[a-z0-9]{2},){0,}(?P<target>[a-z0-9]+)[^\S\r\n]*(?P<annotation><\S+>)"
)


@dataclass
class ObjdumpInstrEntry:
    pc: int
    instr_bits: str
    instr: str
    target: Optional[int] = None
    annotation: Optional[str] = None


next_bbid = count(start=0, step=1).__next__


def get_next_pc(instr: ObjdumpInstrEntry) -> int:
    increment = len(instr.instr_bits) // 2
    return instr.pc + increment


def parseFile(f: TextIO) -> Tuple[List[ObjdumpInstrEntry], List[Tuple[int, int]]]:
    intervals = []
    all_control_instrs = []
    no_target_identified = 0

    def find_next_func(f: TextIO) -> Optional[int]:
        while l := f.readline():
            match = function_header_pattern.match(l)
            if match is not None:
                logging.info(f"{match.group('addr')}\t{match.group('name')}")
                pc = int(match.group("addr"), 16)
                return pc
        return None

    def parse_func(f: TextIO) -> int:
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
        if match.group("instr") in control_insts:
            target, annotation = get_target_from_control_instr(match)
            instr_entry = ObjdumpInstrEntry(
                pc=int(match.group("addr"), 16),
                instr_bits=match.group("instr_bits"),
                instr=match.group("instr"),
                target=target,
                annotation=annotation,
            )
            all_control_instrs.append(instr_entry)
            return instr_entry
        else:
            return ObjdumpInstrEntry(
                pc=int(match.group("addr"), 16),
                instr_bits=match.group("instr_bits"),
                instr=match.group("instr"),
            )

    def get_target_from_control_instr(match: Match) -> Tuple[Optional[int], Optional[str]]:
        nonlocal no_target_identified
        instr = match.group("instr")
        potential_info = match.group("potential_info")

        if instr in no_target_insts:
            no_target_identified += 1
            logging.debug(f"NOTE: dynamic jump\t{match.groups()}")
            anno_match = re.search(r"(<\S+>)", potential_info)
            if anno_match is not None:
                logging.info(
                    f"NOTE: found an annotation\t{anno_match.group(1)} in \t{match.groups()}"
                )
                return None, anno_match.group(1)

        else:
            target_match = target_pattern.search(potential_info)
            if target_match is None:
                no_target_identified += 1
                logging.error(f"Can't identify target\t{match.groups()}")
            else:
                return int(target_match.group("target"), 16), target_match.group("annotation")

        return (None, None)

    while func_start_pc := find_next_func(f):
        func_end_pc = parse_func(f)
        intervals += [(func_start_pc, func_end_pc)]

    logging.info(f"Found {len(all_control_instrs)} control instructions")
    logging.info(f"No target was identified for {no_target_identified} instructions")

    return all_control_instrs, intervals


# Splitting logic
def do_basic_block_analysis(
    all_control_instrs: List[ObjdumpInstrEntry], initial_intervals: List[Interval]
) -> List[Marker]:
    events = intervals_to_events(initial_intervals)

    for control_instr in tqdm(all_control_instrs):
        if control_instr.target is None:
            events += [(control_instr.pc, 0)]
            logging.debug(f"Handled dynamic jump by ending basic block at {control_instr.pc}")
        else:
            events += [(control_instr.pc, 0)]
            events += [(control_instr.target, control_instr.target + 1)]
            logging.debug(f"Handled {control_instr}")

    return events_to_markers(events)


def objdump_to_bbs(f: TextIO) -> BasicBlocks:
    all_control_instrs, inital_basic_blocks = parseFile(f)
    markers = do_basic_block_analysis(all_control_instrs, inital_basic_blocks)
    return BasicBlocks(markers=markers)
