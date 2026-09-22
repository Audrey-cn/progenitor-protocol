"""[sandbox_linux] Stage-1 OS hardening for the gene-cage subprocess (Linux x86-64).

seccomp-BPF denylist via prctl(PR_SET_NO_NEW_PRIVS) + prctl(PR_SET_SECCOMP,
SECCOMP_MODE_FILTER). Pure stdlib (ctypes). Part of R4 Stage 1 — docs/R4_SANDBOX.md.

Blocked syscalls (x86-64): socket, socketpair, connect, execve, execveat, plus
write-flagged open(2)/openat(2) — the cage has no fs:write grant today. Read-only opens
are untouched, so imports keep working (failed .pyc writes are ignored by the interpreter).

Contract:
- Applies on Linux x86-64. Anywhere else: returns {"applied": False, "reason": ...} — no error.
- Honors PROGENITOR_SANDBOX_SECCOMP=off as an operator escape hatch (reported, not silent).
- Fails closed on install errors on a supported host: raises SandboxHardeningError (the
  parent surfaces it) — a half-installed wall is worse than a refused run.
"""
from __future__ import annotations

import ctypes
import os
import platform
import sys

PR_SET_NO_NEW_PRIVS = 38
PR_SET_SECCOMP = 22
SECCOMP_MODE_FILTER = 2
SECCOMP_RET_ALLOW = 0x7FFF0000
SECCOMP_RET_ERRNO = 0x00050000
EPERM = 1

AUDIT_ARCH_X86_64 = 0xC000003E

SYS_OPEN, SYS_OPENAT = 2, 257
SYS_SOCKET, SYS_SOCKETPAIR, SYS_CONNECT = 41, 53, 42
SYS_EXECVE, SYS_EXECVEAT = 59, 322

O_WRITE_FLAGS = 0o1 | 0o2 | 0o100 | 0o1000 | 0o2000  # W|R|CREAT|TRUNC|APPEND


class SandboxHardeningError(RuntimeError):
    pass


class _sock_filter(ctypes.Structure):
    _fields_ = [("code", ctypes.c_uint16), ("jt", ctypes.c_uint8),
                ("jf", ctypes.c_uint8), ("k", ctypes.c_uint32)]


class _sock_fprog(ctypes.Structure):
    _fields_ = [("len", ctypes.c_uint16), ("filter", ctypes.POINTER(_sock_filter))]


def _stmt(code, k=0):
    return _sock_filter(code, 0, 0, k)


def _jump(code, k, jt, jf):
    return _sock_filter(code, jt, jf, k)


BPF_LD_W_ABS = 0x20
BPF_JEQ_K = 0x15
BPF_RET_K = 0x06
BPF_ALU_AND_K = 0x54


def _build_filter_minimal():
    """Diagnostic variant: arch check + unconditional allow. If even this EPERMs
    everything, the bug is in the encoding/arch handling, not the deny rules."""
    return [
        _stmt(BPF_LD_W_ABS, 4),
        _jump(BPF_JEQ_K, AUDIT_ARCH_X86_64, 0, 1),
        _stmt(BPF_RET_K, SECCOMP_RET_ALLOW),
        _stmt(BPF_RET_K, SECCOMP_RET_ERRNO | EPERM),
    ]


def _build_filter(deny=True, variant="full"):
    if variant == "diag-arch-match":
        # EPERM iff arch == x86-64 (else allow) - verifies arch load + compare.
        return [
            _stmt(BPF_LD_W_ABS, 4),
            _jump(BPF_JEQ_K, AUDIT_ARCH_X86_64, 1, 0),
            _stmt(BPF_RET_K, SECCOMP_RET_ALLOW),
            _stmt(BPF_RET_K, SECCOMP_RET_ERRNO | EPERM),
        ]
    if variant == "diag-openat-any":
        # EPERM iff nr == openat (else allow) - verifies nr load + per-syscall match.
        return [
            _stmt(BPF_LD_W_ABS, 0),
            _jump(BPF_JEQ_K, SYS_OPENAT, 1, 0),
            _stmt(BPF_RET_K, SECCOMP_RET_ALLOW),
            _stmt(BPF_RET_K, SECCOMP_RET_ERRNO | EPERM),
        ]
    if variant == "diag-openat-writeflag":
        # EPERM iff nr == openat AND flags has write bits - verifies the flag load/AND/JEQ chain.
        return [
            _stmt(BPF_LD_W_ABS, 0),
            _jump(BPF_JEQ_K, SYS_OPENAT, 2, 0),
            _stmt(BPF_LD_W_ABS, 24),
            _stmt(BPF_ALU_AND_K, O_WRITE_FLAGS),
            _jump(BPF_JEQ_K, 0, 1, 0),
            _stmt(BPF_RET_K, SECCOMP_RET_ALLOW),
            _stmt(BPF_RET_K, SECCOMP_RET_ERRNO | EPERM),
        ]
    """x86-64 cBPF program. Indexes matter — the jt/jf arithmetic below depends on them."""
    if variant == "socket-only":
        # Diagnostic bisect: deny socket only, no open/openat involvement.
        return [
            _stmt(BPF_LD_W_ABS, 4),
            _jump(BPF_JEQ_K, AUDIT_ARCH_X86_64, 0, 3),
            _stmt(BPF_LD_W_ABS, 0),
            _jump(BPF_JEQ_K, SYS_SOCKET, 2, 0),
            _stmt(BPF_RET_K, SECCOMP_RET_ALLOW),
            _stmt(BPF_RET_K, SECCOMP_RET_ERRNO | EPERM),
        ]
    # Stage 1 scope: network + exec denial only. FS write-scoping via openat flag
    # matching proved fragile under the cBPF verifier - that moves to Stage 2 (Landlock),
    # which is the purpose-built tool for filesystem rules.
    return [
        _stmt(BPF_LD_W_ABS, 4),                            # 0:  seccomp_data.arch
        _jump(BPF_JEQ_K, AUDIT_ARCH_X86_64, 0, 5),         # 1:  != x86-64 → EPERM-all
        _stmt(BPF_LD_W_ABS, 0),                            # 2:  nr
        _jump(BPF_JEQ_K, SYS_EXECVE, 3, 0),                # 3  → deny @7
        _jump(BPF_JEQ_K, SYS_EXECVEAT, 2, 0),              # 4
        _jump(BPF_JEQ_K, SYS_SOCKET, 1, 0),                # 5
        _jump(BPF_JEQ_K, SYS_CONNECT, 0, 0),               # 6
        _stmt(BPF_RET_K, SECCOMP_RET_ALLOW),               # 7
        _stmt(BPF_RET_K, SECCOMP_RET_ERRNO | EPERM),       # 8
    ]


