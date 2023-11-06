import m5
from m5.objects import *
from caches import *
import argparse
# from Common import Options

# Configure argparser
parser = argparse.ArgumentParser()
# Options.addCommonOptions(parser)
# Options.addSEOptions(parser)

parser.add_argument(
      "-c",
      "--cmd",
      default="",
      help="The binary to run in syscall emulation mode.",
)

args = parser.parse_args()

print(args.cmd)

# Configure system

system = System()

system.clk_domain = SrcClockDomain()
system.clk_domain.clock = '100MHz'
system.clk_domain.voltage_domain = VoltageDomain()

system.mem_mode = 'timing'
system.mem_ranges = [AddrRange('8192MB')]

### CPU ###
system.cpu = RiscvMinorCPU()

### MEMORY ###
system.membus = SystemXBar()

# Connects DMEM and IMEM directly to MEM DDR3
# system.cpu.icache_port = system.membus.cpu_side_ports
# system.cpu.dcache_port = system.membus.cpu_side_ports

# Instantiate caches
system.cpu.icache = L1ICache()
system.cpu.dcache = L1DCache()

# Connect caches to CPU ports
system.cpu.icache.connectCPU(system.cpu)
system.cpu.dcache.connectCPU(system.cpu)

# Connect caches to DDR3 bus
system.cpu.icache.connectBus(system.membus)
system.cpu.dcache.connectBus(system.membus)

system.system_port = system.membus.cpu_side_ports

# Setup Memory Controller
system.mem_ctrl = MemCtrl()
system.mem_ctrl.dram = DDR3_1600_8x8()
system.mem_ctrl.dram.range = system.mem_ranges[0]
system.mem_ctrl.port = system.membus.mem_side_ports

### INTERRUPTS ###
system.cpu.createInterruptController()

# ISA Tests compiled in gem5-resources/src/asmtest/bin with ps environment for SE system
# binary = f'../../gem5-resources/src/asmtest/bin/{test}'
binary = args.cmd

### SPAWN ### 
# for gem5 V21 and beyond
system.workload = SEWorkload.init_compatible(binary)

process = Process()
process.cmd = [binary]
system.cpu.workload = process
system.cpu.createThreads()

### ROOT ###
root = Root(full_system = False, system = system)
m5.instantiate()

### SIMULATE ###
print(f"Simulating {args.cmd.split('/')[-1]}")
exit_event = m5.simulate()

print('Exiting @ tick {} because {}'
      .format(m5.curTick(), exit_event.getCause()))
