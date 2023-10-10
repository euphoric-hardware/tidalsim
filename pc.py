import re

instruction_pattern = re.compile(r"core\s*\d: 0x(?P<pc>\w+) ")
name_pattern = re.compile(r"core\s*\d:\s*>>>>\s*(?P<name>\w+)")

file = "aha-mont64.log"
with open(file) as f:
    lines = f.readlines()


def parse_lines(lines):
    instructions = {}
    names = {}
    jumps = {}
    returns = {}
    prev = 0
    for line in lines:
        if instruction := instruction_pattern.match(line):
            pc = int(instruction.group("pc"), 16)
            if pc not in instructions:
                instructions[pc] = 0
            instructions[pc] += 1
            if abs(pc - prev) > 4:
                if pc not in jumps:
                    jumps[pc] = 0
                    # returns[pc] = set()
                jumps[pc] += 1
                # returns[pc].add(prev)
                returns[prev] = pc
            prev = pc
        elif name := name_pattern.match(line):
            symbol = name.group("name")
            names[pc + 4] = symbol
    return instructions, names, jumps, returns

def get_traces(lines, indexes):
    jumps = set(indexes.keys())
    starts = set(indexes.items())
    start = None
    blocks = []
    block = []
    for line in lines:
        if instruction := instruction_pattern.match(line): 
            pc = int(instruction.group("pc"), 16)
            if pc == start:
                block.append(pc)
                blocks.append(block)
                block = []
                start = None
            elif start is not None:
                block.append(pc)
            elif pc in jumps:
                start = indexes[pc]
                block.append(pc)
    return blocks
            

instructions, names, jumps, returns = parse_lines(lines)
blocks = get_traces(lines, returns)

jumps = {key: item for (key,item) in sorted(jumps.items(), key=lambda x: x[-1], reverse=True)}



