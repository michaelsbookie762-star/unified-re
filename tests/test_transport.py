import asyncio
import sys

import pytest

from unified_re.common import GateError, ROOT
from unified_re.transport import Connection, expand_availability


def configuration():
    return {"command": sys.executable, "args": ["-X", "utf8", str(ROOT / "tests/fixture_mcp.py")], "call_timeout": 8}


@pytest.mark.asyncio
async def test_actual_protocol_abrupt_eof_never_silently_reconnects():
    connection = Connection(configuration())
    await connection.start()
    try:
        with pytest.raises(Exception):
            await asyncio.wait_for(connection.call("abrupt_disconnect", {}), 10)
        # The owner worker completes transport finalization; no replacement is
        # created and no previous context is reported alive.
        await asyncio.wait_for(asyncio.shield(connection.worker), 10)
        assert connection.alive is False
        with pytest.raises(GateError) as error:
            await connection.call("typed_error", {})
        assert error.value.status == "disconnected"
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_real_protocol_error_flag_is_kept():
    connection = Connection(configuration())
    await connection.start()
    try:
        raw = await connection.call("typed_error", {})
        assert raw["isError"] is True
        assert raw["content"]
        # SDK intentionally hides the Python exception message; the wire error
        # is what this gateway must preserve, not an invented traceback.
        assert "typed_error" in str(raw["content"])
    finally:
        await connection.close()


def test_unknown_availability_contract_does_not_mean_available():
    with pytest.raises(GateError) as error:
        expand_availability({"structuredContent": {"result": {"open": False}}})
    assert error.value.status == "needs_context"
