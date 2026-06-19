#!/usr/bin/env python3
"""
星门阵列连通性诊断工具
用于测试 Progenitor 星门通道的可用性
"""

import sys
import time
from urllib import request, error

DEFAULT_GATEWAYS = [
    "https://raw.githubusercontent.com/Audrey-cn/progenitor-registry/main/genes/",
    "https://ghproxy.com/https://raw.githubusercontent.com/Audrey-cn/progenitor-registry/main/genes/",
    "https://mirror.ghproxy.com/https://raw.githubusercontent.com/Audrey-cn/progenitor-registry/main/genes/",
    "https://ipfs.io/ipfs/",
    "https://dweb.link/ipfs/",
    "https://cloudflare-ipfs.com/ipfs/",
]

IPFS_GATEWAYS = [
    "https://ipfs.io/ipfs/",
    "https://dweb.link/ipfs/",
    "https://cloudflare-ipfs.com/ipfs/",
    "https://ghproxy.com/ipfs/",
]

AKASHIC_INDEX = "https://raw.githubusercontent.com/Audrey-cn/progenitor-registry/main/.akashic_index.json"


def test_gateway(gateway_url, timeout=10):
    """测试单个网关连通性"""
    start = time.perf_counter()
    try:
        req = request.Request(gateway_url)
        with request.urlopen(req, timeout=timeout) as resp:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return {
                "gateway": gateway_url,
                "status": "✅ ONLINE",
                "response_ms": elapsed_ms,
                "status_code": resp.status,
            }
    except error.HTTPError as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "gateway": gateway_url,
            "status": f"⚠️ HTTP {e.code}",
            "response_ms": elapsed_ms,
            "error": str(e),
        }
    except error.URLError as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "gateway": gateway_url,
            "status": "❌ UNREACHABLE",
            "response_ms": elapsed_ms,
            "error": str(e),
        }
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "gateway": gateway_url,
            "status": f"❌ ERROR",
            "response_ms": elapsed_ms,
            "error": str(e),
        }


def test_ipfs_content(cid, timeout=15):
    """测试IPFS内容是否可访问"""
    print(f"\n🌌 测试IPFS内容: {cid[:20]}...")

    for gateway in IPFS_GATEWAYS:
        url = f"{gateway}{cid}"
        print(f"   尝试: {gateway}", end=" ")
        result = test_gateway(url, timeout)
        print(f"{result['status']} ({result.get('response_ms', 0):.1f}ms)")

        if "✅" in result["status"]:
            return True, gateway, result

    return False, None, None


def test_akashic_index():
    """测试阿卡夏索引获取"""
    return test_gateway(AKASHIC_INDEX)


def test_cid_from_index(index_file):
    """从阿卡西索引测试CID"""
    import json
    from pathlib import Path

    index_path = Path(index_file)
    if not index_path.exists():
        print(f"索引文件不存在: {index_file}")
        return

    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)

    print(f"\n📋 测试索引中的 {len(index)} 个基因...")

    success = 0
    failed = 0

    for name, entry in index.items():
        cid = entry.get("cid")
        if not cid:
            continue

        print(f"\n[{name}]")
        ok, gw, result = test_ipfs_content(cid)
        if ok:
            success += 1
        else:
            failed += 1

    print(f"\n📊 IPFS内容测试结果: {success} 成功, {failed} 失败")
    return success, failed


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--cid":
        if len(sys.argv) < 3:
            print("用法: python gateway_diag.py --cid <CID>")
            return 1

        cid = sys.argv[2]
        ok, gw, result = test_ipfs_content(cid)
        return 0 if ok else 1

    if len(sys.argv) > 1 and sys.argv[1] == "--index":
        if len(sys.argv) < 3:
            print("用法: python gateway_diag.py --index <索引文件>")
            return 1

        index_file = sys.argv[2]
        test_cid_from_index(index_file)
        return 0

    print("""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
     🌌 Progenitor 星门阵列连通性诊断
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """)

    print("📡 测试星门通道...")
    results = []

    for i, gateway in enumerate(DEFAULT_GATEWAYS, 1):
        print(f"\n[{i}/{len(DEFAULT_GATEWAYS)}] 测试: {gateway[:60]}...")
        result = test_gateway(gateway)
        results.append(result)
        print(f"    {result['status']} ({result.get('response_ms', 0):.1f}ms)")

    print("\n\n📖 测试阿卡夏索引...")
    index_result = test_akashic_index()
    results.append(index_result)
    print(f"    {index_result['status']} ({index_result.get('response_ms', 0):.1f}ms)")

    print("\n\n🌐 测试IPFS网关...")
    ipfs_results = []
    for gateway in IPFS_GATEWAYS:
        result = test_gateway(gateway)
        ipfs_results.append(result)
        print(f"{gateway}: {result['status']} ({result.get('response_ms', 0):.1f}ms)")

    print("\n" + "=" * 80)
    print("📊 汇总")
    print("=" * 80)

    online = sum(1 for r in results if "✅" in r["status"])
    warning = sum(1 for r in results if "⚠️" in r["status"])
    failed = sum(1 for r in results if "❌" in r["status"])

    print(f"  ✅ 在线: {online}")
    print(f"  ⚠️ 受限: {warning}")
    print(f"  ❌ 失败: {failed}")
    print("=" * 80)

    ipfs_online = sum(1 for r in ipfs_results if "✅" in r["status"])
    print(f"\n🌐 IPFS网关: {ipfs_online}/{len(IPFS_GATEWAYS)} 在线")

    if online >= 2:
        print("\n🎉 星门阵列状态：良好！至少 2 个网关可用。")
    elif online == 1:
        print("\n⚠️ 星门阵列状态：降级运行，仅 1 个网关可用。")
    else:
        print("\n🔴 星门阵列状态：危急！所有网关均不可用。")

    return 0 if online >= 1 else 1


if __name__ == "__main__":
    sys.exit(main())
