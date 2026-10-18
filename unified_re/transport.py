"""One owner task enters and exits each SDK transport and session context."""
import asyncio
import os
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

from .common import GateError, ROOT


class Connection:
    def __init__(self, config):
        self.config = config
        self.queue = asyncio.Queue()
        self.worker = None
        self.active = None
        self.active_future = None
        self.identity = None
        self.tools = []
        self.alive = False

    async def start(self):
        if self.worker:
            if not self.alive:
                raise GateError("disconnected", "Session lost; an explicit task reconnect is required")
            return self
        self.ready = asyncio.get_running_loop().create_future()
        self.worker = asyncio.create_task(self._run())
        try:
            await asyncio.wait_for(asyncio.shield(self.ready), timeout=self.config.get("startup_timeout", 25))
        except BaseException:
            await self.close()
            raise
        return self

    async def _run(self):
        # Explicitly pass only process prerequisites and declared environment names.
        env = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA") if k in os.environ}
        env.update({k: os.environ[k] for k in self.config.get("env_names", []) if k in os.environ})
        env.update({"PYTHONIOENCODING": "utf-8", "NO_COLOR": "1"})
        env.update(self.config.get("public_env", {}))
        try:
            params = StdioServerParameters(command=self.config["command"], args=self.config.get("args", []), cwd=str(ROOT), env=env)
            with open(os.devnull, "w") as stderr:
                async with stdio_client(params, errlog=stderr) as (read, write):
                    async with ClientSession(read, write, read_timeout_seconds=float(self.config.get("call_timeout", 90))) as session:
                        initialized = await session.initialize()
                        self.identity = initialized.model_dump(mode="json", by_alias=True, exclude_none=True)
                        cursor = None
                        while True:
                            listed = await session.list_tools(params=types.PaginatedRequestParams(cursor=cursor) if cursor else None)
                            self.tools.extend(t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in listed.tools)
                            cursor = listed.next_cursor
                            if not cursor:
                                break
                        self.alive = True
                        self.ready.set_result(True)
                        while True:
                            item = await self.queue.get()
                            if item is None:
                                break
                            name, arguments, future = item
                            if future.cancelled():
                                continue
                            self.active_future = future
                            self.active = asyncio.create_task(session.call_tool(name, arguments=arguments))
                            try:
                                result = await self.active
                                if not future.done():
                                    future.set_result(result.model_dump(mode="json", by_alias=True, exclude_none=True))
                            except asyncio.CancelledError:
                                if not future.done():
                                    future.set_exception(GateError("cancelled", "MCP request cancelled"))
                                if asyncio.current_task().cancelling():
                                    raise
                            except Exception as error:
                                if not future.done():
                                    future.set_exception(error)
                                # A transport error cannot be treated as a new stateful session.
                                raise
                            finally:
                                self.active = self.active_future = None
        except BaseException as error:
            if not self.ready.done():
                self.ready.set_exception(error)
            if self.active_future is not None and not self.active_future.done():
                self.active_future.set_exception(GateError("disconnected", "MCP transport closed"))
        finally:
            self.alive = False
            while not self.queue.empty():
                item = self.queue.get_nowait()
                if item is not None and not item[2].done():
                    item[2].set_exception(GateError("disconnected", "MCP transport closed"))

    async def call(self, name, arguments):
        if not self.alive:
            raise GateError("disconnected", "MCP connection is not alive")
        future = asyncio.get_running_loop().create_future()
        await self.queue.put((name, arguments, future))
        try:
            return await future
        except asyncio.CancelledError:
            if self.active_future is future and self.active is not None:
                self.active.cancel()
            raise

    async def close(self):
        if self.active:
            self.active.cancel()
        if self.worker:
            if self.alive:
                await self.queue.put(None)
            else:
                self.worker.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(self.worker), timeout=10)
            except BaseException:
                self.worker.cancel()
                await asyncio.gather(self.worker, return_exceptions=True)
            self.worker = None
        self.alive = False


def rea_result(raw):
    """Do not flatten provider raw_result into normalized Evidence."""
    if raw.get("isError"):
        return None
    structured = raw.get("structuredContent")
    if structured is not None:
        return structured.get("normalized_result", structured.get("result", structured))
    return None


def expand_availability(raw):
    result = rea_result(raw)
    if not isinstance(result, dict) or "tool_availability" not in result:
        raise GateError("needs_context", "REA session did not supply a recognized tool_availability contract")
    inventory = result["tool_availability"]
    entries = {}
    for group in inventory.get("groups", []):
        facts = {k: v for k, v in group.items() if k != "names"}
        facts.setdefault("client_requirements", inventory.get("client_requirements"))
        for name in group["names"]:
            entries[name] = facts
    return entries
