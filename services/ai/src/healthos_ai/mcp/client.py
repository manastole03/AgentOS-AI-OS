from typing import Any, cast

from langchain_mcp_adapters.client import MultiServerMCPClient

from healthos_ai.config import Settings


async def load_mcp_tools(settings: Settings) -> list[Any]:
    if not settings.mcp_servers:
        return []
    tools = await MultiServerMCPClient(cast(Any, settings.mcp_servers)).get_tools()
    if not settings.mcp_tool_allowlist:
        return tools
    allowed = set(settings.mcp_tool_allowlist)
    return [tool for tool in tools if tool.name in allowed]
