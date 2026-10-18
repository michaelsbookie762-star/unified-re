"""Protocol-fault fixture only. This is not a REA substitute."""
import os
from typing import Any

from mcp.server import MCPServer

server = MCPServer("owned-protocol-fault-fixture")


@server.tool(structured_output=True)
async def abrupt_disconnect() -> dict[str, Any]:
    os._exit(23)


@server.tool(structured_output=True)
async def typed_error() -> dict[str, Any]:
    raise ValueError("owned fixture intentional failure")


if __name__ == "__main__":
    server.run()
