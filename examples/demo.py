#!/usr/bin/env python3
"""Minimal, reproducible demo of Progenitor's security gate + seed activation.

Run from the repo root:

    python3 examples/demo.py

The lysosome check has no side effects. Seed activation writes state under
``~/.progenitor/`` (see the README "Is it safe?" section). Standard library only.
"""
import contextlib
import io
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "hatchery"))
from engine import Crucible, ingest

print("== Lysosome gate: dangerous-pattern scan (no side effects) ==")
crucible = Crucible()
benign = "def main():\n    return sum(range(10))\n"
hostile = "import os\ndef main():\n    os.system('rm -rf /')\n"
print("  benign gene                 ->",
      "ALLOWED" if crucible._layer4_lysosome(benign)["passed"] else "BLOCKED")
verdict = crucible._layer4_lysosome(hostile)
print("  os.system('rm -rf /') gene  ->",
      "ALLOWED" if verdict["passed"] else "BLOCKED", "—", verdict.get("reason"))

print("\n== Seed activation: ingest -> catalyze (writes ~/.progenitor/) ==")
with contextlib.redirect_stdout(io.StringIO()):  # mute the engine's internal audit chatter
    result = ingest(str(REPO / "INGEST_ME_TO_EVOLVE_pgn-core.pgn"))["catalyze"]()
print("  state:", result.get("state"))
for layer in result.get("crucible", {}).get("results", []):
    mark = "PASS" if layer.get("passed") else "FAIL"
    print(f"    {layer.get('layer')} {layer.get('name')}: {mark}")
