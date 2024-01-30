#!/usr/bin/env bash

set -x
set -e

gen-cache-state --dir data
vcs -full64 -q -sverilog -Mupdate -debug_access+all -Mdir=vcs +incdir+./vlog tb.v -o simv
./simv
