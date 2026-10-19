"""Build a single shared capability catalog from pinned, allowlisted inputs."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unified_re.common import ROOT, SKILL, digest, read_json, write_json

# Methodology classification does not claim an executable engine exists.
PROFILES = {
    "js-reverse": (["javascript", "electron", "web"], ["javascript.static", "web.observe"], "JavaScript / Electron 模块依赖、路由、IPC、签名链路与前端行为分析"),
    "ida-reverse": (["native"], ["native.analyze"], "IDA native decompilation 机器码、伪代码、函数、交叉引用"),
    "ghidra-reverse": (["native"], ["native.analyze"], "Ghidra free open-source native decompilation 原生二进制反编译与交叉引用"),
    "radare2": (["native"], ["native.analyze"], "radare2 CLI binary inspection, disassembly and references"),
    "dotnet-reverse": (["managed"], ["managed.inspect"], "Inspect compiled C# .NET assemblies, metadata and intermediate language 托管程序元数据"),
    "apk-reverse": (["apk"], ["android.inspect"], "Android APK decompile and inspect manifest, classes, methods 安卓安装包静态分析"),
    "go-rust-reverse": (["native"], ["native.metadata"], "Go Rust compiler and build metadata 编译器、模块与依赖元数据"),
    "binary-diff": (["native", "artifact"], ["binary.compare"], "Compare released binary versions and migrate symbols 跨版本差分、符号迁移"),
    "browser-automation": (["web"], ["web.observe"], "Inspect page layout, scripts, browser interaction 网页交互与浏览器观察"),
    "protocol-reverse": (["capture"], ["capture.inspect"], "Recover wire protocols from recorded network traffic 从离线网络流量还原通信格式"),
    "digital-forensics": (["capture", "artifact"], ["artifact.inspect"], "Evidence preservation, disk and memory timeline 数字取证、证据保全"),
    "docs-generator": (["any"], ["report.compose"], "Synthesize evidence and limitations into a report 证据报告、技术文档"),
    "case-review": (["any"], ["evidence.review"], "Review evidence lineage and traceability 审查证据链、来源与完整性"),
    "reverse-engineering": (["native", "artifact"], ["native.analyze"], "Understand compiled or obfuscated artifacts 通用逆向方法、静态到动态的阶段交接"),
    "firmware-pentest": (["firmware"], ["firmware.inspect"], "Firmware extraction and inspection 固件区域分析与提取"),
    "database-security": (["database"], ["database.inspect"], "Database schema and security inspection 数据库结构与访问权限分析"),
}
TOOL_MAP = {
    "analyze_javascript_application": ("javascript.static", ["javascript", "electron"], "path", "analyze"),
    "inspect_managed_artifact": ("managed.inspect", ["managed"], "path", "analyze"),
    "inspect_android_package": ("android.inspect", ["apk"], "path", "analyze"),
    "inspect_go_binary": ("native.metadata", ["native"], "path", "analyze"),
    "inspect_rust_binary": ("native.metadata", ["native"], "path", "analyze"),
    "inspect_firmware_regions": ("firmware.inspect", ["firmware"], "path", "analyze"),
    "inspect_sqlite_database": ("database.inspect", ["database"], "path", "analyze"),
    "inspect_network_capture": ("capture.inspect", ["capture"], "path", "analyze"),
    "inspect_artifact": ("artifact.inspect", ["artifact"], "active", "analyze"),
    "open_binary": ("target.open", ["native", "artifact"], "path", "triage"),
    "close_binary": ("target.close", ["any"], "active", "cleanup"),
    "analyze_function": ("native.analyze", ["native"], "active", "analyze"),
    "decompile_function": ("native.analyze", ["native"], "active", "analyze"),
    "list_strings": ("native.strings", ["native"], "active", "analyze"),
    "list_segments": ("native.segments", ["native"], "active", "analyze"),
    "list_procedures": ("native.procedures", ["native"], "active", "analyze"),
    "inspect_analysis_view": ("evidence.read", ["any"], "retained", "evidence"),
    "get_evidence_bundle": ("evidence.read", ["any"], "retained", "evidence"),
    "binary_session": ("session.inspect", ["any"], "session", "triage"),
}


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args]).decode("utf-8").strip()


def strip_control(text):
    # Imported controllers are data, never executable instructions. Remove global
    # setup/action/precedent/route/menu sections from procedural excerpts.
    text = re.sub(r"\A---\r?\n.*?\r?\n---\r?\n", "", text, count=1, flags=re.S)
    sections = re.split(r"(?m)(?=^## )", text)
    bad = r"ACTION REQUIRED|路由上下文|下一步|Next.Step|自动.*配置|自举|CRITICAL|授权.*先例|First Instruction"
    return "\n".join(s for s in sections if not re.search(bad, s.splitlines()[0] if s.splitlines() else "", re.I))


def main():
    discovery = read_json(ROOT / "reports/discovery.json")
    provenance, skills, resource_files = {}, [], []
    for source, prefix in (("reverse-skill", "skills"), ("rea", ".agents/skills/reverse-engineer-anything")):
        repo = ROOT / "upstream" / source
        commit = git(repo, "rev-parse", "HEAD")
        provenance[source] = {"url": f"https://github.com/{'zhaoxuya520/reverse-skill' if source == 'reverse-skill' else 'morluto/rea'}", "commit": commit, "license": "MIT"}
        extra = ["RULES.md", "RULES_zh.md", "README_AI.md", "AGENTS.md", "scripts", "docs", "CTF-Sandbox-Orchestrator"] if source == "reverse-skill" else []
        paths = git(repo, "ls-files", "-z", prefix, *extra).split("\0")
        # Preserve relative resources exactly. They are not active entrypoints and
        # are never bulk-injected or exposed as shell execution by the gateway.
        for rel in paths:
            path = repo / rel
            if not path.is_file() or path.is_symlink() or any(p.startswith(".env") for p in Path(rel).parts):
                continue
            destination = ROOT / "resources" / source / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
            resource_files.append({"source": source, "commit": commit, "path": str(destination.relative_to(ROOT)).replace("\\", "/"), "sha256": digest(path.read_bytes())})
        for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            if (repo / name).is_file():
                target = ROOT / "resources" / source / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(repo / name, target)
                resource_files.append({"source": source, "commit": commit, "path": target.relative_to(ROOT).as_posix(), "sha256": digest(target.read_bytes())})
        if source != "reverse-skill":
            continue
        for rel in paths:
            if not rel.endswith("/SKILL.md") or rel == "skills/SKILL.md":
                continue
            path = repo / rel
            if not path.is_file():
                continue
            name = path.parent.name
            text = path.read_text(encoding="utf-8-sig")
            types, caps, purpose = PROFILES.get(name, (["specialist"], [name.replace("-", ".")], name.replace("-", " ")))
            clean = strip_control(text)
            procedure = SKILL / "procedures" / (name + ".md")
            procedure.parent.mkdir(parents=True, exist_ok=True)
            procedure.write_text(clean, encoding="utf-8")
            frontmatter = text.split("---", 2)[1] if text.startswith("---") else ""
            description = re.search(r"description:\s*(.*)", frontmatter, re.S)
            skills.append({"id": "reverse-skill:" + name, "name": name, "source": source, "version": commit, "kind": "methodology", "target_types": types, "capabilities": caps, "stages": ["analyze"] if name not in ("docs-generator", "case-review") else ["synthesis"], "purpose": purpose, "trigger_description": description.group(1).strip() if description else purpose, "procedure": str(procedure.relative_to(SKILL)).replace("\\", "/"), "original": f"resources/reverse-skill/{rel}", "requirements": caps, "scope": "specialist", "platforms": ["windows", "linux", "darwin"], "priority": 10 if name != "reverse-engineering" else 0})
    common = [
        ("triage", "triage", "any", "session.inspect", "确认目标身份、平台、范围和真实依赖；仅对明确目标做只读辨型。Check target identity and real backend availability before analysis."),
        ("rea-javascript", "analyze", "javascript", "javascript.static", "Recover script relationships, module imports, route declarations and Electron IPC from an extracted shipped application without running it. 静态分析交付程序中的脚本依赖、路由、进程通信；不运行目标。"),
        ("rea-managed", "analyze", "managed", "managed.inspect", "Read .NET metadata and CIL from a shipped managed assembly. 静态读取托管程序集元数据与中间语言。"),
        ("rea-native", "analyze", "native", "native.analyze", "Recover readable procedures, instructions, callers and references from native machine code using an available provider. 从编译后的机器指令恢复可读函数。"),
        ("rea-artifact", "analyze", "artifact", "artifact.inspect", "Inspect a packaged archive and its members, retain digests and inventory evidence. 安装包、归档文件、成员与哈希清单。"),
        ("evidence", "evidence", "any", "evidence.read", "Read retained Evidence in the same session; preserve parent IDs, limitations and distinct provider observations. 同一会话中按引用读取证据，保留来源与未知事项。"),
        ("synthesis", "synthesis", "any", "report.compose", "Produce a traceable report from the task's evidence; distinguish observations, inference and unknowns. 按证据写报告，区分事实、推论与未验证内容。"),
    ]
    for name, stage, target, cap, text in common:
        path = SKILL / "procedures" / (name + ".md")
        path.write_text(text + "\n", encoding="utf-8")
        skills.append({"id": "unified:" + name, "name": name, "source": "rea" if name.startswith("rea-") else "unified", "version": provenance["rea"]["commit"] if name.startswith("rea-") else "1", "kind": "methodology", "target_types": [target], "capabilities": [cap], "stages": [stage], "purpose": text, "procedure": f"procedures/{name}.md", "requirements": [] if stage in ("triage", "synthesis") else [cap], "scope": "specialist", "platforms": ["windows", "linux", "darwin"], "priority": 12})
    tools = []
    for source, value in discovery["sources"].items():
        identity = value.get("identity", {})
        source_version = identity.get("serverInfo", {}).get("version", "unknown")
        for tool in value.get("tools", []):
            name = tool["name"]
            profile = TOOL_MAP.get(name)
            cap, targets, target_mode, stage = profile if profile else (f"declared.{source}.{name}", ["unknown"], "unknown", "unknown")
            # Only explicitly reviewed REA read-only/session operations are callable.
            reviewed = source == "rea" and profile is not None
            availability = value.get("availability", {}).get(name)
            effects = availability.get("effects", ["unknown"]) if availability else ["unknown"]
            tools.append({"id": source + "::" + name, "source": source, "name": name, "version": source_version, "definition": tool, "contract_hash": digest(tool), "capabilities": [cap], "target_types": targets, "target_mode": target_mode, "target_parameter": "input_path" if name == "analyze_javascript_application" else "path", "stage": stage, "effects": effects, "effect_vocabulary": "upstream REA closed flags" if availability else "unverified", "reviewed": reviewed, "resource_kind": "task-session" if source == "rea" else "shared-instance", "availability_snapshot": availability, "behavior_equivalence": None})
    relations = [
        {"type": "complementary", "from": "unified:triage", "to": "unified:rea-javascript", "input": "identified explicit target", "output": "retained application Evidence"},
        {"type": "dependency", "from": "unified:evidence", "to": "unified:rea-javascript", "condition": "requires parent evidence from same live session"},
        {"type": "complementary", "from": "unified:evidence", "to": "unified:synthesis", "input": "evidence with provenance", "output": "report"},
        {"type": "exclusive", "members": ["reverse-skill:ida-reverse", "reverse-skill:ghidra-reverse", "reverse-skill:radare2", "unified:rea-native"], "scope": "primary-per-stage", "condition": "one concrete provider and instance selected"},
        {"type": "alternative", "from": "reverse-skill:ida-reverse", "to": "reverse-skill:ghidra-reverse", "trigger": "dependency unavailable; explicit revised plan before new evidence"},
        {"type": "equivalent-capability", "members": ["reverse-skill:js-reverse", "unified:rea-javascript"], "capability": "javascript.static", "interchangeable_tools": False, "reason": "methodology overlaps, browser runtime differs from target-free static inspection"},
    ]
    rules = {"version": 1, "order": ["user_requirements", "target_type", "platform", "permissions", "dependencies", "live_availability", "specialization", "stage", "continuity", "retrieval_rank"], "one_primary_per_stage": True, "hard_rules": ["no_secret_reads", "explicit_target_required", "no_unreviewed_effects", "no_unowned_resource", "no_silent_fallback", "no_implicit_reconnect", "no_cross_task_evidence", "no_controller_injection"], "score_semantics": "RRF merges ranks only; cosine and BM25 are uncalibrated retrieval signals, never confidence", "equivalence": "Requires reviewed input/output, effects, target/state semantics AND same behavior proof; name/schema similarity is insufficient"}
    for skill in skills:
        rea_reference = {"triage": "connection-and-recovery.md", "rea-javascript": "javascript-applications.md", "rea-managed": "native-and-artifacts.md", "rea-native": "native-and-artifacts.md", "rea-artifact": "native-and-artifacts.md", "evidence": "evidence-workflows.md", "synthesis": "evidence-workflows.md"}.get(skill["name"])
        skill["reference_paths"] = [f"resources/rea/.agents/skills/reverse-engineer-anything/references/{rea_reference}"] if skill["id"].startswith("unified:") and rea_reference else []
        skill["procedure_sha256"] = digest((SKILL / skill["procedure"]).read_bytes())
        skill["dependency_providers"] = {cap: [t["id"] for t in tools if cap in t["capabilities"]] for cap in skill["requirements"]}
        if skill["name"] in ("attack-chain", "ctf-sandbox-orchestrator"):
            skill["scope"] = "controller-reference"
    workflow = [
        {"stage": "triage", "depends_on": [], "input": "explicit target and authorization", "output": "target identity and dependency facts"},
        {"stage": "analyze", "depends_on": ["triage"], "input": "verified target identity", "output": "source-specific Evidence"},
        {"stage": "evidence", "depends_on": ["analyze"], "input": "same-session parent Evidence", "output": "evidence references and coverage"},
        {"stage": "synthesis", "depends_on": ["evidence"], "input": "retained evidence and limitations", "output": "reviewable report"},
    ]
    operations = {"javascript": "rea::analyze_javascript_application", "electron": "rea::analyze_javascript_application", "managed": "rea::inspect_managed_artifact", "apk": "rea::inspect_android_package", "artifact": "rea::inspect_artifact", "native": "rea::analyze_function", "firmware": "rea::inspect_firmware_regions", "database": "rea::inspect_sqlite_database", "capture": "rea::inspect_network_capture"}
    capability_index = {cap: {"skills": [s["id"] for s in skills if cap in s["capabilities"]], "tools": [t["id"] for t in tools if cap in t["capabilities"]], "interchangeability": "not inferred; requires verified behavior and contracts"} for cap in sorted({c for s in skills for c in s["capabilities"]} | {c for t in tools for c in t["capabilities"]})}
    # Shared across MCP and Skill. Snapshots are explicitly not live readiness.
    catalog = {"schema_version": 1, "resource_base": "project-root; outside automatic Skill discovery", "resources_digest": digest(resource_files), "sources": provenance, "skills": skills, "tools": tools, "capabilities": capability_index, "relations": relations, "workflow": workflow, "default_operations": operations, "rules": rules}
    from scripts.cloak_catalog import extend_catalog
    extend_catalog(catalog)
    catalog["version"] = digest({k: v for k, v in catalog.items() if k != "version"})
    write_json(SKILL / "catalog.json", catalog)
    write_json(SKILL / "resource-manifest.json", resource_files)
    print(json.dumps({"skills": len(skills), "tools": len(tools), "resources": len(resource_files), "catalog_version": catalog["version"]}))


if __name__ == "__main__":
    main()
