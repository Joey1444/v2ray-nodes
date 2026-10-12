#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公共节点 → 去垃圾 → 存活检测 → (可选) 按国家过滤 → 输出可订阅列表

定位：**不自己爬源**。爬取复用 AutoMergePublicNodes 的产出（它自己每约 6 小时刷新一次），
本脚本只做上游没做的事——洗垃圾、验存活、验归属国。

国家判定用 **DB-IP Lite** 离线库（免费、无需 key、CC BY 4.0），按节点真实 IP 归属地判断，
**不看节点名**——名字可以随便写，骗不了 GeoIP。

输出：
  sub.txt         base64 订阅（v2rayN 直接订阅这个）
  sub-plain.txt   明文版，方便肉眼检查

只用标准库，无第三方依赖。
数据来源署名：IP geolocation by DB-IP (https://db-ip.com)
"""

import asyncio
import base64
import bisect
import datetime
import gzip
import ipaddress
import json
import sys
import urllib.request
from pathlib import Path

UPSTREAMS = [
    # 每个源都实测过；括号内是它对「美国独立 IP」池的净新增贡献（2026-10-12 实测）。
    # 合并去重后美国独立 IP：15（单源）→ 88。
    "https://raw.githubusercontent.com/chengaopan/AutoMergePublicNodes/master/list.txt",        # 基线 15
    "https://raw.githubusercontent.com/aiboboxx/v2rayfree/main/sub",                           # +36
    "https://raw.githubusercontent.com/free18/v2ray/main/v.txt",                               # +17
    "https://raw.githubusercontent.com/mahdibland/ShadowsocksAggregator/master/Eternity.txt",  # +14
    "https://raw.githubusercontent.com/peasoft/NoMoreWalls/master/list.txt",                   # +4
    "https://raw.githubusercontent.com/mfuu/v2ray/master/sub",                                 # +2
]

# 只要这个国家的节点；设为 None 则不做国家过滤
COUNTRY = "US"

GEOIP_URL = "https://download.db-ip.com/free/dbip-country-lite-{ym}.csv.gz"
GEOIP_CACHE = Path(__file__).resolve().parent / "_cache"

# 已知 anycast CDN 段：这些 IP 的位置取决于你从哪解析/连接，GeoIP 判定对它们没有意义。
# 实测踩过：域名 host（如 *.fly.dev / *.v.3dns.vip）在 GitHub 机房解析得到美国边缘 IP，
# 但在用户所在国解析会得到另一个边缘——所以「域名 host」一律不采信。
# 这张表会过期；宁缺毋滥，且只影响候选池大小，不影响正确性。
CDN_RANGES = [
    "199.232.0.0/16", "140.248.0.0/16", "151.101.0.0/16", "146.75.0.0/16",  # Fastly
    "104.16.0.0/13", "172.64.0.0/13", "173.245.48.0/20", "103.21.244.0/22",  # Cloudflare
]
CDN_NETS = [ipaddress.ip_network(c) for c in CDN_RANGES]

CONCURRENCY = 200   # 并发探测数
TIMEOUT = 4.0       # 单节点 TCP 连接超时（秒）
# 只用来兜住极端增长，不做筛选。刻意不靠这个值做排名：探测点在机房，
# 按它的延迟砍数量会误杀对本地好的节点。
MAX_NODES = 400

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


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "node-filter/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def decode_sub(raw: str) -> str:
    """订阅可能是「整体 base64」也可能是「明文多行」，两种都吃。"""
    raw = raw.strip()
    if not raw:
        return ""
    if "://" in raw[:200]:
        return raw
    try:
        return base64.b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8", "ignore")
    except Exception:
        return raw


def b64d(s: str) -> str:
    s = s.strip()
    try:
        return base64.b64decode(s + "=" * (-len(s) % 4)).decode("utf-8", "ignore")
    except Exception:
        return ""


# ---------- 节点解析 ----------

# 只认这些「真的是代理节点」的协议。
# 上游列表里混着大量 http(s):// 链接——那些是别的订阅地址，不是节点，
# 而它们同样能连上端口，不加白名单就会被当成"存活节点"混进来。
NODE_SCHEMES = {
    "vmess", "vless", "trojan", "ss", "ssr",
    "hysteria", "hysteria2", "hy2", "tuic", "snell", "anytls",
}


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


# ---------- GeoIP（DB-IP Lite） ----------

def _month_candidates(n: int = 3):
    """当月 → 往前推 n 个月（当月库可能还没发布）。"""
    d = datetime.date.today().replace(day=1)
    out = []
    for _ in range(n):
        out.append(d.strftime("%Y-%m"))
        d = (d - datetime.timedelta(days=1)).replace(day=1)
    return out


def _load_geoip_raw() -> bytes:
    GEOIP_CACHE.mkdir(exist_ok=True)
    for ym in _month_candidates():
        cached = GEOIP_CACHE / f"dbip-country-lite-{ym}.csv.gz"
        if cached.exists() and cached.stat().st_size > 1_000_000:
            print(f"[geoip] 用本地缓存 {cached.name}")
            return cached.read_bytes()
        try:
            raw = fetch_bytes(GEOIP_URL.format(ym=ym))
            cached.write_bytes(raw)
            print(f"[geoip] 下载 {ym}（{len(raw) / 1e6:.1f} MB）")
            return raw
        except Exception as e:
            print(f"[geoip] {ym} 不可用：{e}", file=sys.stderr)
    raise RuntimeError("DB-IP 库全部拉取失败")


def build_country_index(country: str):
    """返回 (v4_starts, v4_ranges, v6_starts, v6_ranges)，均为升序。"""
    text = gzip.decompress(_load_geoip_raw()).decode("utf-8", "ignore")
    v4, v6 = [], []
    for line in text.splitlines():
        p = line.split(",")
        if len(p) != 3 or p[2] != country:
            continue
        try:
            s, e = ipaddress.ip_address(p[0]), ipaddress.ip_address(p[1])
        except ValueError:
            continue
        (v4 if s.version == 4 else v6).append((int(s), int(e)))
    v4.sort()
    v6.sort()
    print(f"[geoip] {country} 段：IPv4 {len(v4)} · IPv6 {len(v6)}")
    return [r[0] for r in v4], v4, [r[0] for r in v6], v6


def _direct_ip(host: str):
    """只接受直连 IP。域名 host 一律返回 None——解析结果随位置变，判定不可靠。"""
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _is_cdn(ip) -> bool:
    return any(ip in n for n in CDN_NETS)


def in_country(ip, idx) -> bool:
    starts4, r4, starts6, r6 = idx
    starts, ranges = (starts4, r4) if ip.version == 4 else (starts6, r6)
    if not ranges:
        return False
    v = int(ip)
    i = bisect.bisect_right(starts, v) - 1
    return i >= 0 and v <= ranges[i][1]


# ---------- 存活探测 ----------

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

    if COUNTRY:
        idx = build_country_index(COUNTRY)
        kept, n_dom, n_cdn, n_other = [], 0, 0, 0
        for c in cand:
            ip = _direct_ip(c[1])
            if ip is None:
                n_dom += 1
                continue
            if _is_cdn(ip):
                n_cdn += 1
                continue
            if in_country(ip, idx):
                kept.append(c)
            else:
                n_other += 1
        print(f"[geoip] {len(cand)} 候选 → 域名(不可判) {n_dom} · CDN段 {n_cdn} · 非{COUNTRY} {n_other}"
              f" → 保留 {len(kept)}")
        cand = kept

    if not cand:
        print(f"[abort] 过滤后没有候选节点，保持原文件不动", file=sys.stderr)
        return 1

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
    scope = f"仅 {COUNTRY}" if COUNTRY else "不过滤国家"
    print(f"[write] {scope}；保留 {len(keep)} 个"
          f"（最快 {keep[0][1]:.0f}ms / 最慢 {keep[-1][1]:.0f}ms）")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
