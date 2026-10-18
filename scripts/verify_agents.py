"""Verify the actual global launch entries using real MCP, without an LLM."""
import asyncio
import json
import os
import sys
import tomllib
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def check(client, config):
    env = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA") if k in os.environ}
    params = StdioServerParameters(command=config["command"], args=config["args"], cwd=config["cwd"], env=env)
    with open(os.devnull, "w") as stderr:
        async with stdio_client(params, errlog=stderr) as streams:
            async with ClientSession(*streams, read_timeout_seconds=180) as session:
                identity = await session.initialize()
                tools = (await session.list_tools()).tools
                raw = await session.call_tool("capability_search", {"query": "不运行程序，梳理 JavaScript 脚本模块之间的依赖关系", "limit": 5})
                raw = raw.model_dump(mode="json", by_alias=True, exclude_none=True)
                data = raw["structuredContent"]
                data = data.get("result", data)
                assert not raw.get("isError") and data.get("candidates") and data.get("model_fingerprint")
                assert any("javascript.static" in c.get("capabilities", []) for c in data["candidates"])
                print(client, "initialize / tools/list / capability_search PASS", flush=True)
                return {"client": client, "server": identity.model_dump(mode="json", by_alias=True)["serverInfo"], "tool_count": len(tools),
                        "model_fingerprint": data["model_fingerprint"], "candidate_ids": [c["id"] for c in data["candidates"]], "passed": True}


async def main():
    home = Path.home()
    codex = Path(os.environ.get("CODEX_HOME", home / ".codex")) / "config.toml"
    pi = Path(os.environ.get("PI_CODING_AGENT_DIR", home / ".pi/agent")) / "extensions/pi-mcp-bridge/mcp-servers.json"
    configurations = [("Codex", tomllib.loads(codex.read_text(encoding="utf-8-sig"))["mcp_servers"]["unified-re"]),
                      ("Pi", json.loads(pi.read_text(encoding="utf-8-sig"))["mcpServers"]["unified-re"])]
    results = [await check(name, config) for name, config in configurations]
    target = ROOT / "reports/global-agents-verification.json"
    target.write_text(json.dumps({"checks": results, "limit": "Protocol launch entries verified; existing GUI chats must reload their tool catalog."}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
