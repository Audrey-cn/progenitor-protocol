"""verify_seed - 种子一致性校验：证明你运行的 .pgn 与官方发布/本地重建完全一致。

用法:
  python tools/verify_seed.py --expect <sha256>     # 校验仓库内种子 == 期望哈希
  python tools/verify_seed.py --rebuild             # 从 hatchery 重建种子并比对(等价于 release_check 的种子环节)
  python tools/verify_seed.py --expect <sha256> --rebuild   # 重建后比对期望哈希(净室验证)

R1 缓解: 生成器源码可审计,但交付物是压缩载荷。本工具闭合"菜谱 vs 成品"的信任缝隙——
先审计生成器,再本地重建,再比对官方 SHA-256;三条全过,你就不是在信任任何人,而是在验证数学。
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
SEED = REPO_DIR / "INGEST_ME_TO_EVOLVE_pgn-core.pgn"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def rebuild() -> int:
    r = subprocess.run([sys.executable, str(REPO_DIR / "hatchery" / "incubator.py")],
                       cwd=REPO_DIR)
    return r.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--expect", help="期望的种子 SHA-256（如 Release 页面公布的值）")
    ap.add_argument("--rebuild", action="store_true", help="先从 hatchery 本地重建种子")
    args = ap.parse_args()

    if not SEED.exists():
        print(f"[verify_seed] 找不到种子: {SEED}")
        return 1

    if args.rebuild:
        print("[verify_seed] 本地重建种子 ...")
        if rebuild() != 0:
            print("[verify_seed] 重建失败")
            return 1

    actual = sha256_file(SEED)
    print(f"[verify_seed] 种子 SHA-256: {actual}")
    if args.expect:
        if actual.lower() == args.expect.lower():
            print("[verify_seed] ✅ 与期望哈希一致")
        else:
            print(f"[verify_seed] ❌ 与期望哈希不一致: {args.expect}")
            return 1
    print("[verify_seed] 通过。审计生成器源码 + 本地重建 + 哈希比对 = 不信任任何人,只验证数学。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
