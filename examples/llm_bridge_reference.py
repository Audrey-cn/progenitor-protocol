"""[R5 reference] LLM bridge reference implementation for absorb-from-knowledge.

The engine ships the EXTENSION POINT (Phagocyte.register_llm_bridge) but no LLM —
this reference shows both ways to complete the pipeline:

1. Spec mode (deterministic, offline): the "knowledge" is a JSON gene spec and
   spec_to_gene_code compiles it into gene source. Fully testable, no LLM needed.

2. LLM mode (pattern for real hosts): make_llm_bridge(llm_chat) wraps any text->text
   chat callable (OpenAI-compatible API, local model, whatever the host has) into a
   (translate_fn, repair_fn) pair ready for register_llm_bridge.

Both satisfy the engine contract (tests/test_llm_bridge_honesty.py):
    translate_fn(raw_text) -> python source string that defines verify() -> truthy
The emitted source passes the lysosome denylist and runs in the restricted sandbox.

Zero third-party dependencies. Host-side example - the engine never imports it.
"""
from __future__ import annotations

import json

GENE_PROMPT = """You translate knowledge into a Progenitor gene.

Rules:
- Output ONLY Python source code defining main() and verify().
- main() implements the capability using the Python standard library only.
- Forbidden: import os/socket/subprocess, eval, exec, open, __import__, dunder getattr.
- verify() must re-check the capability and return a truthy value.

Knowledge to absorb:
"""

# The sandbox exposes almost no builtins (just print), so the emitted gene must be free
# of builtin calls - hence the literal-True verify default, written as an escaped \n.
DEFAULT_VERIFY = "main()\\n    return True"


def spec_to_gene_code(text: str) -> str:
    """Compile a JSON gene spec into gene source.

    Spec: {"name": str, "description": str, "body": str,
           "verify": str (optional, default 'main(); return True'),
           "pure": bool (optional, header hint only)}

    `body` lines become main()'s body; `verify` lines become verify()'s body.
    """
    spec = json.loads(text)
    name = str(spec.get("name", "gene"))
    if not name.replace("-", "").replace("_", "").isalnum():
        raise ValueError(f"invalid spec name: {name!r}")
    description = str(spec.get("description", ""))
    body = str(spec["body"]).rstrip()
    verify_body = str(spec.get("verify", DEFAULT_VERIFY)).rstrip()

    indent = "\n    "
    header = (
        f"# life_id: PGN@L1-R5-{name.upper().replace('-', '_')}\n"
        f"# creator: llm-bridge-reference\n"
        f"# description: {description}\n"
    )
    return (
        f"{header}\n"
        f"def main():\n"
        f"{indent}{body}\n"
        f"\n"
        f"def verify():\n"
        f"{indent}{verify_body}\n"
    )


def make_llm_bridge(llm_chat, repair_chat=None):
    """Wrap an LLM chat callable as (translate_fn, repair_fn) for register_llm_bridge.

    llm_chat(prompt) -> str must return Python source defining verify() -> truthy.
    repair_chat(code, error) -> str optionally fixes rejected code.
    """
    def translate_fn(text: str) -> str:
        return llm_chat(GENE_PROMPT + text)

    if repair_chat is None:
        return translate_fn, None

    def repair_fn(code: str, error: str) -> str:
        # Engine contract: repair_fn(code, error) -> fixed code. Pass both through so the
        # host's repair callable sees exactly what failed and why.
        return repair_chat(code, error)

    return translate_fn, repair_fn
