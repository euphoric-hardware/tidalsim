from dataclasses import dataclass
from intervaltree import IntervalTree, Interval

@dataclass
class BasicBlocks:
    pc_to_bb_id: IntervalTree

# RISC-V Psuedoinstructions: https://github.com/riscv-non-isa/riscv-asm-manual/blob/master/riscv-asm.md#pseudoinstructions
branches = [
        # RV64I branches
        'beq', 'bge', 'bgeu', 'blt', 'bltu', 'bne',
        # RV64C branches
        'c.beqz', 'c.bnez',
        # Psuedo instructions
        'beqz', 'bnez', 'blez', 'bgez', 'bltz', 'bgtz', 'bgt', 'ble', 'bgtu', 'bleu'
        ]
jumps = ['j', 'jal', 'jr', 'jalr', 'ret', 'call', 'c.j', 'c.jal', 'c.jr', 'c.jalr', 'tail']
syscalls = ['ecall', 'ebreak', 'mret', 'sret', 'uret']
control_insts = set(branches + jumps + syscalls)

no_target_insts = set(syscalls + ['jr', 'jalr', 'c.jr', 'c.jalr', 'ret'])