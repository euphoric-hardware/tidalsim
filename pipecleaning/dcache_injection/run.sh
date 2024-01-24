#!/usr/bin/env bash

set -x
set -e

gen-cache-state --type tag --reverse-ways > tag_array.bin
gen-cache-state --type tag --pretty --reverse-ways > tag_array.pretty
gen-cache-state --type data --reverse-ways > data_array.bin
gen-cache-state --type data --pretty --reverse-ways > data_array.pretty
vcs -full64 -q -sverilog -Mupdate -debug_access+all test.v -o simv
./simv
