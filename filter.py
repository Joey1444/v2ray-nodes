#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公共节点 → 去垃圾 → 存活检测 → 输出可订阅列表

定位：**不自己爬源**。爬取复用 AutoMergePublicNodes 的产出（它自己每约 6 小时刷新一次），
本脚本只做两件上游没做的事——洗掉垃圾条目、实测 TCP 存活并按延迟排序。

输出：
  sub.txt         base64 订阅（v2rayN 直接订阅这个）
  sub-plain.txt   明文版，方便肉眼检查

只用标准库，无第三方依赖。
"""

import asyncio
import base64
import ipaddress
import json
import sys
import urllib.request
from pathlib import Path

UPSTREAMS = [
    "https://raw.githubusercontent.com/chengaopan/AutoMergePublicNodes/master/list.txt",
]

CONCURRENCY = 200   # 并发探测数
TIMEOUT = 4.0       # 单节点 TCP 连接超时（秒）
MAX_NODES = 200     # 最多保留多少个（按探测点延迟升序）

ROOT = Path(__file__).resolve().parent

# Windows 默认按 GBK 读写，中文输出会乱码或抛错
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ---------- 抓取 ----------

def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "node-filter/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "ignore")


def decode_sub(raw: str) -> str:
    """订阅可能是「整体 base64」也可能是「明文多行」，两种都吃。"""
    raw = raw.strip()
    if not raw:
        return ""
    if "://" in raw[:200]:
        return raw
    try:
        pad = "=" * (-len(raw) % 4)
        return base64.b64decode(raw + pad).decode("utf-8", "ignore")
    except Exception:
        return raw


def b64d(s: str) -> str:
    s = s.strip()
    try:
        return base64.b64decode(s + "=" * (-len(s) % 4)).decode("utf-8", "ignore")
    except Exception:
        return ""


# ---------- 解析 ----------

def split_hostport(hp: str):
    """'1.2.3.4:80' / '[::1]:443' → (host, port)"""
    hp = hp.strip()
    if hp.startswith("["):
        host, _, port = hp[1:].partition("]:")
    else:
        host, _, port = hp.rpartition(":")
    host = host.strip().strip("[]")
    try:
        return host, int(port)
    except ValueError:
        return host, None


# 只认这些「真的是代理节点」的协议。
# 上游列表里混着大量 http(s):// 链接——那些是别的订阅地址，不是节点，
# 而它们同样能连上端口，不加白名单就会被当成"存活节点"混进来。
NODE_SCHEMES = {
    "vmess", "vless", "trojan", "ss", "ssr",
    "hysteria", "hysteria2", "hy2", "tuic", "snell", "anytls",
}


def parse_node(line: str):
    """返回 (host, port) 或 None。只做粗解析——端口和地址够用即可。"""
    line = line.strip()
    if "://" not in line:
        return None
    scheme, rest = line.split("://", 1)
    scheme = scheme.lower()
    if scheme not in NODE_SCHEMES:
        return None
    core = rest.split("#", 1)[0].split("?", 1)[0]

    if scheme == "vmess":
        obj = json.loads(b64d(core) or "{}")
        host, port = obj.get("add"), obj.get("port")
        try:
            return str(host).strip(), int(port)
        except (TypeError, ValueError):
            return None

    if scheme in ("ss", "ssr"):
        if "@" in core:
            _, hostport = core.rsplit("@", 1)
        else:
            hostport = b64d(core).rsplit("@", 1)[-1]
        return split_hostport(hostport.split("/", 1)[0])

    # vless / trojan / hysteria2 / tuic / anytls / snell …
    hostport = core.rsplit("@", 1)[-1] if "@" in core else core
    return split_hostport(hostport.split("/", 1)[0])


def usable_host(host: str) -> bool:
    """挡掉回环/内网/保留地址——公共列表里大量「广告占位节点」就靠这一条清掉。"""
    if not host:
        return False
    h = host.strip().strip("[]")
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return h.lower() not in ("localhost",) and not h.lower().endswith(".local")
    return not (ip.is_loopback or ip.is_private or ip.is_unspecified
                or ip.is_reserved or ip.is_multicast or ip.is_link_local)


# ---------- 探测 ----------

async def probe(host: str, port: int, sem: asyncio.Semaphore):
    async with sem:
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=TIMEOUT
            )
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return (loop.time() - t0) * 1000
        except Exception:
            return None


# ---------- 主流程 ----------

async def main() -> int:
    raw_lines = []
    for url in UPSTREAMS:
        try:
            text = decode_sub(fetch(url))
            got = [l.strip() for l in text.splitlines() if l.strip()]
            print(f"[fetch] {url}\n         → {len(got)} 行")
            raw_lines.extend(got)
        except Exception as e:
            print(f"[fetch] 失败 {url}: {e}", file=sys.stderr)

    if not raw_lines:
        print("[abort] 上游一条都没拿到，保持原文件不动", file=sys.stderr)
        return 1

    seen, cand = set(), []
    for line in raw_lines:
        parsed = parse_node(line)
        if not parsed:
            continue
        host, port = parsed
        if not host or not port or not (0 < port < 65536) or not usable_host(host):
            continue
        key = (host, port)
        if key in seen:
            continue
        seen.add(key)
        cand.append((line, host, port))
    print(f"[parse] 原始 {len(raw_lines)} 行 → 去重去垃圾后 {len(cand)} 个候选")

    sem = asyncio.Semaphore(CONCURRENCY)
    results = await asyncio.gather(*(probe(h, p, sem) for _, h, p in cand))
    alive = sorted(
        ((line, ms) for (line, _, _), ms in zip(cand, results) if ms is not None),
        key=lambda x: x[1],
    )
    print(f"[probe] 存活 {len(alive)} 个（超时 {TIMEOUT}s，并发 {CONCURRENCY}）")

    if not alive:
        print("[abort] 没有一个存活，保持原文件不动", file=sys.stderr)
        return 1

    keep = alive[:MAX_NODES]
    plain = "\n".join(line for line, _ in keep) + "\n"
    (ROOT / "sub-plain.txt").write_text(plain, encoding="utf-8")
    (ROOT / "sub.txt").write_text(
        base64.b64encode(plain.encode("utf-8")).decode("ascii"), encoding="utf-8"
    )
    print(f"[write] 保留 {len(keep)} 个（最快 {keep[0][1]:.0f}ms / 最慢 {keep[-1][1]:.0f}ms）")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
