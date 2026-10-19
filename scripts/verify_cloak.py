"""Real local HTTP fixture -> unified MCP -> official Playwright MCP -> CloakBrowser."""
import asyncio
import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.demo import GatewayClient, unpack
from unified_re.common import ROOT, write_json


class Page(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/drop":
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        if self.path == "/slow":
            time.sleep(5)
        body = ("<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>CloakBrowser 集成验证</title>"
                f"<h1>Owned page {self.path}</h1><label>名称<input aria-label='名称'></label><button>验证</button></html>").encode()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            pass


async def main():
    http = ThreadingHTTPServer(("127.0.0.1", 0), Page)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{http.server_port}"
    client = GatewayClient({"command": sys.executable, "args": ["-X", "utf8", str(ROOT / "scripts/serve.py")]})
    checks, transcript = [], []
    pending = None

    async def call(name, args):
        raw = await client.call(name, args)
        transcript.append({"tool": name, "arguments": args, "raw_result": raw})
        return unpack(raw)

    def checked(name, condition):
        assert condition, name
        checks.append({"check": name, "passed": True})
        print(name, "PASS", flush=True)

    async def plan(path):
        value = await call("task_plan", {"request": "用 CloakBrowser 独立浏览器查看网页可见结构，记录页面观察证据", "target_path": base + path, "context": {"permissions": ["web_read"]}})
        checked("real_browser_plan_" + path, value["status"] == "ready")
        return value, {"task_id": value["id"], "revision": value["revision"]}

    try:
        await client.start()
        for query in ["用 cloak 浏览器查看网页", "Render a website in a fresh session and examine its visible structure"]:
            hits = await call("capability_search", {"query": query, "limit": 20})
            checked("semantic_browser_recall", any(c["source"] == "cloakbrowser" for c in hits["candidates"]))
        denied = await call("task_plan", {"request": "CloakBrowser 网页观察", "target_path": base + "/first", "context": {"permissions": ["read_local"]}})
        checked("local_scope_does_not_authorize_web", denied["status"] == "permission_required")
        task, binding = await plan("/first")
        stage = await call("stage_load", binding)
        checked("only_browser_stage_definitions", [t["id"] for t in stage["tool_definitions"]] == ["cloakbrowser::browser_snapshot"])
        await call("stage_advance", binding)
        stage = await call("stage_load", binding)
        checked("single_primary_with_reverse_complement", stage["primary_skill"]["id"] == "unified:cloakbrowser" and len(stage["supplemental_skills"]) == 1)
        wrong = await call("gateway_call", {**binding, "tool_id": "cloakbrowser::browser_navigate", "arguments": {"url": base + "/second"}})
        checked("unplanned_url_denied", wrong["status"] == "target_mismatch")
        wrong = await call("gateway_call", {**binding, "tool_id": "cloakbrowser::browser_evaluate", "arguments": {"function": "() => document.title"}})
        checked("unreviewed_evaluation_denied", wrong["status"] == "plan_mismatch")
        navigated = await call("gateway_call", {**binding, "tool_id": "cloakbrowser::browser_navigate", "arguments": {"url": base + "/first"}})
        checked("real_cloak_navigation", navigated["status"] == "succeeded")
        await call("stage_advance", binding)
        snapshot = await call("gateway_call", {**binding, "tool_id": "cloakbrowser::browser_snapshot", "arguments": {}})
        checked("same_session_snapshot_and_source", snapshot["status"] == "succeeded" and snapshot["reference"]["source"] == "cloakbrowser" and snapshot["reference"]["observed_url"] == base + "/first")
        checked("owned_snapshot_content_exposed_with_hash", "Owned page /first" in snapshot["observation"]["text"] and bool(snapshot["reference"]["snapshot_sha256"]))
        checked("browser_observation_is_not_rea_evidence", snapshot["reference"]["evidence_id"].startswith("browser_obs_") and "not REA" in snapshot["reference"]["evidence_kind"])
        old_reference = snapshot["reference"]["evidence_id"]
        await call("stage_advance", binding)
        await call("task_report", {**binding, "evidence_ids": [old_reference], "markdown": "# 本地浏览器观察验证\n" + "在本服务独占的 CloakBrowser 临时会话中，实际导航至明确授权的本地测试网页，并通过同一 MCP 会话取得页面快照。观察引用保留原始结果、实际 URL 和来源；没有读取用户浏览器登录状态。URL 身份不等于页面内容哈希。"})
        finished = await call("stage_advance", binding)
        checked("complete_browser_staged_workflow", finished["status"] == "completed")
        switched = await call("task_revise", {**binding, "target_path": base + "/second"})
        checked("browser_target_switch_new_generation", switched["status"] == "ready" and switched["generation"] == task["generation"] + 1)
        stale = await call("stage_load", binding)
        checked("old_browser_revision_rejected", stale["status"] == "stale_plan")
        binding = {"task_id": switched["id"], "revision": switched["revision"]}
        blank = await call("gateway_call", {**binding, "tool_id": "cloakbrowser::browser_snapshot", "arguments": {}})
        checked("new_browser_has_no_previous_page", blank["reference"]["observed_url"] == "about:blank")
        await call("stage_advance", binding)
        await call("gateway_call", {**binding, "tool_id": "cloakbrowser::browser_navigate", "arguments": {"url": base + "/second"}})
        await call("stage_advance", binding)
        second = await call("gateway_call", {**binding, "tool_id": "cloakbrowser::browser_snapshot", "arguments": {}})
        await call("stage_advance", binding)
        rejected = await call("task_report", {**binding, "evidence_ids": [old_reference], "markdown": "x" * 100})
        checked("old_browser_evidence_not_reused", rejected["status"] == "evidence_mismatch" and second["reference"]["observed_url"] == base + "/second")
        await call("task_cancel", {"task_id": binding["task_id"]})
        failed, binding = await plan("/drop")
        await call("stage_advance", binding)
        error = await call("gateway_call", {**binding, "tool_id": "cloakbrowser::browser_navigate", "arguments": {"url": base + "/drop"}})
        checked("real_browser_error_preserved", error["status"] == "backend_error" and error["raw_mcp_result"]["isError"] is True)
        await call("task_cancel", {"task_id": failed["id"]})
        slow, binding = await plan("/slow")
        await call("stage_advance", binding)
        pending = asyncio.create_task(call("gateway_call", {**binding, "tool_id": "cloakbrowser::browser_navigate", "arguments": {"url": base + "/slow"}}))
        for _ in range(80):
            journal = await call("task_journal", {"task_id": slow["id"]})
            if any(e["kind"] == "call_dispatched" for e in journal["events"]):
                break
            await asyncio.sleep(.05)
        cancelled = await call("task_cancel", {"task_id": slow["id"]})
        outcome = await pending
        checked("browser_inflight_cancel_closes_owned_session", cancelled["status"] == "cancelled" and outcome["status"] == "cancelled")
        reconnect, binding = await plan("/first")
        await client.close()
        await client.start()
        disconnected = await call("task_status", {"task_id": reconnect["id"]})
        checked("browser_disconnect_not_implicit_reconnect", disconnected["status"] == "disconnected")
        resumed = await call("task_revise", binding)
        checked("browser_explicit_reconnect_replans", resumed["status"] == "ready" and resumed["generation"] == reconnect["generation"] + 1)
        await call("task_cancel", {"task_id": resumed["id"]})
        status = await call("backend_status", {})
        checked("browser_leases_and_sessions_released", not status["live_owned_sessions"] and not status["leases"])
        write_json(ROOT / "reports/cloak-verification.json", {"passed": True, "checks": checks, "browser": "146.0.7680.177.5", "mcp": "0.0.83"})
    finally:
        if pending:
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await client.close()
        http.shutdown()
        http.server_close()
        write_json(ROOT / "reports/cloak-transcript.json", transcript)


if __name__ == "__main__":
    asyncio.run(main())
