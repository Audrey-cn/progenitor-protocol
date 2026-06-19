"""Self-locating path constants for progenitor-protocol dev tools.

Replaces the former cross-repo ``devkit_context`` glue (progenitor-devkit, now
dissolved). Paths resolve relative to this repo; the sibling registry defaults
to ``../progenitor-registry`` but can be relocated via environment variables.
"""
from __future__ import annotations

import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent            # progenitor-protocol/tools
PROTOCOL_DIR = SCRIPT_DIR.parent                        # progenitor-protocol repo root
GIT_DIR = PROTOCOL_DIR                                  # back-compat alias (this repo)
TRAE_DIR = PROTOCOL_DIR.parent                          # workspace holding sibling repos
REGISTRY_DIR = Path(os.environ.get("PROGENITOR_REGISTRY_DIR", TRAE_DIR / "progenitor-registry")).resolve()
REPORT_DIR = Path(os.environ.get("PROGENITOR_REPORT_DIR", PROTOCOL_DIR / "reports")).resolve()
RUNTIME_DIR = Path(os.environ.get("PROGENITOR_RUNTIME_DIR", TRAE_DIR / ".runtime" / "progenitor")).resolve()

__all__ = ["SCRIPT_DIR", "GIT_DIR", "TRAE_DIR", "PROTOCOL_DIR", "REGISTRY_DIR", "REPORT_DIR", "RUNTIME_DIR"]
