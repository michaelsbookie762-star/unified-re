"""Generate source pins and Chinese handoff reports from observed evidence."""
import importlib.metadata
import json
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unified_re.common import ROOT, SKILL, digest, now, read_json, write_json


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args]).decode("utf-8").strip()


def main():
    catalog = read_json(SKILL / "catalog.json")
    discovery = read_json(ROOT / "reports/discovery.json")
    index = read_json(ROOT / "var/index-manifest.json")
    semantic = read_json(ROOT / "reports/retrieval-evaluation.json")
    rea = read_json(ROOT / "reports/rea-verification.json")
    gateway = read_json(ROOT / "reports/gateway-verification.json")
    launcher = read_json(ROOT / "reports/launcher-verification.json")
    suite = ET.parse(ROOT / "reports/tests.xml").getroot().find("testsuite")
    tests = {key: int(suite.attrib.get(key, 0)) for key in ("tests", "failures", "errors", "skipped")}
    assert not tests["failures"] and not tests["errors"]
    assert semantic["passed"] and rea["passed"] and gateway["passed"] and launcher["passed"]
    assert catalog["version"] == index["catalog_version"]
    entrypoints = list((ROOT / ".agents/skills").rglob("SKILL.md"))
    assert entrypoints == [SKILL / "SKILL.md"]
    resources = read_json(SKILL / "resource-manifest.json")
    assert digest(resources) == catalog["resources_digest"]
    assert all(digest((ROOT / f["path"]).read_bytes()) == f["sha256"] for f in resources)

    npm = read_json(ROOT / "package-lock.json")["packages"]["node_modules/rea-agents"]
    original = Path(r"C:\Users\Administrator\.codex\reverse-skill")
    code_files = [*ROOT.glob("unified_re/*.py"), *ROOT.glob("scripts/*.py"), *ROOT.glob("tests/*.py"), ROOT / "start.ps1", ROOT / "setup.ps1", ROOT / "pyproject.toml", ROOT / "requirements.lock", ROOT / "uv.lock", ROOT / "package-lock.json", ROOT / ".codex/config.toml", SKILL / "SKILL.md"]
    code = [{"path": p.relative_to(ROOT).as_posix(), "sha256": digest(p.read_bytes())} for p in sorted(code_files)]
    native = discovery["sources"]["rea"]["session"]["structuredContent"]["result"]["analysis_provider_candidates"]
    source_lock = {"schema_version": 1, "recorded_at": now(), "workspace": str(ROOT), "original_workspace": str(ROOT.parent), "upstream": catalog["sources"], "original_reverse_skill": {"path": str(original), "commit": git(original, "rev-parse", "HEAD"), "status": git(original, "status", "--short")}, "runtime": {"python": platform.python_version(), "node": subprocess.check_output(["node", "--version"]).decode().strip(), "mcp_python": importlib.metadata.version("mcp"), "onnxruntime": importlib.metadata.version("onnxruntime"), "numpy": importlib.metadata.version("numpy"), "tokenizers": importlib.metadata.version("tokenizers"), "rea": {"version": npm["version"], "npm_integrity": npm["integrity"], "source_commit": None, "note": "Docs/source snapshot and published npm integrity are pinned independently; no unproven commit-to-package identity"}}, "catalog": {"version": catalog["version"], "skills": len(catalog["skills"]), "tool_definitions": len(catalog["tools"]), "contract_reviewed_tool_count": sum(t["reviewed"] for t in catalog["tools"]), "resource_count": len(resources), "resources_digest": catalog["resources_digest"]}, "model": index["model"], "embedding_pipeline": index["pipeline"], "model_fingerprint": index["model_fingerprint"], "index_representation": index["representation"], "code_files": code, "code_tree_digest": digest(code), "verification": {"tests": tests, "retrieval_cases": len(semantic["cases"]), "real_rea_checks": len(rea["checks"]), "real_gateway_checks": len(gateway["checks"])}, "limits": ["no real native engine execution verified", "direct shared GUI/database/browser/device bindings remain unverified", "fresh Codex desktop session discovery unverified", "retrieval signals are not calibrated confidence", "cooperative locks are not an OS security sandbox"]}
    for name in ("rea", "reverse-skill"):
        path = ROOT / "upstream" / name
        assert git(path, "rev-parse", "HEAD") == catalog["sources"][name]["commit"]
        source_lock["upstream"][name]["working_tree_status"] = git(path, "status", "--short")
    source_lock["verification"]["powershell_launcher_verified"] = launcher["passed"]
    source_lock["index_file_sha256"] = digest((ROOT / "var/index.sqlite").read_bytes())
    write_json(ROOT / "SOURCES.lock.json", source_lock)

    day = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    upstream_rows = "\n".join(f"| {key} | `{value.get('commit', value.get('version', 'unknown'))}` | {value['license']} |" for key, value in catalog["sources"].items())
    provider_rows = "\n".join(f"| {p['provider']['id']} | {p['availability']['status']} | {p['availability'].get('code')} |" for p in native)
    source_rows = "\n".join(f"| {name} | {value.get('status')} | {len(value.get('tools', []))} | {value.get('endpoint_tcp', '未探测/无独立端口')} | {value.get('tool_call_verified', False)} |" for name, value in discovery["sources"].items())
    audit = f"""# 只读审计与合并决策记录

日期：{day}，Asia/Shanghai。MCP 快照时间：`{discovery['observed_at']}`。事实以所列证据层为限。

## 已验证事实

- 实际任务工作区为 `{ROOT.parent}`。初始 Git 为尚无提交的 master，已有 `.codex-tools/`、`.playwright-mcp/` 和 `output/` 未跟踪产物；未覆盖或删除。本实现全部位于 `unified-re/`。
- 原 reverse-skill 位于 `{original}`，仍为 `7e2097fd90d25c2f976f6eba26d6c00aa88051df`，既有未跟踪 `cloakbrowser/` 保留。上游较新版本另外获取，不对原检出执行 pull、reset 或清理。
- 初始在已核查的全局 npm、用户 Skill 根和全局 MCP 注册中未发现 REA；这不是对全盘所有未知目录的否定证明。随后只安装了项目本地 `rea-agents@6.5.0`。
- 初始审阅用户提供的全局 AGENTS 指令；实际工作区及已核查父目录当时没有磁盘 AGENTS.md。两上游 AGENTS、文档、相关源码和真实 tools/list 契约均已纳入审计，未运行其自动全局配置步骤。

采用的源码/文档版本：

| 项目 | 提交 | 许可证 |
|---|---|---|
{upstream_rows}

运行包单独固定为 REA 6.5.0，npm integrity 为 `{npm['integrity']}`。不把仓库 main 提交直接宣称为该 npm 包的构建提交；运行接口按真实 MCP 发现结果核对。

## 工具层与引擎层

| 源 | 协议审计状态 | 发现的工具数 | TCP 观察 | 审计时工具调用成功 |
|---|---|---:|---|---|
{source_rows}

这里的协议初始化、工具定义、端口响应和分析引擎可用性是独立事实。REA 的真实静态样本调用见单独验收。Ghidra 直连端口后来出现 TCP 响应，但没有验证该端口确为 Ghidra、也没有读取用户已打开目标；不能将它标为已打通的 Ghidra 分析器。Reqable 的 TCP 响应同样不能替代目标工具调用。IDA 桥初始化失败，原因未伪造为“确定没有安装”。

REA `binary_session` 的原生候选报告：

| 提供方 | 可用性 | 原因码 |
|---|---|---|
{provider_rows}

`tools/list` 中仍包含不可用工具；本实现扩展 `tool_availability.groups` 并核对名称并集，不能用注册或排名替代该检查。PentestSwarm 返回工具目录时产生不合法 JSON-RPC 消息，标为 `protocol_partial`，未算执行验收成功。

Burp 桥的实现会读取令牌文件，未启动；Xquik、Anything Analyzer 的凭据依赖未触碰。没有读取 .env、浏览器登录状态、保存密码、验证码或密钥内容。常规运行仅从显式允许的环境变量读取配置，不记录其值。

## 方法、路由、脚本、MCP 与引擎的区分

| 层 | 合并结果 |
|---|---|
| 方法论 | {len(catalog['skills'])} 条规范化方法记录；原始专项作为有版本资源保留 |
| 调度与规则 | 一个生效的 SKILL.md、同一 catalog.json、阶段拓扑与硬门禁 |
| 脚本与引用 | {len(resources)} 个清单资源，保留原有相对布局和哈希，位于发现目录外 |
| MCP 工具 | {len(catalog['tools'])} 个真实发现的定义，稳定 `source::tool`，保留完整参数/返回 Schema |
| 执行适配 | {source_lock['catalog']['contract_reviewed_tool_count']} 个 REA 操作完成契约映射；是否执行仍看具体目标与实时依赖；其余为未审查声明 |
| 分析引擎 | 静态 JS/归档真实验证；原生引擎未实测，桥的存在不等于引擎能力 |

## 规则冲突与采用的统一契约

| 原规则冲突 | 合并决策 |
|---|---|
| reverse-skill 的读后自动配置/安装与本任务的只读审计、项目隔离 | 不执行自动配置；不写全局配置；仅保留所需方法和资源 |
| 旧路由的泛逆向/IDA 强制匹配与 REA 的具体目标分流 | 先辨型和检查真实依赖；不强制 IDA，也不将普通源码开发误交给 REA |
| 默认兜底最接近模块与用户要求无匹配 | 返回 no_match / unsupported，不强塞模块 |
| CTF/先例中的默认授权模型与明确目标/权限 | 只接受用户当前任务授权；参考文本不能自动赋权 |
| 多总控、下一步菜单与单主 Skill 连续执行 | 一个生效总控，每阶段一个主方法；真正的目标歧义才待补上下文 |
| 失败后换工具与 REA 不可替换的具体提供方/证据语义 | 显式修订计划、会话代次与引用；不静默混合结果 |
| Ghidra/IDA 注释或 GUI 操作与只读目标范围 | 未列入当前计划的变更一律拒绝；不保存、关闭用户 GUI 数据库 |

## 设计选择与未验证项

本地 384 维量化多语言模型 + BM25，分别排名后 RRF；用途向量独立于长篇步骤，步骤仍分块索引。该表示修复了加入参考文档后低词面重合任务的召回退化。相似度没有校准为置信度。

SQLite 保存索引、任务、事件与排他租约。REA 任务使用独占进程和持久连接。共享实例别名必须配置相同资源键；外部进程绕开协调器不受此锁控制。目标不明或实例身份无法核对时停止，不推断可互换。

REA-owned Ghidra 条件规划与固定提供方绑定有契约/策略测试，但本机当前没有该原生端到端验证；不将模拟的 available 元数据当作真实引擎证据。Ghidra/IDA 直连、JSHook 浏览器状态、数据库连接、设备和凭据服务没有实际目标执行验收。源码/脚本保留不等于所有依赖已安装。

## 官方依据与源码入口

- [REA 官方仓库](https://github.com/morluto/rea)，固定源码中的 `docs/mcp-contracts.md`、`docs/ghidra-provider.md`、`src/contracts/` 和专项 references。
- [reverse-skill 官方仓库](https://github.com/zhaoxuya520/reverse-skill)，固定版本的 AGENTS.md、RULES.md、routing.json 和各专项。
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v2.3.0)，当前 stdio、结构化输出、取消契约已核对。
- [模型卡与 mean pooling](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2)，[固定 ONNX 转换提交](https://huggingface.co/Xenova/paraphrase-multilingual-MiniLM-L12-v2/tree/2c4055b12046f11709e9df2c122e59ffbdc2f900)。
- [Codex MCP 项目配置](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)，[Skill 发现规则](https://learn.chatgpt.com/docs/build-skills)。新桌面会话是否实际发现本项目配置尚未验证。
"""
    (ROOT / "reports/审计记录.md").write_text(audit, encoding="utf-8")

    acceptance_rows = "\n".join(f"| {c['check']} | 通过 |" for c in gateway["checks"])
    verification = f"""# 实施与验收报告

日期：{day}，Asia/Shanghai。代码与资源版本见 `../SOURCES.lock.json`；模型及索引元数据见 `../var/index-manifest.json`。

## 交付与已验证结果

- 一个被发现的主 Skill，{len(catalog['skills'])} 条方法记录，{len(catalog['tools'])} 个工具元数据，{len(resources)} 个有来源和哈希的保留资源。
- 一个真实 stdio MCP 服务，统一检索、规划、阶段加载、参数/结果验证、任务状态、取消和工具调用。
- 自动化测试：{tests['tests']} 项，失败 {tests['failures']}，错误 {tests['errors']}，跳过 {tests['skipped']}。证据：`tests.xml`。
- 真实多语言检索用例：{len(semantic['cases'])} 项，包括中英文、低关键词重合表达和三个无关请求。证据：`retrieval-evaluation.json`。仅代表这些用例，不是成功率估计。
- 真实官方 REA MCP 检查：{len(rea['checks'])} 项。完成 JS 模块/导入关系、同会话保留证据、归档打开/活动目标读取/关闭、真实错误以及新连接引用失效。证据：`rea-verification.json` 及 `rea-*-raw.json`。
- 客户端 → 统一 MCP → 官方 REA 的联合检查：{len(gateway['checks'])} 项。证据：`gateway-verification.json`、`gateway-tools.json` 和 `gateway-transcript.json`。
- PowerShell `start.ps1` 已通过真实 MCP 初始化、12 项工具发现及状态调用；证据：`launcher-verification.json`。

## 核心验收对应关系

| 要求 | 结果与证据 |
|---|---|
| 真正联合语义与关键词召回 | 本地 ONNX 推理、独立用途向量与步骤分块、BM25、RRF；同库含方法与完整工具元数据 |
| 无适用能力 | 三个无关任务返回 no_match；不执行最接近结果 |
| 同义与等价 | 实际同名工具保留来源、Schema 和行为差异；仅能力重合不认定可替换 |
| 互补与互斥 | 共享阶段依赖拓扑、单主 Skill、硬偏好和近分歧义；循环/缺依赖是明确冲突 |
| 硬规则矛盾 | 平台、权限、只读与执行要求、排除/要求同一提供方均有回归 |
| 同一后端争用 | 两个 owner 的真实 SQLite 排他租约、别名相同键、部分申请回滚、外来释放拒绝；并非真实 IDA/Ghidra 双控制实验 |
| 按阶段加载 | 当前阶段一个主过程与选定 Schema，参考按页加载；发现目录中只有一个 SKILL.md |
| 真实 MCP 协议 | 统一服务及 REA 初始化、tools/list、调用、结构化结果；真实工具数与可用性名称并集核对 |
| 真实无害 REA 流程 | 自建 JS 样本与 ZIP 归档；没有用 fixture 替代 REA |
| 状态保持与目标切换 | 原会话证据可读；换目标换修订号/代次、旧引用拒绝、跨任务引用拒绝 |
| 错误、取消与断线 | 真实 REA 错误、进行中请求取消、旧连接关闭后显式重连；另用独立协议 fixture 验证突然 EOF |

纯策略 fixture、协议故障 fixture 与真实 REA 证据分开。fixture 的工具不进入交付能力目录或验收样本流程。

## 真实联合流程逐项结果

| 检查 | 结果 |
|---|---|
{acceptance_rows}

## 仍存在的限制

1. 原生 Ghidra/IDA/Hopper 当前未完成真实目标分析。REA 报告 Ghidra/IDA 未配置、Hopper 主机不支持；不等同于确认机器绝无相关安装。条件 Ghidra 路径只验证规划/绑定门禁。
2. {source_lock['catalog']['contract_reviewed_tool_count']} 个 REA 操作是已映射的执行契约，不等于每个操作在本机都可用；已实际验证的工作流以本报告列出的 JS、归档及状态调用为限。其余 MCP 定义是可检索元数据，未审查的副作用或句柄绑定会拒绝执行。
3. Ghidra/IDA 直连桥、JSHook 浏览器、Reqable 实际分析、设备与数据库共享目标未验收；端口及协议存在不能替代这些证据。PentestSwarm 协议有警告。
4. 权限声明来自可信本地客户端对用户请求的解释，协调锁只管经过本服务的调用；本服务不是隔离恶意本地用户的安全沙箱。
5. 文件/目录输入有界，禁止秘密路径和隐式目标，未知目标类型会返回明确状态。没有自动安装商业引擎、没有读取账号登录状态。
6. 新 Codex 桌面会话的自动发现未操作验证；已写项目级配置，真实 MCP 客户端连接已验证。项目文件需要整体保留或按说明迁移绝对路径。
7. 没有校准置信度、普适检索准确率、Token 节省比例或性能提升结论。

## 复现

在项目根目录运行：

```powershell
./.venv/Scripts/python.exe -X utf8 -m pytest -q --junitxml=reports/tests.xml
./.venv/Scripts/python.exe -X utf8 scripts/evaluate_retrieval.py
./.venv/Scripts/python.exe -X utf8 scripts/verify_rea.py
./.venv/Scripts/python.exe -X utf8 scripts/demo.py
```

启动 stdio 服务：`start.ps1`。完整接入和规则说明见 `../README.zh-CN.md`。不修改全局配置，也没有清理原始检出或既有文件。
"""
    (ROOT / "reports/验收报告.md").write_text(verification, encoding="utf-8")
    print(json.dumps({"tests": tests, "real_rea_checks": len(rea["checks"]), "gateway_checks": len(gateway["checks"]), "catalog": catalog["version"], "source_code_digest": source_lock["code_tree_digest"]}))


if __name__ == "__main__":
    main()
