from mcp.server.fastmcp import FastMCP

from healthos_ai.teams import TEAM_DEFINITIONS

mcp = FastMCP("HealthOS AI Catalog", stateless_http=True, json_response=True)


@mcp.tool()
def list_agent_teams() -> list[dict[str, str]]:
    """List HealthOS agent teams. Execution remains protected by the REST identity boundary."""
    return [
        {"name": name.value, "description": definition.description}
        for name, definition in TEAM_DEFINITIONS.items()
    ]


@mcp.tool()
def healthcare_ai_safety_policy() -> dict[str, str]:
    """Return the mandatory high-impact decision safety policy."""
    return {
        "clinical": "Decision support only; licensed clinician review is required.",
        "insurance": "No autonomous final coverage or claim determination.",
        "privacy": "Use only authorized minimum-necessary data and never cross tenant boundaries.",
    }


mcp_app = mcp.streamable_http_app()
