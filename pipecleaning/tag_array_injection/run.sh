#!/usr/bin/env bash

set -x
set -e

gen-cache-state --reverse-ways > tag_array.bin
gen-cache-state --pretty --reverse-ways > tag_array.pretty
vcs -full64 -q -sverilog -Mupdate -debug_access+all test.v -o simv
./simv
