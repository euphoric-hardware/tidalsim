# Multilevel Simulation using `gem5`

## Setup

### Dependencies

#### Docker

1. Pull the latest Docker image Ubuntu 22.04 with optional dependencies
```sh
docker pull gcr.io/gem5-test/ubuntu-22.04_all-dependencies:v22-1
```
2. Run the Docker environment using 
```sh
docker run -u $UID:$GID --volume <gem5 directory>:/gem5 --rm -it gcr.io/gem5-test/ubuntu-22.04_all-dependencies:v22-1 
```

#### Source

### gem5

1. Clone the `gem5` repository
```sh
git clone https://github.com/gem5/gem5
```
2. Build the RISC-V CPU. There are several options for compilation settings which trade off speed for resolution. We use `.opt` here as starting point. This may take *several* hours. 
```sh
scons build/RISCV/gem5.opt -j {cpus}
```
- **debug** has optimizations turned off. This ensures that variables won’t be optimized out, functions won’t be unexpectedly inlined, and control flow will not behave in surprising ways. That makes this version easier to work with in tools like gdb, but without optimizations this version is significantly slower than the others. You should choose it when using tools like gdb and valgrind and don’t want any details obscured, but other wise more optimized versions are recommended.
- **opt** has optimizations turned on and debugging functionality like asserts and DPRINTFs left in. This gives a good balance between the speed of the simulation and insight into what’s happening in case something goes wrong. This version is best in most circumstances.
- **fast** has optimizations turned on and debugging functionality compiled out. This pulls out all the stops performance wise, but does so at the expense of run time error checking and the ability to turn on debug output. This version is recommended if you’re very confident everything is working correctly and want to get peak performance from the simulator.

3. We will need a config script to run our benchmarks. The system is currently running in System Emulation (SE) mode. This allows us to skip having to configure the board and many of the peripherals requires by the Full System (FS) mode. 
- The system has a `RiscvMinorCPU`, a simple in-order core meant to emulate the `rocket-chip`.
- The clk is set to 100 MHz and the DRAM to 8192 MB
- We have an L1 ICache and an L1 DCache
- We use a `DDR3_1600_8x8` as the mem controller

### Benchmarks

Most benchmarks are tethered, meaning they make syscalls that must be handled by either `gem5` or `spike`. For `spike` we use the proxy kernel `pk` to run the benchmarks. `gem5` supports these off the shelf, but since programs are executed in user mode, some system features are required.

#### RISC-V 

To work with `gem5` we require special instances of the benchmarks. These can be obtained as follows.

1. Clone the `gem5-resources` repository
```sh
git clone https://gem5.googlesource.com/public/gem5-resources
```
2. Build the benchmarks

#### Embench-IOT

We require a special patch to get 64-bit versions of the `embench-iot` tests. 

1. Clone the `embench-iot` repository
```sh
git clone https://github.com/embench/embench-iot.git
```
2. Download the patch and apply it.
```sh
cd embench-iot
git apply embench.patch
```
3. Build the benchmarks

