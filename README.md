# Multi-level Simulation using `gem5`

## Setup

- `git submodule update --init --recursive .`
- `git apply --directory embench-iot/ embench.patch` (make embench compile for rv64gc)
- `make gem5` (build the gem5 simulator binary)
- `make embench` (build the embench benchmarks for with rv64gc cross-compiler)

## Details

### gem5

With 32 threads, building `gem5.opt` takes 10-15 minutes.

There are several options for compilation settings which trade off speed for resolution.
We use `.opt` here as starting point.

- **debug** has optimizations turned off. This ensures that variables won’t be optimized out, functions won’t be unexpectedly inlined, and control flow will not behave in surprising ways. That makes this version easier to work with in tools like gdb, but without optimizations this version is significantly slower than the others. You should choose it when using tools like gdb and valgrind and don’t want any details obscured, but other wise more optimized versions are recommended.
- **opt** has optimizations turned on and debugging functionality like asserts and DPRINTFs left in. This gives a good balance between the speed of the simulation and insight into what’s happening in case something goes wrong. This version is best in most circumstances.
- **fast** has optimizations turned on and debugging functionality compiled out. This pulls out all the stops performance wise, but does so at the expense of run time error checking and the ability to turn on debug output. This version is recommended if you’re very confident everything is working correctly and want to get peak performance from the simulator.

We will need a config script to run our benchmarks.
The system is currently running in System Emulation (SE) mode.
This allows us to skip having to configure the board and many of the peripherals requires by the Full System (FS) mode. 

- The system has a `RiscvMinorCPU`, a simple in-order core meant to emulate the `rocket-chip`.
- The clk is set to 100 MHz and the DRAM to 8192 MB
- We have an L1 ICache and an L1 DCache
- We use a `DDR3_1600_8x8` as the mem controller

### Benchmarks

Most benchmarks are tethered, meaning they make syscalls that must be handled by either `gem5` or `spike`. For `spike` we use the proxy kernel `pk` to run the benchmarks. `gem5` supports these off the shelf, but since programs are executed in user mode, some system features are required.

#### RISC-V ISA Benchmarks

To work with `gem5` we require special instances of the benchmarks. These can be obtained as follows.

1. Clone the `gem5-resources` repository
```sh
git clone https://gem5.googlesource.com/public/gem5-resources
```
2. Build the benchmarks

