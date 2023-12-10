#!/usr/bin/env bash

poetry run mypy -p tidalsim -p tests --ignore-missing-imports --exclude archive --check-untyped-defs
