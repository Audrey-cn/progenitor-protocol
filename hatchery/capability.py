"""[capability] Gene Contract v2 — capability manifests + scoped (pure / advisory) execution.

Keystone of the corrected design (see docs/VISION.md). A gene declares a capability manifest
(purity / inputs / outputs / grants). A `pure` gene runs with NO ambient authority — no os /
socket / subprocess / file / network, no dunder attribute access, only a curated builtins set
and a whitelist of compute-only stdlib modules. Its output is ADVISORY: run_pure_gene returns
a proposal and never performs side effects on the host's behalf; the host agent decides whether
to act on it. This turns "sandbox arbitrary untrusted code" (unsolvable) into "run a declared,
authority-free function" (solvable).

SECURITY HONESTY: the AST allowlist + curated builtins are a STRONG PRE-FILTER, not a guaranteed
boundary. In-process CPython sandboxing is famously porous — any allowlisted module that turns a
string into attribute/field access (e.g. operator.attrgetter, string.Formatter.get_field) re-opens
an escape to the real builtins, so the allowlist must be kept tight and is defense-in-depth. For
genuinely untrusted sources, run pure genes out-of-process too (subprocess + resource caps, and
ideally OS isolation: seccomp/landlock/namespaces or wasm) — that is the real boundary.
"""
from __future__ import annotations

import ast
import importlib
import re
import signal

# Compute-only stdlib a pure gene may import — no I/O, no ambient authority.
# SECURITY: any module that turns a *string* into attribute/field access bypasses the AST
# dunder check (the dunder name never appears as an ast.Attribute node) and is full RCE:
#   - `operator` (attrgetter/methodcaller):  operator.attrgetter('__globals__')(json.dumps)...
#   - `string`   (Formatter.get_field/vformat): string.Formatter().get_field('0.__globals__', [json.dumps], {})...
# Both reach a real frame's __globals__ → real __builtins__ → __import__. They are EXCLUDED and
# must never be re-added. Treat this allowlist as a strong pre-filter, NOT a hard boundary.
PURE_SAFE_MODULES = {
    "json", "re", "math", "datetime", "hashlib", "base64", "itertools", "collections",
    "textwrap", "statistics", "decimal", "fractions", "difflib", "bisect",
    "heapq", "functools",
}

# Builtins a pure gene may use — note the absence of eval/exec/open/__import__/getattr/...
# `print` is also excluded: a pure gene returns a value, and stdout writes are I/O.
PURE_SAFE_BUILTINS = {
    "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes", "chr", "complex",
    "dict", "divmod", "enumerate", "filter", "float", "format", "frozenset", "hash", "hex",
    "int", "isinstance", "issubclass", "iter", "len", "list", "map", "max", "min", "next",
    "oct", "ord", "pow", "range", "repr", "reversed", "round", "set", "slice",
    "sorted", "str", "sum", "tuple", "zip",
}

# Calls rejected at the AST level (defense-in-depth alongside the curated builtins).
_CALL_DENY = {
    "eval", "exec", "compile", "open", "__import__", "getattr", "setattr", "delattr",
    "vars", "globals", "locals", "input", "breakpoint", "memoryview", "help", "exit", "quit",
}

# Dunder attributes that walk from a value to type/builtins (escape gadgets).
_DUNDER_DENY = {
    "__class__", "__subclasses__", "__bases__", "__base__", "__mro__", "__globals__",
    "__builtins__", "__code__", "__closure__", "__subclasshook__", "__getattribute__",
    "__import__", "__dict__", "__loader__", "__spec__", "mro",
}


