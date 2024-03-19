import subprocess
import fileinput
import sys
from pathlib import Path
from typing import Optional
import logging


def run_cmd(cmd: str, cwd: Path) -> subprocess.CompletedProcess:
    logging.info(f'Running "{cmd}"')
    result = subprocess.run(cmd, shell=True, stdout=sys.stdout, stderr=subprocess.STDOUT, cwd=cwd)
    assert result.returncode == 0, f"{cmd} failed with returncode {result.returncode}"
    return result


def run_cmd_pipe(cmd: str, cwd: Path, stderr: Path) -> subprocess.CompletedProcess:
    logging.info(f'Running "{cmd}" and redirecting stderr to {stderr}')
    with stderr.open("w") as stderr_file:
        result = subprocess.run(cmd, shell=True, stdout=sys.stdout, stderr=stderr_file, cwd=cwd)
        assert result.returncode == 0, f"{cmd} failed with returncode {result.returncode}"
        return result


def run_cmd_capture(cmd: str, cwd: Path) -> str:
    logging.info(f'Running "{cmd}" and capturing stdout')
    result = subprocess.run(cmd, shell=True, capture_output=True, cwd=cwd)
    stdout = result.stdout.decode("UTF-8").strip()
    assert (
        result.returncode == 0
    ), f"{cmd} failed with returncode {result.returncode} and stdout {stdout}"
    return stdout


def run_cmd_pipe_stdout(cmd: str, cwd: Path, stdout: Path) -> subprocess.CompletedProcess:
    logging.info(f'Running "{cmd}" and redirecting stdout to {stdout}')
    with stdout.open("w") as stdout_file:
        result = subprocess.run(cmd, shell=True, stdout=stdout_file, cwd=cwd)
        assert result.returncode == 0, f"{cmd} failed with returncode {result.returncode}"
        return result


def run_rtl_sim_cmd(
    simulator: Path,
    perf_file: Path,
    perf_sample_period: int,
    max_instructions: Optional[int],
    chipyard_root: Path,
    binary: Path,
    loadarch: Path,
    suppress_exit: bool,
    checkpoint_dir: Optional[Path],
    timeout_cycles: int = 10_000_000,
) -> str:
    max_insts_str = f"+max-instructions={max_instructions} " if max_instructions is not None else ""
    checkpoint_dir_str = (
        f"+checkpoint-dir={checkpoint_dir.resolve()} " if checkpoint_dir is not None else ""
    )
    suppress_exit_str = "+suppress-exit " if suppress_exit else ""
    # +no_hart0_msip = with loadarch, the target should begin execution immediately without
    #   an interrupt required to jump out of the bootrom
    rtl_sim_cmd = (
        f"{simulator} "
        "+permissive "
        "+dramsim "
        f"+dramsim_ini_dir={chipyard_root.resolve()}/generators/testchipip/src/main/resources/dramsim2_ini "
        "+no_hart0_msip "
        "+ntb_random_seed_automatic "
        f"+max-cycles={timeout_cycles} "
        f"+perf-sample-period={perf_sample_period} "
        f"+perf-file={perf_file.resolve()} "
        f"{max_insts_str}"
        f"+loadmem={binary.resolve()} "
        f"+loadarch={loadarch.resolve()} "
        f"{checkpoint_dir_str}"
        "+permissive-off "
        f"{suppress_exit_str}"
        f"{binary.resolve()}"
    )
    return rtl_sim_cmd
    # run_cmd(rtl_sim_cmd, cwd)
