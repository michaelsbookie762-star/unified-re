"""End-to-end client -> unified MCP -> official REA MCP, real local samples."""
import asyncio
import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unified_re.common import ROOT, now, write_json
from unified_re.transport import rea_result
from scripts.fixtures import archive_fixture


class GatewayClient:
    """The front-end client multiplexes requests; backend sessions stay serial."""
    def __init__(self, config):
        self.config = config
        self.stack = None

    async def start(self):
        self.stack = AsyncExitStack()
        streams = await self.stack.enter_async_context(stdio_client(StdioServerParameters(command=self.config["command"], args=self.config["args"], cwd=str(ROOT), env={"PYTHONIOENCODING": "utf-8"})))
        self.session = await self.stack.enter_async_context(ClientSession(*streams, read_timeout_seconds=120))
        self.identity = await self.session.initialize()
        self.tools = [t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in (await self.session.list_tools()).tools]

    async def call(self, name, arguments):
        raw = await self.session.call_tool(name, arguments=arguments)
        return raw.model_dump(mode="json", by_alias=True, exclude_none=True)

    async def close(self):
        if self.stack:
            await self.stack.aclose()
            self.stack = None


def unpack(raw):
    if raw.get("isError"):
        raise AssertionError(json.dumps(raw, ensure_ascii=True)[:2000])
    structured = raw.get("structuredContent")
    if structured is None:
        raise AssertionError("Gateway did not return structured data")
    return structured.get("result", structured)


