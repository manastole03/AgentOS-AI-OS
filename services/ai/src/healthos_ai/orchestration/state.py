from typing import TypedDict


class AgentOSState(TypedDict, total=False):
    prompt: str
    requested_team: str | None
    selected_team: str
    collaborators: list[str]
    route_rationale: str
    plan: list[str]
    retrieved_context: list[str]
    memories: list[str]
    team_results: dict[str, str]
    final_response: str
    provider: str
    memory_mode: str
