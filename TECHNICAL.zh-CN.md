> 浏览器扩展更新：已增加授权 HTTP(S) URL 的 CloakBrowser 观察路径及独立观察证据。最新接口、权限和环境结论见 [CloakBrowser 与环境验收](reports/CloakBrowser-环境验收.md)。下文原始实施快照中的本地目标范围与未接入浏览器结论不覆盖此后续扩展。

> 这是原实现的完整技术说明，保留供查阅。日常用法和当前接入范围请先看 [简明使用说明](README.zh-CN.md)；历史验收记录不代表 Agent 当前已连接。

# REA 与 reverse-skill 本地统一系统

这是独立的项目级 Skill + stdio MCP 服务。统一入口、能力目录、阶段依赖、裁决规则和任务状态已经实现；不是插件或插件市场项目。

当前可执行验收路径是 **本地静态 REA 分析 → 同会话证据读取 → 报告**。52 条方法记录和 293 个真实发现的工具定义进入同一检索库；这不表示 293 个工具均已获准执行。其他桥接工具保留原始契约，缺少可验证目标句柄、副作用审查或实际引擎时明确拒绝执行。

## 在本机运行

```powershell
Set-Location 'C:\Users\Administrator\Documents\ChatGPT\TH Test\unified-re'
# 已安装完成；跑真实协议示例：
.\.venv\Scripts\python.exe -X utf8 scripts/demo.py
# MCP 客户端的启动命令（stdio 等待协议消息属正常行为）：
.\start.ps1
```

项目 Python 环境、固定 REA 6.5.0、本地 ONNX 模型和 SQLite 索引已就位。正常运行不用 API Key，不调用远端嵌入服务，不执行样本程序。

复制项目后恢复依赖可运行 `setup.ps1`。它使用带哈希的 `requirements.lock` 和 `package-lock.json`，不修改全局配置、不安装商业引擎、不清理已有目录。新机器需要调整 `backends.json` 及接入示例中的绝对路径；当前目录包含已审计的本机桥接路径，不是跨机器通用配置。REA-only 配置模板见 `examples/backends.rea-only.json`。

## 接入 AI 客户端

本子目录的 `.codex/config.toml` 已写好项目级 stdio 启动配置；`.agents/skills/unified-re/SKILL.md` 是唯一生效的总控。将 **unified-re 子目录**作为项目打开后，在新会话核实 `unified-re` 工具是否出现。当前聊天的既有工具目录不会因为写入配置而自动获得新服务，桌面新会话发现尚未作为验收事实。

