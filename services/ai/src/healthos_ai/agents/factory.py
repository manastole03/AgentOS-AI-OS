from langgraph.graph import StateGraph

from healthos_ai.orchestration.state import AgentOSState
from healthos_ai.teams.factory import TeamAgentFactory


def new_workflow() -> StateGraph[AgentOSState, None, AgentOSState, AgentOSState]:
    """Return the typed outer graph builder for extensions and structural tests."""
    return StateGraph(AgentOSState)


__all__ = ["TeamAgentFactory", "new_workflow"]
