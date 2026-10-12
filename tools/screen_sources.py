#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""体检候选源：拉一个订阅地址，报「候选节点数 / 美国独立 IP 数」。

补源时先跑这个，再跑 net_new.py 看净新增——**只看仓库大小会选到高度重复的源**。

用法：
    python tools/screen_sources.py <url> [<url> ...]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import filter as F  # noqa: E402


def screen(url: str):
    idx = F.build_country_index("US")
    try:
        text = F.decode_sub(F.fetch(url))
    except Exception as e:
        return f"拉取失败 {str(e)[:40]}"
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines or "://" not in " ".join(lines[:3]):
        return f"非节点格式（{len(lines)} 行）"
    seen, us = set(), set()
    for line in lines:
        p = F.parse_node(line)
        if not p:
            continue
        host, port = p
        if not host or not port or not (0 < port < 65536) or not F.usable_host(host):
            continue
        seen.add((host, port))
        ip = F._direct_ip(host)
        if ip and not F._is_cdn(ip) and F.in_country(ip, idx):
            us.add(host)
    return f"候选 {len(seen):>4} · 美国独立 IP {len(us):>3}"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__.strip())
        sys.exit(1)
    print(f"{'源':<40} 结果")
    print("-" * 70)
    for u in sys.argv[1:]:
        name = F.src_name(u)
        print(f"{name:<40} {screen(u)}")
