# Multi-level Simulation using `spike`, uArch Warmup Models, and Chipyard RTL Simulation

## Setup in Chipyard

- Install `poetry`
    - `curl -sSL https://install.python-poetry.org | POETRY_HOME=/scratch/<YOUR USERNAME>/poetry python3 -`
    - Add `POETRY_HOME/bin` to your `$PATH`
    - Add `export PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring"` to your `~/.bashrc`
        - There is a [bug with an older version of pip](https://github.com/python-poetry/poetry/issues/3365)
    - Run `poetry self add poetry-plugin-dotenv`
- Clone Chipyard and use the `multi-level-sim` branch
- Run [Chipyard setup](https://chipyard.readthedocs.io/en/stable/Chipyard-Basics/Initial-Repo-Setup.html) as usual
    - Install [miniconda3](https://github.com/conda-forge/miniforge/#download)
    - Install `conda-lock`: `conda install -n base conda-lock=1.4`, `conda activate base`
    - `./build-setup.sh --use-lean-conda`
- Activate the Chipyard conda environment
    - `conda activate ./.conda-env`
    - `source env.sh`
- Install the `tidalsim` poetry environment
    - `cd tools/tidalsim`
    - `poetry install`
    - This will install the `tidalsim` scripts and dependencies into the *conda virtualenv*
    - Try running `gen-ckpt -h` and `tidalsim -h`

### TidalSim Flow

- Build a RTL simulator with state injection support
    - `cd sims/vcs`
    - `make default STATE_INJECT=1 CONFIG=FastRTLSimRocketNoL2Config` (`STATE_INJECT=1` will use the state injection `TestHarness`, the `CONFIG` is set to a Rocket core without an L2)
- Run simulation with state injection and functional cache warmup
    - `tidalsim --binary tests/hello.riscv --interval-length 1000 --clusters 3 --simulator sims/vcs/simv-inject-chipyard.harness-FastRTLSimRocketNoL2Config --chipyard-root . --dest-dir runs --cache-warmup`
    - This will run sampled simulation and store the results in the `runs` directory
    - Run `head runs/hello.riscv*/**/perf.csv` to see the performance logs for each sample replayed in RTL simulation
- Collect a reference performance trace (just add `--golden-sim` to the `tidalsim` invocation)
    - `tidalsim --binary tests/hello.riscv --interval-length 1000 --clusters 3 --simulator sims/vcs/simv-inject-chipyard.harness-FastRTLSimRocketNoL2Config --chipyard-root . --dest-dir runs --golden-sim`

### Manual Checkpoint Generation

- `gen-ckpt --binary $RISCV/riscv64-unknown-elf/share/riscv-tests/isa/rv64ui-p-add --dest-dir checkpoints --inst-points 0 100 200 300`
    - This will take checkpoints after 0, 100, 200, 300 instructions have committed
- `head -n 3 checkpoints/rv64ui-p-add.loadarch/*/loadarch`
    - This will show the PC and priv mode for each checkpoint taken
- To restart a single checkpoint in RTL simulation
    - `cd sims/vcs`
    - `make run-binary LOADMEM=1 STATE_INJECT=1 LOADARCH=checkpoints/rv64ui-p-add.loadarch/0x80000000.100 EXTRA_SIM_FLAGS="+perf-sample-period=100 +perf-file=perf.csv +max-instructions=1000"`
        - `+perf-sample-period` is the window for reporting performance statistics (in instructions)
        - `+perf-file` is where performance statistics are dumped to (CSV format)
        - `+max-instructions` terminates the simulation after the specified number of instructions have committed

## Dev Notes

- To run unittests: `pytest`
    - To run a specific test: `pytest tests/test_mtr.py -rA -k "with_data"` (`-k` specifies a string fragment of test function you want to run, `-rA` shows the test stdout output)
    - Some tests use temporary directories to do their work, those directories are persisted here: `ls /tmp/pytest-of-<user>/pytest-current/<test function>/`
- To typecheck: `poetry run pyright`
- To format: `poetry run black tidalsim`, `poetry run black tests`

---

---

## Old / Archive

### Setup

- `git submodule update --init --recursive .`
- `git apply --directory embench-iot/ embench.patch` (make embench compile for rv64gc)
- `make gem5` (build the gem5 simulator binary)
- Get the RISC-V gcc cross compiler
    - Pick a release from here: https://github.com/riscv-collab/riscv-gnu-toolchain/tags
    - Download it (e.g. `wget https://github.com/riscv-collab/riscv-gnu-toolchain/releases/download/2023.07.07/riscv64-elf-ubuntu-20.04-gcc-nightly-2023.07.07-nightly.tar.gz`)
    - Unpack it (`tar -xzvf riscv64-elf-ubuntu-20.04-gcc-nightly-2023.07.07-nightly.tar.gz`)
    - Add it to your $PATH (`export PATH = ${PATH}:/path/to/riscv/bin`)
    - Set the $RISCV envvar (`export RISCV = /path/to/riscv`)
    - Restart your shell and make sure `which riscv64-unknown-elf-gcc` returns the right path
- `make embench` (build the embench benchmarks for with rv64gc cross-compiler)
- Build `spike` (riscv-isa-sim)
    - `git clone git@github.com:riscv-software-src/riscv-isa-sim`
    - `cd riscv-isa-sim && mkdir build && cd build`
    - `../configure --prefix=$RISCV`
    - `make -j32 && make install`
- Build `pk` (riscv-pk)
    - `git clone git@github.com:riscv-software-src/riscv-pk`
    - `cd riscv-pk && mkdir build && cd build`
    - `../configure --prefix=$RISCV --host=riscv64-unknown-elf`
    - `make -j8 && make install`
- `make embench-spike`: runs all embench binaries on spike and saves their commit logs in `runs`
- `make embench-gem5`: runs all embench binaries on gem5 and saves their stats.txt files in `runs`

### gem5 (old)

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

