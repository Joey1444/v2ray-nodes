#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""算候选源对**现有 sources.txt 合并池**的净新增独立 IP（默认美国，可换地区）。

这是选源的**正确判据**：有些仓库自身很大，但和已有源高度重复，加了只增加每轮耗时。
实测 `ermaozi/get_subscribe` 自身 15 个美国 IP，净新增 0；`free-nodes/clashfree`（16.9k★）
自身 40 个，净新增同样为 0。

用法：
    python tools/net_new.py <url> [<url> ...]
    python tools/net_new.py --region CN <url> [...]      # 按大陆 IP 评估
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import filter as F  # noqa: E402


def region_ips(url: str, idx):
    """返回 (该地区独立 IP 集合, 候选数)；失败抛异常。"""
    text = F.decode_sub(F.fetch(url))
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    seen, hit = set(), set()
    for line in lines:
        p = F.parse_node(line)
        if not p:
            continue
        host, port = p
        if not host or not port or not (0 < port < 65536) or not F.usable_host(host):
            continue
        seen.add((host, port))
        ip = F._direct_ip(host)
        if ip and not F._is_cdn(ip) and F.in_region(ip, idx):
            hit.add(host)
    return hit, len(seen)


if __name__ == "__main__":
    cands = sys.argv[1:]
    region = "US"
    if "--region" in cands:
        i = cands.index("--region")
        region = cands[i + 1].upper()
        del cands[i:i + 2]
    if not cands:
        print(__doc__.strip())
        sys.exit(1)

    idx = F.build_region_indexes([region])[region]

    base = set()
    for u, _scope in F.load_sources():
        try:
            ips, _ = region_ips(u, idx)
            base |= ips
        except Exception as e:
            print(f"  (基线源失败 {F.src_name(u)}: {str(e)[:40]})", file=sys.stderr)
    print(f"现有 sources.txt 合并后的 {region} 独立 IP：{len(base)}\n")

    print(f"{'候选源':<44}{'自身':>6}{'净新增':>8}   判据")
    print("-" * 74)
    acc = set(base)
    for u in cands:
        try:
            ips, total = region_ips(u, idx)
        except Exception as e:
            print(f"{F.src_name(u):<44}{'':>6}{'':>8}   ✗ {str(e)[:34]}")
            continue
        new = ips - acc
        verdict = "✓ 值得加入" if len(new) >= 3 else "✗ 重复，别加"
        print(f"{F.src_name(u):<44}{len(ips):>6}{len(new):>8}   {verdict}")
        acc |= ips
