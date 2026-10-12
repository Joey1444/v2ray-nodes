#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""独立真实代理测试器：对一份节点列表逐个「穿节点取 generate_204」，报哪些真能用。

用途：不改订阅、不跑整条流水线，只诊断——例如怀疑某批节点到底能不能用时。
与主流程 `filter.py` 用的是同一套验证逻辑（同一份 build_outbound）。

Xray 位置：环境变量 XRAY_BIN，否则找 PATH 里的 xray，否则用 v2rayN 自带的。

用法：
    python tools/proxy_test.py <节点文件> [并发数]
    # 节点文件每行一个 URI（可直接用 sub-plain.txt）
"""
import concurrent.futures
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import filter as F  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return 1
    src = Path(sys.argv[1])
    lines = [l.strip() for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        print("文件里没有节点")
        return 1

    print(f"Xray: {F.XRAY_BIN}  |  测 {len(lines)} 个节点（穿节点取 generate_204）\n")
    ok = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=F.VERIFY_WORKERS) as ex:
        for i, (line, ms, err) in enumerate(
                ex.map(F.verify_node, enumerate([(l, 0) for l in lines])), 1):
            tag = line.split("://")[0]
            host = line.split("@")[-1].split("#")[0][:30] if "@" in line else line[:30]
            if ms is not None:
                ok += 1
                print(f"  [{i:>3}] ✓ {ms:>7.0f}ms  {tag:<7} {host}")
            else:
                print(f"  [{i:>3}] ✗ {err:<22} {tag:<7} {host}")
    print(f"\n真能当代理用：{ok}/{len(lines)}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
