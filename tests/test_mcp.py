import pytest
from mcp import Client

from support_bot.mcp_server import mcp


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_mcp_exposes_read_tools_only():
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.list_tools()
    names = {t.name for t in result.tools}
    assert names == {"verify_customer", "lookup_order", "check_policy", "escalate_to_human"}
