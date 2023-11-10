#!/usr/bin/env bash

mypy -p tidalsim -p tests --ignore-missing-imports --exclude archive
