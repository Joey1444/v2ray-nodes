# v2ray-nodes

定时抓取公共节点 → 去垃圾 → 实测 TCP 存活 → 输出一份**干净可订阅**的列表，供 v2rayN 订阅。

## 订阅地址

```
https://raw.githubusercontent.com/Joey1444/v2ray-nodes/main/sub.txt
```

在 v2rayN 里：**订阅 → 订阅设置 → 添加**，把上面的 URL 填进去，然后打开**自动更新间隔**（建议 6 小时）。

## 它做了什么

上游 [AutoMergePublicNodes](https://github.com/chengaopan/AutoMergePublicNodes)（NoMoreWalls 的 fork）每约 6 小时抓取合并一次公共节点，但产出里混着垃圾：

- **广告占位节点** —— 例如 `add: 127.0.0.1`、备注「防屏蔽机场引流君」这类回环地址条目，是给维护者的付费机场引流的。它们在客户端里可能被当成「最快节点」而自动选中，直接把你打回本地。
- **大量死节点** —— 公共列表里绝大部分端点已经连不上。

本仓库的 `filter.py` 只做上游没做的三件事：

1. **去垃圾** —— 挡掉回环 / 内网 / 保留地址（`127.0.0.1`、`10.x`、`192.168.x`、`0.0.0.0` 等）
2. **只认代理协议** —— 上游混着约 200 条 `http(s)://` 订阅地址（不是节点，但同样能连上端口），加协议白名单挡掉
3. **去重** —— 按 `(host, port)`
4. **按真实归属国过滤** —— 见下节。当前只保留 `US`
5. **TCP 存活检测** —— 并发连接测试
6. **真实代理验证** —— 起 Xray，**穿过节点取 `generate_204`**，只留真能用的（见下）

## 为什么必须做「真实代理验证」

**TCP 通 ≠ 能当代理用。** 公共免费节点里绝大多数是「服务器还在、端口开着，但配置或凭据已失效」。

实测：69 个 TCP 存活的美国节点里，**只有 22 个真能穿过它取到网页**（约 1/3）。不验证的话，客户端会满屏 `-1`——你根本不知道哪些能用。

验证方式与 v2rayN 的「真连接延迟」同路数：起 Xray 核、穿节点、取 `https://www.google.com/generate_204`。顺带会剔除两类**内核层面就用不了**的节点：

- **`allowInsecure`** —— Xray 26.2.6+ 已移除该参数，带它的配置内核起不来
- **明文 VLESS + 公网地址** —— Xray 明确拒绝：`vless without TLS or other encryption is prohibited unless the server address is a private IP or domain`

## 上游源

**因为节点名基本是假的。** 实测同一批节点：

```
名字标 🇫🇷 法国     →  真实 IP 在美国
名字标 🇩🇪 德国     →  真实 IP 在美国
名字标 🇵🇱 波兰     →  真实 IP 在美国
同一个域名 ruot.ayucloudservices.nl 被挂上 JP / SG / HR 四个不同国家名
```

所以国家判定用 **DB-IP Lite** 离线库（免费、无需 key，署名见文件头）按**真实 IP** 判断。

另外两类 host **一律丢弃**，因为 GeoIP 对它们没有意义：

- **域名 host**（`*.fly.dev`、`*.v.3dns.vip` 等）——解析结果**随你所在位置变**。在 GitHub 机房解析得到美国边缘 IP，你在别处解析得到的是另一个边缘。
- **已知 anycast CDN 段**（Fastly / Cloudflare 等）——同上，IP 位置不由地理决定。

**已知局限**：这些 IP 是**美国的服务器**，但代理是否真从美国出口，只有实际连一次看出口 IP 才能确认。本仓库不做这一步（成本高），最终以客户端实测为准。

## 分工：为什么不在 Actions 里排名

GitHub Actions 的探测点在美国/欧洲机房，**不等于你在肯尼亚的网络环境**。实测同一批节点：runner 报「最快 6ms」，本机跑是「最快 16ms」——机房到机房的数字对你没有参考价值。

所以本仓库**只负责筛掉死的、留下活的，不做排名**；**排序请在 v2rayN 里跑「测试真连接延迟」**，那才是你本地视角。

## 上游源

6 个源合并，各源贡献已实测（括号内为对「美国独立 IP」池的**净新增**，2026-10-12）：

| 源 | 净新增 |
|---|---|
| [AutoMergePublicNodes](https://github.com/chengaopan/AutoMergePublicNodes) | 基线 15 |
| [aiboboxx/v2rayfree](https://github.com/aiboboxx/v2rayfree) | +36 |
| [free18/v2ray](https://github.com/free18/v2ray) | +17 |
| [mahdibland/ShadowsocksAggregator](https://github.com/mahdibland/ShadowsocksAggregator) | +14 |
| [peasoft/NoMoreWalls](https://github.com/peasoft/NoMoreWalls) | +4 |
| [mfuu/v2ray](https://github.com/mfuu/v2ray) | +2 |

**合并去重后美国独立 IP：15（单源）→ 88**，实测存活 68 个。选源判据是「净新增」而非「自身大小」——有些源自身看着大，但和已有源高度重复（如 `ermaozi/get_subscribe` 自身 15 个美国 IP，净新增 0），加进来只增加耗时。

### 源清单在 `sources.txt`，脚本自己体检

源清单是**数据文件**而非代码，每行一个 URL，`#` 开头为注释。每轮运行都会：

1. 逐个源体检，把「有效节点行数」和连续成功/失败次数记进 `sources-status.json`
2. **连续失败 5 轮 → 自动把该源注释掉**（写成 `# DISABLED auto <url>`，改动在 git diff 里可见，随时手工恢复），避免每轮都为死源白等

补源时：先用 `sources.txt` 注释区里记的「已排查但不采用」清单排除已知无效项，再加新源。

## 为什么跑在 GitHub Actions 而不是本机 n8n

官方文档明确：**「The use of standard GitHub-hosted runners is free: In public repositories.」** 本仓库是公开仓库，**Actions 分钟数免费且不限**，唯一的硬限额与本项目无关（单 job 6 小时、单次运行 35 天——本流程约 50 秒）。

n8n 反而更差：需要你本机常开，且多一份要维护的服务。**只有在仓库转私有、或需要碰本机文件时才该换。**

## 已知限制

- **扩源已到天花板**：又筛了 12 个知名仓库（含 16.9k★ 的 `free-nodes/clashfree`、多个 Telegram 采集器），**净新增为 0**——它们聚合的是同一批上游。公开生态的美国 IP 池稳定在 ~88，其中真能用的约 22。想再涨只能换路子（自建节点 / 放宽地区 / 付费源）。
- **源会失效**：公开仓库可能停更、改名（实测多个直接 404）或被 GitHub 封（`barry-far/V2ray-Configs` 因 ToS 被封）。单个源失败不影响整体（逐个 try/except）。补源照上表方法**先测净新增**，别只看仓库大小。
- **验证是在机房做的**：Actions 探测点在美国，**机房能通 ≠ 你在肯尼亚能通**。流水线能砍掉大部分死节点，最终仍建议在客户端本地再测一次。
- **归属国只是"服务器在美国"**：GeoIP 判的是 IP 归属，不保证流量真的从美国出口。
- **免费公共节点的安全性**：这些是**陌生人的服务器**，你全部流量都会经过它。**不要用它登录银行、邮箱、社交账号**，也不要用它做账号注册一类的敏感操作。

## 保持定时不失效

GitHub 会在仓库 **60 天无活动**后自动停掉 scheduled workflow。本工作流每 6 小时会提交一次变更，正常情况下不会触发该限制；若长期无变更导致停摆，手动跑一次 `workflow_dispatch` 即可恢复。

## 本地手动运行

```bash
python filter.py
```

输出 `sub.txt`（base64 订阅）与 `sub-plain.txt`（明文，方便肉眼检查）。只用标准库，无第三方依赖。
