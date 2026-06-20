#!/usr/bin/env bash
# Local release gate (RUNTIME_AND_BUILD_PLAN exit-criterion #1).
# Runs the test suite and rebuilds + validates the .pgn seed — the same checks as CI.
# Use this before/after any engine change (and around the future source-modularization).
#
#   tools/release_check.sh            # uses python3
#   PYTHON=/path/to/python tools/release_check.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
echo "==> pytest"
"$PY" -m pytest tests/ -q
echo "==> rebuild + validate seed"
"$PY" hatchery/incubator.py
echo "✓ release-check passed"
