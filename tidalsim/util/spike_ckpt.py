def arch_state_dump_cmds(nharts: int) -> str:
    mem_dump = "dump\n"
    def reg_dump(h: int):
        return f"""pc {h}
priv {h}
reg {h} fcsr
reg {h} vstart
reg {h} vxsat
reg {h} vxrm
reg {h} vcsr
reg {h} vtype
reg {h} stvec
reg {h} sscratch
reg {h} sepc
reg {h} scause
reg {h} stval
reg {h} satp
reg {h} mstatus
reg {h} medeleg
reg {h} mideleg
reg {h} mie
reg {h} mtvec
reg {h} mscratch
reg {h} mepc
reg {h} mcause
reg {h} mtval
reg {h} mip
reg {h} mcycle
reg {h} minstret
mtime
mtimecmp {h}\n""" \
        + ''.join([f"freg {h} {fr}\n" for fr in range(32)]) \
        + ''.join([f"reg {h} {xr}\n" for xr in range(32)]) \
        + f"vreg {h}\n"

    return mem_dump + ''.join([reg_dump(h) for h in range(nharts)])