def check_pure_safe(code):
    """AST allowlist for a `pure` gene. Returns (ok: bool, reason: str)."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return False, f"syntax error: {exc}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in PURE_SAFE_MODULES:
                    return False, f"import not allowed in a pure gene: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in PURE_SAFE_MODULES:
                return False, f"import not allowed in a pure gene: {node.module}"
        elif isinstance(node, ast.Attribute):
            if node.attr in _DUNDER_DENY or (node.attr.startswith("__") and node.attr.endswith("__")):
                return False, f"dunder attribute access not allowed: .{node.attr}"
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            return False, "global/nonlocal not allowed in a pure gene"
        elif isinstance(node, ast.Subscript):
            base = node.value
            name = base.id if isinstance(base, ast.Name) else (base.attr if isinstance(base, ast.Attribute) else "")
            if name in _DUNDER_DENY:
                return False, f"subscript on {name} not allowed"
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _CALL_DENY:
            return False, f"call not allowed in a pure gene: {node.func.id}()"
    return True, "pure-safe"


def _safe_import(name, *args, **kwargs):
    if name.split(".")[0] not in PURE_SAFE_MODULES:
        raise ImportError(f"import not allowed in a pure gene: {name}")
    return importlib.import_module(name)


def _pure_builtins():
    import builtins as _b
    safe = {k: getattr(_b, k) for k in PURE_SAFE_BUILTINS if hasattr(_b, k)}
    safe.update({"True": True, "False": False, "None": None, "__import__": _safe_import})
    return safe


class _PureTimeout(Exception):
    """Raised when a pure gene exceeds its wall-clock budget."""


def run_pure_gene(code, params=None, *, entry="main", timeout_sec=5):
    """Run a pure gene's entry function; return its result as an ADVISORY proposal.

    Never performs side effects on the host's behalf — the host agent decides what to do with
    result["result"]. Refuses if the code is not pure-safe. A wall-clock cap (``timeout_sec``)
    stops runaway loops; it relies on SIGALRM and so only applies on the main thread of a
    Unix host — elsewhere it degrades gracefully (no timeout). Memory caps still require the
    out-of-process sandbox; the allowlist already denies all I/O and ambient authority.
    """
    ok, reason = check_pure_safe(code)
    if not ok:
        return {"status": "rejected", "reason": reason}
    namespace = {"__builtins__": _pure_builtins()}

    def _on_timeout(signum, frame):
        raise _PureTimeout()

    timer_set = False
    old_handler = None
    try:
        if timeout_sec and hasattr(signal, "SIGALRM"):
            try:
                old_handler = signal.signal(signal.SIGALRM, _on_timeout)
                signal.setitimer(signal.ITIMER_REAL, timeout_sec)
                timer_set = True
            except (ValueError, OSError):
                timer_set = False  # not on the main thread → run without the cap
        try:
            exec(compile(code, "<pure-gene>", "exec"), namespace)
            fn = namespace.get(entry)
            if not callable(fn):
                return {"status": "loaded", "reason": f"no callable '{entry}'"}
            return {"status": "proposed", "advisory": True, "result": fn(**(params or {}))}
        except _PureTimeout:
            return {"status": "timeout", "reason": f"pure gene exceeded {timeout_sec}s"}
        except Exception as exc:
            return {"status": "error", "reason": f"{type(exc).__name__}: {exc}"}
    finally:
        if timer_set:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)


def parse_capability_manifest(header):
    """Parse Gene Contract v2 manifest fields from a gene's comment/YAML header.

    Recognized: life_id, creator, description, purity (pure|effectful, default effectful),
    inputs, outputs, grants (comma list). Effectful is the safe default for unlabeled genes.
    """
    manifest = {"purity": "effectful", "grants": []}
    for key in ("life_id", "creator", "description", "purity", "inputs", "outputs"):
        match = re.search(rf"(?m)^\s*#?\s*{key}:\s*(.+)$", header)
        if match:
            manifest[key] = match.group(1).strip()
    grants = re.search(r"(?m)^\s*#?\s*grants:\s*(.+)$", header)
    if grants:
        manifest["grants"] = [g.strip() for g in grants.group(1).strip().strip("[]").split(",") if g.strip()]
    purity = str(manifest.get("purity", "effectful")).strip().lower()
    manifest["purity"] = purity if purity in ("pure", "effectful") else "effectful"
    return manifest
