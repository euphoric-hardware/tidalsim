# gem5 build

gem5 = gem5/build/RISCV/gem5.opt

gem5: $(gem5)

$(gem5):
	cd gem5 && scons build/RISCV/gem5.opt --ignore-style -j $(shell nproc)

# Embench binary builds

embench_benchmarks = $(notdir $(shell find embench-iot/src -mindepth 1 -type d))
embench_benchmarks_srcs = $(foreach dir,$(embench_benchmarks),$(shell find embench-iot/src/$(dir) -mindepth 1 -type f))
embench_benchmarks_dirs = $(addprefix embench-iot/bd/src/,$(embench_benchmarks))
# Function to append basename to path
add_basename = $(addsuffix /$(notdir $(1)),$(1))
embench_benchmarks_bins := $(foreach dir,$(embench_benchmarks_dirs),$(call add_basename,$(dir)))

embench: $(embench_benchmarks_bins)

$(embench_benchmarks_bins) &: $(embench_benchmarks_srcs)
	cd embench-iot && ./build_all.py --arch riscv32 --chip generic --board ri5cyverilator --cc riscv64-unknown-elf-gcc --cflags="-c -O2 -ffunction-sections" --ldflags="-Wl,-gc-sections" --user-libs="-lm" -v

# Running embench benchmarks on spike

embench_spike_logs = $(addsuffix /spike.log,$(addprefix runs/embench/,$(embench_benchmarks)))
embench-spike: $(embench_spike_logs)

runs/embench/%/spike.log: embench-iot/bd/src/%
	mkdir -p $(dir $@)
	spike -l pk $^/$(notdir $^) > $@ 2>&1

# Running embench benchmarks on gem5

embench_gem5_logs = $(addsuffix /m5out/stats.txt,$(addprefix runs/embench/,$(embench_benchmarks)))
embench-gem5: $(embench_gem5_logs)

runs/embench/%/m5out/stats.txt: embench-iot/bd/src/%
	mkdir -p $(dir $@)
	./gem5/build/RISCV/gem5.opt --outdir=$(dir $@) ./rocket/rocket.py -c $^/$(notdir $^)

.PHONY: gem5 embench embench-spike embench-gem5
