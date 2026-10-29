# v2ray-nodes

[![update-nodes](https://github.com/Joey1444/v2ray-nodes/actions/workflows/update.yml/badge.svg)](https://github.com/Joey1444/v2ray-nodes/actions/workflows/update.yml)

定时抓取公开节点，去垃圾 → 按 IP 归属地分地区 → **真实代理验证**，每个地区输出一份可以直接订阅的干净列表。

每份列表里的**每一个节点都验证过能真正代理**（不是"端口通"）。

## 订阅地址

| 地区 | 订阅地址 | 现状 |
|---|---|---|
| 美国 | `https://raw.githubusercontent.com/Joey1444/v2ray-nodes/main/sub-us.txt` | 通常几十个 |
| 香港 / 台湾 | `https://raw.githubusercontent.com/Joey1444/v2ray-nodes/main/sub-hktw.txt` | 上游池子小，通常个位数 |
| 中国大陆 | `https://raw.githubusercontent.com/Joey1444/v2ray-nodes/main/sub-cn.txt` | 公开 socks 代理，通常个位数，存活以小时计 |

**v2rayN**：订阅 → 订阅分组设置 → 添加 → 地址填上面的 URL → 自动更新间隔 `360`（分钟）→ 更新订阅。
想要几个地区就加几条订阅，客户端里按分组切换。

老地址 `.../main/sub.txt` 仍然只装**美国**节点，已订阅的不用改。

其它客户端只要支持 base64 订阅即可使用。

## 为什么需要它

公开免费节点列表最大的问题不是数量少，而是**绝大多数根本不能用**——服务器还在、端口也开着，但配置或凭据早已失效。

实测：TCP 存活的节点里，**只有一半左右真能穿过它取到网页**。直接订阅原始列表，客户端会满屏 `-1`，你无法分辨哪些能用。

本仓库只做一件事：把噪音去掉，给你一份验证过的短列表。

## 工作流程

| 步骤 | 做什么 |
|---|---|
| **采集** | 7 个上游源合并去重（6 个通用 + 1 个只喂大陆）。清单在 [`sources.txt`](sources.txt)，行首写 `[cn]` 可把该源限定给某个地区；每轮自动体检，连续失败 5 轮自动停用 |
| **清洗** | 剔除回环 / 内网 / 保留地址与非节点链接；只保留代理协议（vmess / vless / trojan / ss / hysteria2 …） |
| **归属过滤** | 用 **DB-IP** 离线库判**真实 IP** 的归属地（国家/地区），再按地区分组 —— **不看节点名，实测名字基本是假的** |
| **粗筛** | 并发 TCP 存活检测 |
| **终验** | 起 Xray、**穿节点取 `generate_204`** —— 与 v2rayN 的「真连接延迟」同路数，只留真能用的。大陆那份改成打 `https://www.baidu.com`（google 在大陆不通）——**必须用 HTTPS**，公开代理池里大量代理只转发明文，用 HTTP 验会全部假通过 |

每 6 小时运行一次，结果提交回本仓库。

## 配置

`filter.py` 顶部：

| 项 | 说明 |
|---|---|
| `REGIONS` | 地区分组：每组 = 国家码列表 + 一份输出文件 + 一个验证地址。**加一个地区就是加一行** |
| `DISABLE_AFTER = 5` | 源连续失败多少轮后自动停用 |
| `VERIFY_TIMEOUT` / `VERIFY_WORKERS` | 终验的超时与并发 |

定时：`.github/workflows/update.yml` 里的 `cron`（当前 `23 */6 * * *`）。

## 维护工具

改源或排查问题时用，不影响主流程：

| 工具 | 用途 |
|---|---|
| `python tools/screen_sources.py <url...>` | 体检候选源：报候选数与指定国家（`--region CN`，默认 US）的独立 IP 数 |
| `python tools/net_new.py <url...>` | 算候选源对现有源的**净新增**（同样支持 `--region`）—— **这才是选源的判据** |
| `python tools/proxy_test.py <节点文件>` | 独立验证器：逐节点穿代理取 `generate_204` |

## 已知限制

- **终验在机房做**：Actions 探测点在美国，**机房能通 ≠ 你本地能通**。流水线能砍掉大部分死节点，最终仍建议在你自己的网络里再测一次。
- **归属地只保证"服务器在美国"**：GeoIP 判的是 IP 归属，不保证流量真的从美国出口。
- **大陆那份只有个位数，而且都是公开 socks 代理**：翻墙订阅里没人分享大陆节点（大陆出口翻不了墙），能拿到大陆 IP 的只有公开代理池。实测 2026-10-29：proxifly 的 CN 文件 685 条，其中 541 条 socks、端口可达 180、**真能穿 HTTPS 的只有 4 个**。这批节点存活以小时计、带宽很低；v2rayN 只认 `socks://` 不认 `http://`，所以只输出 socks 条目。**要稳定的大陆 IP 只能自建或买回国服务。**
- **港台池子也小**：709 个候选里港台合计约 20 个，终验后通常只剩个位数——要更多只能自己搭。
- **扩源已到天花板**：另筛过 12 个知名仓库（含 16.9k★ 的 `free-nodes/clashfree`），净新增为 **0** —— 它们聚合的是同一批上游。公开生态的美国 IP 池稳定在 ~88，终验后能用的在 20~40 之间波动。想再涨只能换路子（自建节点 / 付费源）。
- **源会失效**：公开仓库可能停更、改名或被封。`sources.txt` 注释区记着**已排查但不采用**的清单，避免重复劳动。

## 安全提示

**免费公共节点是陌生人的服务器，你全部流量都会经过它。**

不要用它登录银行、邮箱、社交账号，也不要用它做账号注册一类的敏感操作。

大陆那份是公开 socks 代理（多数是被滥用的开放代理），风险同类，**更不要拿它登录任何账号**。

## 运行载体

跑在 **GitHub Actions**（官方说明：*"The use of standard GitHub-hosted runners is free: In public repositories."*）。本仓库公开，**分钟数免费不限**；单次运行约 50 秒，不需要任何本机常驻服务。

## 署名

IP geolocation by [DB-IP](https://db-ip.com) (CC BY 4.0)。
