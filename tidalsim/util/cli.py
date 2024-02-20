import subprocess
import fileinput
import sys
from pathlib import Path
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