def _unsupported_reason() -> str | None:
    if sys.platform != "linux":
        return "not linux"
    machine = platform.machine().lower()
    if machine not in ("x86_64", "amd64"):
        return f"unsupported architecture: {platform.machine()}"
    return None


def diagnose_filter():
    """Install successive RET-terminated prefixes of the full filter (seccomp filters
    stack). The first prefix the kernel rejects pinpoints the invalid instruction group.
    Returns [(prefix_len, result), ...]. FOR DIAGNOSIS ONLY - installed filters persist."""
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                           ctypes.c_ulong, ctypes.c_ulong]
    libc.prctl.restype = ctypes.c_int
    prog = _build_filter()
    results = []
    for length in range(1, len(prog) + 1):
        seg = prog[:length]
        if seg[-1].code & 0x07 != 0x06:  # only RET-terminated prefixes are valid programs
            continue
        arr = (_sock_filter * length)(*seg)
        fprog = _sock_fprog(length, arr)
        if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            results.append((length, f"NNP errno {ctypes.get_errno()}"))
            continue
        if libc.prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER,
                      ctypes.addressof(fprog), 0, 0) != 0:
            results.append((length, f"EINVAL errno {ctypes.get_errno()}"))
        else:
            results.append((length, "ok"))
    return results


def apply_sandbox_hardening(deny: bool = True, variant: str = "full") -> dict:
    """Install the Stage-1 seccomp denylist in the calling (sandbox) process.

    Never silently skips on a supported host: install errors raise SandboxHardeningError
    (fail closed). Non-Linux / non-x86-64 hosts get {"applied": False, "reason": ...}.
    """
    unsupported = _unsupported_reason()
    if unsupported:
        return {"applied": False, "reason": unsupported}
    if os.environ.get("PROGENITOR_SANDBOX_SECCOMP", "").strip().lower() in ("off", "0", "false"):
        return {"applied": False, "reason": "disabled via PROGENITOR_SANDBOX_SECCOMP"}

    libc = ctypes.CDLL(None, use_errno=True)
    if not hasattr(libc, "prctl"):
        raise SandboxHardeningError("libc lacks prctl — cannot install seccomp")
    # Explicit argtypes: prctl(2) is variadic, and pointers through an untyped variadic
    # call are how you get spurious EFAULT (seen on ubuntu CI) — pass the filter as an
    # explicit word-sized address instead of byref.
    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                           ctypes.c_ulong, ctypes.c_ulong]
    libc.prctl.restype = ctypes.c_int

    prog = _build_filter() if deny else _build_filter_minimal()
    if variant in ("socket-only", "diag-arch-match", "diag-openat-any", "diag-openat-writeflag"):
        prog = _build_filter(variant=variant)
    arr = (_sock_filter * len(prog))(*prog)
    fprog = _sock_fprog(len(prog), arr)

    if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        err = ctypes.get_errno()
        raise SandboxHardeningError(f"PR_SET_NO_NEW_PRIVS failed: errno {err}")
    if libc.prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER,
                  ctypes.addressof(fprog), 0, 0) != 0:
        err = ctypes.get_errno()
        raise SandboxHardeningError(f"PR_SET_SECCOMP failed: errno {err} (fprog@{ctypes.addressof(fprog):#x})")
    return {"applied": True, "method": "seccomp-bpf-denylist",
            "blocked": ["socket", "socketpair", "connect", "execve", "execveat"]}
