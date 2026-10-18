"""Real official REA over MCP, without a native/commercial engine."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unified_re.common import ROOT, now, read_json, write_json
from unified_re.targets import identify
from unified_re.transport import Connection, expand_availability, rea_result
from scripts.fixtures import archive_fixture


async def main():
    config = read_json(ROOT / "backends.json")["sources"]["rea"]
    connection = Connection(config)
    report = {"observed_at": now(), "backend": "real rea-agents@6.5.0", "protocol": {}, "checks": []}
    old_id = None
    try:
        await connection.start()
        report["protocol"] = connection.identity
        session = await connection.call("binary_session", {})
        assert set(expand_availability(session)) == {t["name"] for t in connection.tools}
        report["checks"].append({"check": "complete_inventory_and_live_availability", "passed": True, "tool_count": len(connection.tools)})
        target = identify(str(ROOT / "samples/demo-app"))
        analyzed = await connection.call("analyze_javascript_application", {"input_path": target["path"], "detail": "complete"})
        write_json(ROOT / "reports/rea-analysis-raw.json", analyzed)
        assert not analyzed.get("isError"), analyzed
        evidence = analyzed["structuredContent"]
        old_id = evidence["evidence_id"]
        graph = rea_result(analyzed)
        text = json.dumps(graph)
        assert "main.js" in text and "helper.js" in text and "normalizeLabel" in text
        report["checks"].append({"check": "real_static_javascript_modules_and_imports", "passed": True, "target": target, "evidence_id": old_id, "result_keys": list(graph)})
        retained = await connection.call("inspect_analysis_view", {"source": {"kind": "retained-evidence", "evidence_id": old_id}, "view": {"kind": "summary"}})
        assert not retained.get("isError"), retained
        assert old_id in json.dumps(retained)
        write_json(ROOT / "reports/rea-retained-view-raw.json", retained)
        report["checks"].append({"check": "same_session_retained_evidence", "passed": True})
        archive = archive_fixture()
        opened = await connection.call("open_binary", {"path": str(archive)})
        assert not opened.get("isError"), opened
        inspected = await connection.call("inspect_artifact", {})
        assert not inspected.get("isError"), inspected
        assert all(name in json.dumps(inspected) for name in ("main.js", "helper.js", "package.json"))
        write_json(ROOT / "reports/rea-archive-raw.json", {"open": opened, "inspection": inspected, "target": identify(str(archive))})
        report["checks"].append({"check": "real_open_and_active_target_inspection", "passed": True})
        archive_id = inspected["structuredContent"]["evidence_id"]
        closed = await connection.call("close_binary", {})
        assert not closed.get("isError"), closed
        cleared = await connection.call("inspect_analysis_view", {"source": {"kind": "retained-evidence", "evidence_id": archive_id}, "view": {"kind": "summary"}})
        assert cleared.get("isError") is True
        write_json(ROOT / "reports/rea-close-clears-evidence-raw.json", cleared)
        report["checks"].append({"check": "real_close_invalidates_active_context_and_retained_evidence", "passed": True})
        failed = await connection.call("analyze_javascript_application", {"bogus_parameter": True})
        assert failed.get("isError") is True
        write_json(ROOT / "reports/rea-error-raw.json", failed)
        report["checks"].append({"check": "real_backend_input_error_preserved", "passed": True})
    finally:
        await connection.close()
    fresh = Connection(config)
    try:
        await fresh.start()
        missing = await fresh.call("inspect_analysis_view", {"source": {"kind": "retained-evidence", "evidence_id": old_id}, "view": {"kind": "summary"}})
        assert missing.get("isError") is True
        write_json(ROOT / "reports/rea-reconnect-error-raw.json", missing)
        report["checks"].append({"check": "new_connection_does_not_reuse_retained_evidence", "passed": True})
    finally:
        await fresh.close()
    report["passed"] = all(r["passed"] for r in report["checks"])
    write_json(ROOT / "reports/rea-verification.json", report)
    print(json.dumps({"passed": report["passed"], "checks": [r["check"] for r in report["checks"]]}))


if __name__ == "__main__":
    asyncio.run(main())
