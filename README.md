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
2. **去重** —— 按 `(host, port)`
3. **存活检测** —— 并发 TCP 连接测试，按延迟升序保留前 150 个

## 分工：为什么延迟排序要在 v2rayN 里做

GitHub Actions 的探测点在美国/欧洲机房，**不等于你在肯尼亚的网络环境**。所以本仓库只负责「筛掉死的、留下活的」，**真正的延迟排名请在 v2rayN 里跑「测试真连接延迟」**——那才是你本地视角。

## 已知限制

- **单源**：目前只吃 AutoMergePublicNodes。要多源可换用 [wzdnzd/aggregator](https://github.com/wzdnzd/aggregator)（重型，需配置 JSON / Telegram 凭证 / Gist token）。
- **TCP 存活 ≠ 代理可用**：端口通不代表节点真能转发。要更准得跑真实代理测试，成本高，故留给 v2rayN 本地测。
- **免费公共节点的安全性**：这些是**陌生人的服务器**，你全部流量都会经过它。**不要用它登录银行、邮箱、社交账号**，也不要用它做账号注册一类的敏感操作。

## 保持定时不失效

GitHub 会在仓库 **60 天无活动**后自动停掉 scheduled workflow。本工作流每 6 小时会提交一次变更，正常情况下不会触发该限制；若长期无变更导致停摆，手动跑一次 `workflow_dispatch` 即可恢复。

## 本地手动运行

```bash
python filter.py
```

输出 `sub.txt`（base64 订阅）与 `sub-plain.txt`（明文，方便肉眼检查）。只用标准库，无第三方依赖。
