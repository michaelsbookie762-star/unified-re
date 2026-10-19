"""Read-only dependency and MCP audit; no target calls or credential-file reads."""
import asyncio
import contextvars
import importlib.metadata
import json
import logging
import re
import shutil
import socket
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unified_re.common import ROOT, now, read_json, write_json, public_error
from unified_re.transport import Connection, rea_result

SOURCE = contextvars.ContextVar("audit_source", default="unknown")
WARNINGS = []


class ProtocolWarnings(logging.Handler):
    def emit(self, record):
        # Count malformed protocol/logging events without copying their payloads.
        WARNINGS.append({"source": SOURCE.get(), "level": record.levelname})


async def probe(name, config):
    SOURCE.set(name)
    config = dict(config, startup_timeout=18, call_timeout=20)
    connection = Connection(config)
    item = {"source": name, "configured": True, "protocol_verified": False, "analysis_engine_verified": False}
    try:
        await connection.start()
        item.update({"protocol_verified": True, "tool_count": len(connection.tools), "identity": connection.identity})
        if name == "rea":
            raw = await connection.call("binary_session", {})
            item["binary_session_succeeded"] = not raw.get("isError")
            item["native_provider_candidates"] = (rea_result(raw) or {}).get("analysis_provider_candidates", [])
        if name == "cloakbrowser":
            raw = await connection.call("browser_snapshot", {})
            item["blank_browser_snapshot_succeeded"] = not raw.get("isError")
    except Exception as error:
        item["error"] = public_error(error)
    finally:
        await connection.close()
    # TCP is an independent layer even if MCP initialization failed.
    if name in ("ghidra", "idapro", "reqable-mcp"):
        port = {"ghidra": 8080, "idapro": 13337, "reqable-mcp": 9000}[name]
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                item["localhost_tcp"] = "connected; service identity and target analysis unverified"
        except OSError:
            item["localhost_tcp"] = "unreachable"
    item["protocol_warning_count"] = sum(w["source"] == name for w in WARNINGS)
    item["protocol_clean"] = item["protocol_verified"] and item["protocol_warning_count"] == 0
    print(name, "protocol=" + str(item["protocol_verified"]), "tools=" + str(item.get("tool_count", 0)), flush=True)
    return item


async def main():
    reverse = Path.home() / ".codex/reverse-skill"
    text = (reverse / "skills/tool-index.md").read_text(encoding="utf-8-sig")
    names = sorted({m.group(1) for m in re.finditer(r"(?m)^\| ([A-Za-z0-9][A-Za-z0-9_.-]*) \|", text)} | {"git", "uv", "codex", "pi", "npm", "npx", "dotnet", "dnSpy", "ghidra", "frida", "semgrep", "codeql", "docker", "kubectl"})
    query = "[Console]::OutputEncoding = [Text.UTF8Encoding]::new(); $names = @(" + ",".join("'" + n + "'" for n in names) + "); $result = foreach ($name in $names) { $cmd = Get-Command -Name $name -ErrorAction SilentlyContinue | Select-Object -First 1; [pscustomobject]@{name=$name;path=if($cmd){$cmd.Source}else{$null};found=[bool]$cmd} }; $result | ConvertTo-Json -Compress"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", query], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    commands = json.loads(result.stdout)
    packages = {name: importlib.metadata.version(name) for name in ("mcp", "onnxruntime", "numpy", "tokenizers", "jsonschema", "pytest")}
    local = read_json(ROOT / "backends.json")
    browser = read_json(ROOT / "examples/backends.rea-only.json")["sources"]["cloakbrowser"]
    safe = {k: v for k, v in local["sources"].items() if k in ("rea", "ghidra", "idapro", "jshook", "reqable-mcp", "pentestswarm")}
    safe["cloakbrowser"] = browser
    logger = logging.getLogger("mcp.client.stdio")
    handler = ProtocolWarnings()
    old_level, old_propagate = logger.level, logger.propagate
    logger.setLevel(logging.ERROR)
    logger.propagate = False
    logger.addHandler(handler)
    try:
        probes = await asyncio.gather(*(probe(k, v) for k, v in safe.items()))
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
        logger.propagate = old_propagate
    # Configuration presence is inspected without copying credential values.
    global_config = tomllib.loads((Path.home() / ".codex/config.toml").read_text(encoding="utf-8-sig"))
    registered = [{"name": k, "enabled": v.get("enabled", True)} for k, v in global_config.get("mcp_servers", {}).items()]
    output = {"observed_at": now(), "scope": "Current Windows PATH, listed project dependencies, configured safe MCP initialization; not an exhaustive disk/install scan.",
              "commands": commands, "project_python": packages, "registered_mcp": registered, "mcp_checks": probes,
              "skipped": {"burpsuite": "bridge reads a token file; not launched", "anything-analyzer": "credential-dependent service; not launched", "xquik": "OAuth service; no token or account-state reads"},
              "limitations": ["Command discovery is not functional verification.", "TCP connectivity does not identify an application or prove target analysis.", "No user binary, device, GUI database or authenticated browser profile was opened."]}
    write_json(ROOT / "reports/environment-audit.json", output)
    (reverse / "cloakbrowser/output").mkdir(exist_ok=True)
    write_json(reverse / "cloakbrowser/output/environment-audit.json", output)
    print("Dependency commands:", sum(c["found"] for c in commands), "found /", len(commands), "checked", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
