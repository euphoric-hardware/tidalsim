import subprocess
import os
import json

def main():
    print("cwd:", os.getcwd())

    results = {}

    mode = "isa"

    if mode == "isa":
        failed = 0
        fnames = open("tests/configs/isa.txt").readlines()
        for test in fnames:
            if ("ui-ps" in test):

                print(test[:-1], ": ", end="")

                test = test.replace("\n", "")

                result = subprocess.run(
                    f"build/Riscv/gem5.opt configs/rocket/rocket.py -c ../gem5-resources/src/asmtest/bin/{test}",
                    shell=True,
                    capture_output=True
                )
                output = result.stdout.decode('utf-8')

                if 'because exiting with last active thread context' in output:
                    print(f"PASS")
                else:
                    print(f"FAIL")
                    failed += 1


                results[test] = {}
                stats = open("m5out/stats.txt").readlines()
                for line in stats[2:-2]:
                    line = list(filter(lambda x: x != "", line.split(" ")))
                    if len(line) >= 2:
                        results[test][line[0]] = float(line[1])

        with open(f"{mode}.json", 'w') as f:
            json.dump(results, f)

        print(f"***FAILED: {failed} TESTS***")
    elif mode == "embench":
        failed = 0
        fnames = open("tests/configs/embench.txt").readlines()
        for test in fnames:
            if ("" in test):

                print(test[:-1], ": ", end="")

                test = test.replace("\n", "")

                result = subprocess.run(
                    f"build/Riscv/gem5.opt configs/rocket/rocket.py -c ../embench-iot/bd/src/{test}/{test}",
                    shell=True,
                    capture_output=True
                )
                output = result.stdout.decode('utf-8')

                if 'because exiting with last active thread context' in output:
                    print(f"PASS")
                else:
                    print(f"FAIL")
                    failed += 1


                results[test] = {}
                stats = open("m5out/stats.txt").readlines()
                for line in stats[2:-2]:
                    line = list(filter(lambda x: x != "", line.split(" ")))
                    if len(line) >= 2:
                        results[test][line[0]] = float(line[1])

        with open(f"{mode}_data.json", 'w') as f:
            json.dump(results, f)

        print(f"***FAILED: {failed} TESTS***")
    else:
        print("NO MODE SPECIFIED")