其他 MCP 客户端可参考 `examples/mcp.json`。启动 Python 时使用 `-X utf8`，避免 Windows 默认 GBK 干扰中文。项目级接入语法按 [官方 MCP 配置文档](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) 和 [本地 Skill 发现文档](https://learn.chatgpt.com/docs/build-skills) 核对。

给 AI 的调用示例：

```json
{
  "tool": "task_plan",
  "arguments": {
    "request": "静态分析 JavaScript 程序的模块依赖，保留证据，不运行目标",
    "target_path": "C:\\Users\\Administrator\\Documents\\ChatGPT\\TH Test\\unified-re\\samples\\demo-app",
    "context": {"permissions": ["read_local"], "read_only": true}
  }
}
```

随后使用返回的 `id` 和 `revision`：

1. `stage_load` 获取当前阶段的一个主 Skill、补充说明和选定工具原始定义。
2. `stage_advance` 从已完成的辨型阶段进入分析。
3. `gateway_call` 调用 `rea::analyze_javascript_application`，参数是 **`input_path`**，不是任意改名后的 `path`。可用 `detail: "summary"` 保留完整证据并返回摘要。
4. 进入 evidence 阶段，用 `inspect_analysis_view` 的 `source: {kind: "retained-evidence", evidence_id: ...}` 读取该任务同一代次的父证据。
5. 进入 synthesis 阶段，`task_report` 提交 Markdown 与本任务证据 ID，再 `stage_advance` 完成并释放拥有的会话。

`scripts/demo.py` 是可执行的完整客户端示例，包含负例、切换目标、重连及进行中的真实 REA 取消验证。

## 统一 MCP 接口

| 接口 | 作用 |
|---|---|
| `capability_search` | 向量与 BM25 候选召回；不执行 |
| `task_plan` | 只读辨型、授权/约束检查、实时 REA 可用性与计划 |
| `stage_load` / `reference_load` | 当前阶段的方法与工具定义；专项参考按页读取 |
| `gateway_call` | 原始输入/输出契约、计划、目标、来源与状态门禁 |
| `stage_advance` / `task_report` | 阶段推进及证据关联交付 |
| `task_status` / `task_journal` | 持久状态与变化记录 |
| `task_revise` | 显式改计划、换目标或重连；递增修订号及会话代次 |
| `task_cancel` | 取消请求并关闭拥有的会话 |
| `backend_status` | 区分审计快照、协议发现、调用验证与当前会话 |

规划输出包含当前阶段、主/补充 Skill、工具与依赖、顺序、排除候选、备选触发条件和未解决事项。`context` 可表达 `target_type`、`required_skill`、`required_provider`、`excluded_providers`、`capability`、`no_commercial`、`read_only` 和 `required_effects`；不能通过这些字段绕过真实依赖和已审查适配器。

## 检索与增量更新

语义检索使用本地量化 `paraphrase-multilingual-MiniLM-L12-v2`、384 维 attention-mask mean pooling 和 L2 归一化。固定转换权重提交及每个文件的哈希见 `models/multilingual-minilm/manifest.json`；权重源哈希已与该提交的公开对象核验。用途描述独立嵌入，步骤/参考分块采用 256 token、32 token 重叠，避免长参考稀释用途召回。模型的官方训练默认长度为 128，本实现 256 是支持范围内的本地分块选择，没有性能优越性主张。

文档文本与工具功能、输入/输出概要被索引，完整原始 JSON Schema 保留在能力目录和 SQLite 元数据中。只读取指定清单中的 Skill 文档和 MCP 元数据；样本、任务结果、浏览器状态、`.env` 和凭据不进入检索库。

BM25 与向量分别排名，使用 RRF 融合排名；不直接相加不同检索器原始分数。余弦相似度不是校准置信度；0.36 是当前验收语料的启发式相关性下界，不承诺开放域准确率。无命中返回 `no_match`，有命中仍须裁决。

```powershell
# 只重建本地索引；不读取全盘文件或秘密：
.\.venv\Scripts\python.exe -X utf8 scripts/index.py
# 更新过已固定的来源或工具契约后，显式重新生成共享目录：
.\.venv\Scripts\python.exe -X utf8 scripts/build_catalog.py
.\.venv\Scripts\python.exe -X utf8 scripts/index.py
```

内容、源版本或模型指纹变化才重新嵌入相应记录；未变内容复用向量。目录版本变化未更新索引时返回 `stale_index`。`var/index-manifest.json` 记录目录、模型和更新数。更新上游必须先重新审计；不要将固定版本替换为 `latest`。

## 冲突与所有权

| 情况 | 裁决 |
|---|---|
| 同义/重复能力 | 归同一能力类别，保留来源；契约和行为未证实时不认定工具等价 |
| 互补步骤 | 依据共享目录的阶段依赖拓扑排序；循环或缺失依赖返回明确冲突 |
| 互斥主方法 | 每阶段一个主 Skill；补充说明不新增权限或工具 |
| MCP 同名 | 保留 `rea::list_strings`、`ghidra::list_strings` 等稳定来源标识及各自契约 |
| 同一后端 | 规范实例键的 SQLite 排他租约；不同别名需声明相同键，未知身份不强认同一或不同实例 |
| 硬约束矛盾 | 返回 `policy_conflict`；检索排名不能覆盖 |
| 近分/目标不明 | 先辨型；仍影响执行目标则 `needs_context` |
| 后端不可用 | 分为 `missing_dependency`、`unsupported`、暂时故障及信息不足；不静默替换结果 |

REA 每任务使用独立进程和持久 MCP 连接；同任务后端调用串行。前端 MCP 客户端支持并发发送取消请求。Ghidra/IDA 直连桥的当前契约不能在本环境证明所附着目标身份，未开放执行；元数据发现不等于可安全共享一个 GUI 数据库。资源锁只协调本服务的合作调用，不能控制绕开服务的外部程序。

## 状态、证据与安全边界

`var/tasks.sqlite` 保存任务、计划修订、会话代次、租约与事件。`var/results/` 保存完整原始 MCP 结果、错误标志、来源、参数、预定目标和证据引用；上游 `raw_result` 与 `normalized_result` 不被混成等价证据。目录目标哈希是本服务的有界文件清单哈希，上游图哈希具有不同语义，保留各自标识。

调用前后检查目标内容，输入按原始 Schema 校验，成功输出按原始输出 Schema 校验。计划之外的工具、目标路径、附加快照、外部引用或未知参数被拒绝。连接丢失后只保留历史事实；恢复需要 `task_revise`，旧代次引用不能复用。失败观察保留，不能因重试或换目标覆盖历史。

文件/目录是用户显式授权的本地输入；目录最多 2000 个允许类型文件、总计 64 MiB，不跟随符号链接或 junction，不支持任意扫描、目标执行、写入分析目标或主动网络行为。真实样本只做静态分析。原始专项脚本与相对资源保留，但不作为不受限 shell 工具暴露。

## 验证与限制

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --junitxml=reports/tests.xml
.\.venv\Scripts\python.exe -X utf8 scripts/evaluate_retrieval.py
.\.venv\Scripts\python.exe -X utf8 scripts/verify_rea.py
.\.venv\Scripts\python.exe -X utf8 scripts/demo.py
```

查看 `reports/验收报告.md`、`reports/审计记录.md` 及 JSON/XML 原始结果。纯裁决测试、协议故障 fixture 和真实 REA 验证分开记录。

原生引擎未配置、未审查或无法验证句柄的工具会拒绝执行。Hopper 当前主机不支持；没有安装商业分析器。索引召回只在给定用例验收，未校准普适置信度，也未测 Token 节省或性能提升。此实现是同一操作系统账号下的本地协调服务，不是隔离不可信用户的安全沙箱。

## 来源与目录

来源提交、包完整性、目录版本、模型指纹见 `SOURCES.lock.json`。REA、reverse-skill 保留 MIT；模型保留其 Apache-2.0 来源声明；第三方依赖各按原许可证，见 `THIRD_PARTY_NOTICES.md`。未打包 IDA、Hopper、JEB 等单独授权分析器。搬迁时复制整个项目；原始资源在技能发现目录外保存原有布局，避免上游多个 `SKILL.md` 被客户端自动发现为额外入口。

关键目录：`.agents/skills/unified-re/`（唯一入口、共享能力目录及规范化专项）、`resources/`（保持原始相对布局的上游脚本和引用）、`unified_re/`（检索/裁决/状态/调用）、`scripts/`（构建与真实验收）、`reports/`（证据）、`samples/`（自建无害样本）。没有修改全局 Skill 或 MCP 配置，没有删除原项目或用户既有产物。
