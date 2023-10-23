from intervaltree import IntervalTree, Interval
from tqdm import tqdm
import logging
import re
import numpy as np
from sklearn.decomposition import PCA
import matplotlib.pyplot as plt

# Regex patterns to extract instructions or symbols from Spike dump
instruction_pattern = re.compile(r"core\s*\d: 0x(?P<pc>\w+) \((?P<inst>\w+)\)")
name_pattern = re.compile(r"core\s*\d:\s*>>>>\s*(?P<name>\w+)")

# Pass in Spike dump here. We read in and then parse every line
file = "aha-mont64.log"
with open(file) as f:
    lines = f.readlines()

# Make initial pass through the Spike dump
# A new interval is recorded when the PC changes by more than 4
# The end of the previous Interval is the PC that was jumped from
# The start of the next Interval is the PC that was jumped to
# No data is stored, speeds up the lookup significantly
start = None
previous = None
intervals = IntervalTree()
for line in tqdm(lines):
    if instruction := instruction_pattern.match(line):
        pc = int(instruction.group("pc"), 16)
        if not start:
            start = pc
        if previous and (abs(pc - previous) > 4):
            intervals[start:previous + 4] = None
            start = pc
        previous = pc

# Ensures that PCs have a one-to-one mapping to an interval
intervals.merge_equals()
intervals.split_overlaps()

# Assign each interval an index in the BBV vector
# Easier to just instantiate a new tree for lookup later
id = 0
unique_intervals = IntervalTree()
for interval in intervals:
    unique_intervals.addi(interval.begin, interval.end, id)
    id += 1

# Compute the BBV
# Dynamically pass k or a list of k's specifying the interval length
N = len(lines)
ks = [100]

# Make a second pass through and compute the BBV for each interval for each k
# BBV shape is (basic block, interval) meaning the basic block vector is in the columns
bbvs = [np.zeros((len(intervals), N // k + 1)) for k in ks]
for (i, line) in tqdm(enumerate(lines)):
        if instruction := instruction_pattern.match(line):
            pc = int(instruction.group("pc"), 16)
            (interval,) = unique_intervals[pc]
            for (j, k) in enumerate(ks):
                bbvs[j][interval.data, i // k] += 1

# dimensionalities = np.array([])
# for bbv in bbvs:
#     pca = PCA(n_components="mle")
#     result = pca.fit(bbv.T)
#     dimensionalities = np.append(dimensionalities, result.n_components_)

# plt.plot(ks, dimensionalities)