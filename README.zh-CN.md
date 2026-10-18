# unified-re：使用说明

让 AI 用中文或英文查找逆向方法和工具，先裁决依赖与冲突，再按阶段分析本地样本。

## 直接使用

本机已添加 **Codex 和 Pi 用户全局配置**。重启 Codex、重新启动 Pi，在任意项目中使用：

```text
请使用 unified-re，调用 capability_search 做联合语义检索。
不运行程序，帮我选择梳理 JavaScript 脚本模块依赖的方法和工具。
先列出候选及选择原因，暂不分析文件。
```

要完成分析，把目标绝对路径写清楚：

```text
请使用 unified-re 分析这个允许读取的本地目标：C:/path/to/sample
先调用 task_plan 做检索和规划，再按计划完成只读静态分析，给出证据和限制。
不要运行目标程序。
```

Codex 可以用 `$unified-re` 指定 Skill；Pi 可以用 `/skill:unified-re`。已有 reverse-skill 保留，明确指定 unified-re 可避免由旧入口接管。

## 如何触发语义检索

| 调用 | 作用 |
|---|---|
| `capability_search` | 本地多语言语义向量 + BM25，返回候选，不执行分析 |
| `task_plan` | 自动检索，再检查目标、依赖、权限、可用性和冲突 |
| 普通聊天描述 | Agent 可能自动选用；是否调用需看工具记录 |

无需另外开启开关。看到 `capability_search` 返回 `candidates`、`model_fingerprint`，或计划返回 `retrieval_provenance`，才说明实际运行了检索。Pi 的工具名带 `mcp__unified-re__` 前缀。

没有适用能力会返回 `no_match`；缺少依赖会明确提示。相似度不是结论可信度。

## 在另一台 Windows 电脑安装

需要 Python 3.13、uv、Node.js/npm。模型首次下载需要网络，后续检索在本地运行，不需要 API Key。

```powershell
cd C:/path/to/unified-re
./setup.ps1
# 可选：全局配置 Codex 和 Pi
./.venv/Scripts/python.exe -X utf8 scripts/install_agents.py
# 验证两份全局启动配置的真实 MCP 调用
./.venv/Scripts/python.exe -X utf8 scripts/verify_agents.py
```

全局安装脚本要求 Pi 已有 `pi-mcp-bridge` 扩展；它不安装 Pi 或另造插件。配置位置：

- Skill：`~/.agents/skills/unified-re`，链接到本项目的唯一 Skill 目录，Codex 与 Pi 共用。
- Codex MCP：`~/.codex/config.toml` 的 `mcp_servers.unified-re`。
- Pi MCP：`~/.pi/agent/extensions/pi-mcp-bridge/mcp-servers.json` 的 `unified-re`。

脚本只增加 unified-re，先备份已有配置；相同配置重复运行不会重复添加，发现同名异配置会停止。其他 Skill/MCP 保留。移动或删除本项目会使全局入口失效；撤销时只移除新增的 unified-re 注册和目录链接，勿删除链接目标。

也可参照 [examples/mcp.json](examples/mcp.json) 手动接入支持 stdio 的客户端，替换其中的路径。服务启动脚本会定位项目根目录，与客户端当前工作目录无关。后端默认使用可移植的 REA 配置；可用不纳入 Git 的 `backends.json` 增加本机后端。

## 验证与范围

```powershell
./.venv/Scripts/python.exe -X utf8 -m pytest -q
./.venv/Scripts/python.exe -X utf8 scripts/verify_rea.py
./.venv/Scripts/python.exe -X utf8 scripts/demo.py
```

已验证真实 REA 的本地 JavaScript 和归档样本流程。293 个工具定义可检索，其中 17 个 REA 操作已映射执行契约；其余元数据不代表已经可以执行。原生分析引擎尚未完成真实执行验收。**未接入 CloakBrowser。**

截至 2026-10-19，两份全局配置已完成真实协议和检索调用验证；已经打开的 GUI 聊天需要重载，不能据此宣称旧会话已更新工具。全局接入步骤符合 [Codex 官方 MCP 文档](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) 和 [Skill 发现规则](https://learn.chatgpt.com/docs/build-skills)。

按需查看：[完整技术说明](TECHNICAL.zh-CN.md)、[原实施验收](reports/验收报告.md)、[来源版本快照](SOURCES.lock.json)、[许可证与来源](THIRD_PARTY_NOTICES.md)。来源锁中的路径、代码摘要和原验收结果是历史快照，当前提交的变化及验证另见 [全局接入与发布记录](reports/全局接入与发布-2026-10-19.md)。
