"""Project-local stdio MCP. Stdout is reserved for protocol frames."""
from contextlib import asynccontextmanager
from typing import Any

from mcp.server import MCPServer

from .common import GateError, ROOT, read_json
from .engine import Engine

engine = None


@asynccontextmanager
async def lifespan(server):
    global engine
    engine = Engine()
    try:
        yield engine
    finally:
        await engine.close()


server = MCPServer("unified-re", version="0.1.0", lifespan=lifespan)


def guarded(function):
    import functools
    import inspect
    if inspect.iscoroutinefunction(function):
        @functools.wraps(function)
        async def asynchronous(*args, **kwargs):
            try:
                return await function(*args, **kwargs)
            except GateError as error:
                return error.as_dict()
        return asynchronous
    @functools.wraps(function)
    def synchronous(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except GateError as error:
            return error.as_dict()
    return synchronous


@server.tool(structured_output=True)
@guarded
async def capability_search(query: str, limit: int = 12, kind: str | None = None) -> dict[str, Any]:
    """中英向量 + BM25 召回 Skill/工具候选。只检索，不执行；相似度不是置信度。kind 可为 skill/tool。"""
    return engine.search(query, limit, kind)


@server.tool(structured_output=True)
@guarded
async def task_plan(request: str, target_path: str | None = None, context: dict | None = None) -> dict[str, Any]:
    """检索、只读辨型、真实 REA 可用性检查及冲突裁决。context.permissions 需声明已获授权的 read_local；返回可审查分阶段计划或明确阻塞状态。"""
    return await engine.plan(request, target_path, context)


@server.tool(structured_output=True)
@guarded
async def task_status(task_id: str) -> dict[str, Any]:
    """读取持久任务状态、目标、计划修订号、会话代次和证据引用；历史状态不等于在线。"""
    return engine.get(task_id)


@server.tool(structured_output=True)
@guarded
async def stage_load(task_id: str, revision: int) -> dict[str, Any]:
    """只加载当前阶段的主 Skill、补充说明及选定工具原始定义；不注入两个总控或全部目录。"""
    return engine.load_stage(task_id, revision)


@server.tool(structured_output=True)
@guarded
async def reference_load(task_id: str, revision: int, path: str, offset: int = 0, limit: int = 4000) -> dict[str, Any]:
    """按页读取当前阶段已选专项的允许文档；原始总控、秘密文件及任意文件读取均被拒绝。"""
    return engine.load_reference(task_id, revision, path, offset, limit)


@server.tool(structured_output=True)
@guarded
async def gateway_call(task_id: str, revision: int, tool_id: str, arguments: dict) -> dict[str, Any]:
    """核对计划、原始参数 schema、目标哈希与实时可用性后调用；保留完整原始 MCP 结果、isError 和来源。不会静默切换后端。"""
    return await engine.call(task_id, revision, tool_id, arguments)


@server.tool(structured_output=True)
@guarded
async def stage_advance(task_id: str, revision: int) -> dict[str, Any]:
    """仅在当前阶段所需调用成功后进入下一阶段。最终阶段须先提交报告。"""
    result = engine.advance(task_id, revision)
    if result["status"] == "completed":
        await engine.drop_connection(task_id)
    return result


@server.tool(structured_output=True)
@guarded
async def task_report(task_id: str, revision: int, markdown: str, evidence_ids: list[str]) -> dict[str, Any]:
    """以本任务当前会话的证据引用提交报告；不将不同来源证据伪装为等价。"""
    return engine.report(task_id, revision, markdown, evidence_ids)


@server.tool(structured_output=True)
@guarded
async def task_cancel(task_id: str) -> dict[str, Any]:
    """取消本任务调用并关闭本服务拥有的会话；不关闭用户 GUI 数据库或其它任务资源。"""
    return await engine.cancel(task_id)


@server.tool(structured_output=True)
@guarded
async def task_revise(task_id: str, revision: int, target_path: str | None = None, context: dict | None = None) -> dict[str, Any]:
    """显式改计划、切换目标或重连。递增修订号和会话代次，旧引用保留但不可在新会话继续使用。"""
    return await engine.revise(task_id, revision, target_path, context)


@server.tool(structured_output=True)
@guarded
async def task_journal(task_id: str) -> dict[str, Any]:
    """读取本服务记录的状态变化和证据引用，不扫描外部文件。"""
    engine.store.get(task_id)
    return {"task_id": task_id, "events": engine.store.events(task_id)}


@server.tool(structured_output=True)
@guarded
async def backend_status() -> dict[str, Any]:
    """区分审计快照、协议发现、实际调用与当前服务会话；快照不宣称实时在线。"""
    discovery = read_json(ROOT / "reports/discovery.json")
    sources = {key: {"audit_status": value.get("status"), "advertised_tool_count": len(value.get("tools", [])), "audit_tool_call_verified": value.get("tool_call_verified", False), "engine_status": value.get("engine_status", "unknown")} for key, value in discovery["sources"].items()}
    return {"snapshot_observed_at": discovery["observed_at"], "sources": sources, "skipped": discovery["skipped"], "live_owned_sessions": [{"task_id": key, "alive": conn.alive, "source": "rea"} for key, conn in engine.connections.items()], "leases": engine.store.leases(), "warning": "Tool catalog and historical discovery do not prove a live analysis engine"}


def main():
    server.run()


if __name__ == "__main__":
    main()