async def main():
    config = {"command": sys.executable, "args": ["-X", "utf8", str(ROOT / "scripts/serve.py")], "call_timeout": 120, "startup_timeout": 40}
    gateway = GatewayClient(config)
    checks, transcript = [], []

    async def call(name, args):
        raw = await gateway.call(name, args)
        transcript.append({"tool": name, "arguments": args, "raw_result": raw})
        value = unpack(raw)
        return value

    def checked(name, condition, **details):
        if not condition:
            raise AssertionError(name + ": " + json.dumps(details, ensure_ascii=True)[:2000])
        checks.append({"check": name, "passed": True, **details})
        print(name, "PASS", flush=True)

    try:
        await gateway.start()
        write_json(ROOT / "reports/gateway-tools.json", {"identity": gateway.identity.model_dump(mode="json", by_alias=True), "tools": gateway.tools})
        checked("unified_protocol_initialize_and_tools_list", {"capability_search", "task_plan", "gateway_call", "stage_load"} <= {t["name"] for t in gateway.tools}, tool_count=len(gateway.tools))
        hits = await call("capability_search", {"query": "梳理这个交付程序中脚本互相依赖的关系", "limit": 30})
        checked("real_multilingual_joint_retrieval", any("javascript.static" in c["capabilities"] for c in hits["candidates"]))
        negative = await call("capability_search", {"query": "给我一份番茄炒蛋菜谱"})
        checked("no_match_does_not_execute", negative["status"] == "no_match")
        data = await call("task_plan", {"request": "静态分析 JavaScript application 的模块依赖，保留证据，不运行目标", "target_path": str(ROOT / "samples/demo-app"), "context": {"permissions": ["read_local"]}})
        checked("reviewable_plan_with_real_availability", data["status"] == "ready", status=data["status"], reason=data.get("reason"))
        task_id, revision = data["id"], data["revision"]
        phase = await call("stage_load", {"task_id": task_id, "revision": revision})
        checked("only_current_stage_definitions", [t["id"] for t in phase["tool_definitions"]] == ["rea::binary_session"])
        wrong_stage = await call("gateway_call", {"task_id": task_id, "revision": revision, "tool_id": "rea::analyze_javascript_application", "arguments": {"input_path": str(ROOT / "samples/demo-app")}})
        checked("tool_outside_current_plan_rejected", wrong_stage["status"] == "plan_mismatch")
        await call("stage_advance", {"task_id": task_id, "revision": revision})
        phase = await call("stage_load", {"task_id": task_id, "revision": revision})
        checked("primary_and_complementary_skill_loaded", phase["primary_skill"]["id"] == "unified:rea-javascript" and phase["supplemental_skills"][0]["id"] == "reverse-skill:js-reverse")
        mismatch = await call("gateway_call", {"task_id": task_id, "revision": revision, "tool_id": "rea::analyze_javascript_application", "arguments": {"input_path": str(ROOT / "samples/second-app")}})
        checked("planned_target_binding_enforced", mismatch["status"] == "target_mismatch")
        analyzed = await call("gateway_call", {"task_id": task_id, "revision": revision, "tool_id": "rea::analyze_javascript_application", "arguments": {"input_path": str(ROOT / "samples/demo-app"), "detail": "summary"}})
        checked("real_rea_analysis_through_gateway", analyzed["status"] == "succeeded", status=analyzed["status"])
        first_id = rea_result(analyzed["raw_mcp_result"]).get("parent_evidence_id", analyzed["reference"]["evidence_id"])
        await call("stage_advance", {"task_id": task_id, "revision": revision})
        retained = await call("gateway_call", {"task_id": task_id, "revision": revision, "tool_id": "rea::inspect_analysis_view", "arguments": {"source": {"kind": "retained-evidence", "evidence_id": first_id}, "view": {"kind": "summary"}}})
        checked("retained_parent_evidence_in_same_gateway_session", retained["status"] == "succeeded")
        await call("stage_advance", {"task_id": task_id, "revision": revision})
        report_text = "# 本地无害样本静态分析\n\n真实 REA MCP 静态检查了 demo-app，并在同一会话读回保留证据。模块与导入关系由上游图记录支持；没有执行目标程序。静态结果不证明运行时行为，原生反编译引擎未参与该流程。\n"
        await call("task_report", {"task_id": task_id, "revision": revision, "markdown": report_text, "evidence_ids": [first_id]})
        done = await call("stage_advance", {"task_id": task_id, "revision": revision})
        checked("complete_real_staged_workflow", done["status"] == "completed")

        switched = await call("task_revise", {"task_id": task_id, "revision": revision, "target_path": str(ROOT / "samples/second-app")})
        checked("target_switch_new_revision_and_session", switched["status"] == "ready" and switched["revision"] == revision + 1 and switched["generation"] == 2)
        stale = await call("stage_load", {"task_id": task_id, "revision": revision})
        checked("old_plan_revision_rejected", stale["status"] == "stale_plan")
        revision = switched["revision"]
        await call("stage_advance", {"task_id": task_id, "revision": revision})
        second = await call("gateway_call", {"task_id": task_id, "revision": revision, "tool_id": "rea::analyze_javascript_application", "arguments": {"input_path": str(ROOT / "samples/second-app")}})
        checked("second_target_evidence_has_distinct_identity", second["status"] == "succeeded" and second["reference"]["target_sha256"] != analyzed["reference"]["target_sha256"] and "SECOND_TARGET_ONLY" in json.dumps(second["raw_mcp_result"]))
        await call("stage_advance", {"task_id": task_id, "revision": revision})
        invalid_ref = await call("gateway_call", {"task_id": task_id, "revision": revision, "tool_id": "rea::inspect_analysis_view", "arguments": {"source": {"kind": "retained-evidence", "evidence_id": first_id}, "view": {"kind": "summary"}}})
        checked("old_session_evidence_not_reused_after_switch", invalid_ref["status"] == "evidence_mismatch")
        # End the protocol connection while this task is active. On a fresh
        # service process only the journal exists; REA state cannot be assumed.
        await gateway.close()
        gateway = GatewayClient(config)
        await gateway.start()
        status = await call("task_status", {"task_id": task_id})
        checked("service_disconnect_preserves_journal_not_live_handles", status["status"] == "disconnected")
        recovered = await call("task_revise", {"task_id": task_id, "revision": revision})
        checked("explicit_reconnect_replans_and_increments_generation", recovered["status"] == "ready" and recovered["generation"] == 3)
        await call("task_cancel", {"task_id": task_id})

        archive = archive_fixture()
        package_task = await call("task_plan", {"request": "Inspect archive package members and retain artifact inventory evidence", "target_path": str(archive), "context": {"permissions": ["read_local"]}})
        checked("active_target_workflow_resolves_open_prerequisite", package_task["status"] == "ready", status=package_task["status"])
        aid = package_task["id"]
        await call("stage_advance", {"task_id": aid, "revision": 1})
        unopened = await call("gateway_call", {"task_id": aid, "revision": 1, "tool_id": "rea::inspect_artifact", "arguments": {}})
        checked("active_target_cannot_be_read_before_open", unopened["status"] == "needs_context")
        opened = await call("gateway_call", {"task_id": aid, "revision": 1, "tool_id": "rea::open_binary", "arguments": {"path": str(archive)}})
        package = await call("gateway_call", {"task_id": aid, "revision": 1, "tool_id": "rea::inspect_artifact", "arguments": {}})
        checked("real_gateway_open_then_inspect_continuity", opened["status"] == "succeeded" and package["status"] == "succeeded" and "helper.js" in json.dumps(package["raw_mcp_result"]))
        await call("task_cancel", {"task_id": aid})

        # A larger owned static input lets cancellation reach a real outstanding
        # REA analysis request. It is never executed, crawled or indexed.
        cancel_dir = ROOT / "var/fixtures/cancel-app"
        cancel_dir.mkdir(parents=True, exist_ok=True)
        (cancel_dir / "main.js").write_text("\n".join(f"export function f{i}(value) {{ return String(value).trim() + '{i}'; }}" for i in range(12000)), encoding="utf-8")
        cancellable = await call("task_plan", {"request": "Inspect JavaScript modules without executing them", "target_path": str(cancel_dir), "context": {"permissions": ["read_local"]}})
        checked("cancellation_task_planned", cancellable["status"] == "ready")
        cid = cancellable["id"]
        await call("stage_advance", {"task_id": cid, "revision": 1})
        pending = asyncio.create_task(call("gateway_call", {"task_id": cid, "revision": 1, "tool_id": "rea::analyze_javascript_application", "arguments": {"input_path": str(cancel_dir), "detail": "summary"}}))
        dispatched = False
        for _ in range(100):
            journal = await call("task_journal", {"task_id": cid})
            dispatched = any(e["kind"] == "call_dispatched" for e in journal["events"])
            if dispatched or pending.done():
                break
            await asyncio.sleep(.02)
        checked("real_analysis_dispatched_before_cancel", dispatched and not pending.done())
        cancelled = await call("task_cancel", {"task_id": cid})
        reply = await asyncio.wait_for(pending, 20)
        checked("real_rea_request_cancelled_and_owned_session_closed", cancelled["status"] == "cancelled" and reply["status"] == "cancelled")
        health = await call("backend_status", {})
        checked("no_owned_sessions_or_leases_left", not health["live_owned_sessions"] and not health["leases"])
    finally:
        await gateway.close()
        write_json(ROOT / "reports/gateway-transcript.json", transcript)
        write_json(ROOT / "reports/gateway-verification.json", {"observed_at": now(), "passed": len(checks) >= 23 and all(c["passed"] for c in checks), "checks": checks, "uses_real_rea": True})


if __name__ == "__main__":
    asyncio.run(main())
