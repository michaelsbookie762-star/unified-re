"""Only initialize/list metadata. No user target, account or secret file reads."""
import asyncio
import json
import logging
import shutil
import socket
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unified_re.common import ROOT, now, public_error, write_json
from unified_re.transport import Connection, expand_availability


class ProtocolWarnings(logging.Handler):
    def __init__(self):
        super().__init__(logging.ERROR)
        self.messages = []

    def emit(self, record):
        self.messages.append({"message": record.getMessage(), "error_type": type(record.exc_info[1]).__name__ if record.exc_info else None})


async def main():
    # Values are not copied from credential-bearing env/url/header fields.
    global_config = tomllib.loads((Path.home() / ".codex" / "config.toml").read_text(encoding="utf-8"))
    sources = {"rea": {"command": shutil.which("node"), "args": [str(ROOT / "node_modules/rea-agents/scripts/rea.mjs"), "mcp"], "scope": "task", "call_timeout": 120, "env_names": ["GHIDRA_INSTALL_DIR", "JAVA_HOME"]}}
    for name in ("idapro", "ghidra", "jshook", "reqable-mcp", "pentestswarm"):
        value = global_config.get("mcp_servers", {}).get(name)
        if value and value.get("enabled", True):
            sources[name] = {"command": value["command"], "args": value.get("args", []), "scope": "shared", "resource_key": {"ghidra": "ghidra-http://127.0.0.1:8080", "idapro": "ida-http://127.0.0.1:13337", "jshook": "browser-jshook-default", "reqable-mcp": "reqable-http://127.0.0.1:9000", "pentestswarm": "pentestswarm-local"}[name]}
    sources["jshook"]["public_env"] = {"JSHOOK_BASE_PROFILE": "minimal"}
    write_json(ROOT / "backends.json", {"schema_version": 1, "sources": sources})
    output = {"observed_at": now(), "sources": {}, "skipped": {"burpsuite": "bridge reads a token file; excluded by secret policy", "xquik": "credential-dependent remote service; not probed", "anything-analyzer": "credential-dependent remote service; not probed"}}
    for name, config in sources.items():
        connection = Connection(config)
        warnings = ProtocolWarnings()
        logger = logging.getLogger("mcp.client.stdio")
        logger.addHandler(warnings)
        try:
            await connection.start()
            item = {"status": "protocol_verified", "identity": connection.identity, "tools": connection.tools, "tool_call_verified": False, "engine_status": "unknown"}
            if name == "rea":
                session = await connection.call("binary_session", {})
                item.update({"session": session, "availability": expand_availability(session), "tool_call_verified": not session.get("isError", False)})
            output["sources"][name] = item
            if warnings.messages:
                item["status"] = "protocol_partial"
                item["protocol_warnings"] = warnings.messages
            if name in ("ghidra", "idapro", "reqable-mcp"):
                port = {"ghidra": 8080, "idapro": 13337, "reqable-mcp": 9000}[name]
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=2):
                        item["endpoint_tcp"] = "connected"
                except OSError:
                    item["endpoint_tcp"] = "unreachable"
                    item["engine_status"] = "unavailable"
            print(name, item["status"], len(connection.tools), flush=True)
        except Exception as error:
            output["sources"][name] = public_error(error)
            print(name, type(error).__name__, flush=True)
        finally:
            await connection.close()
            logger.removeHandler(warnings)
    write_json(ROOT / "reports/discovery.json", output)


if __name__ == "__main__":
    asyncio.run(main())
