import asyncio
from typing import Any, cast

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from healthos_ai.config import Settings
from healthos_ai.llm import LLMGateway
from healthos_ai.memory import MemoryHit, MemoryRepository
from healthos_ai.observability.audit import AuditLogger, Timer
from healthos_ai.observability.metrics import AI_MODEL_CALLS
from healthos_ai.orchestration.context import RuntimeContext
from healthos_ai.orchestration.state import AgentOSState
from healthos_ai.rag import KnowledgeRepository
from healthos_ai.teams import TeamName
from healthos_ai.teams.factory import TeamAgentFactory, message_text


class RouteDecision(BaseModel):
    primary_team: TeamName
    collaborators: list[TeamName] = Field(default_factory=list, max_length=2)
    rationale: str = Field(max_length=500)


class Plan(BaseModel):
    steps: list[str] = Field(min_length=1, max_length=8)


class AgentOrchestrator:
    def __init__(
        self,
        settings: Settings,
        llm: LLMGateway,
        teams: TeamAgentFactory,
        knowledge: KnowledgeRepository,
        memories: MemoryRepository,
        audit: AuditLogger,
        checkpointer: Any = None,
    ) -> None:
        self._settings, self._llm, self._teams = settings, llm, teams
        self._knowledge, self._memories, self._audit = knowledge, memories, audit
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_team_agents)
        self.graph: Any = self._build().compile(checkpointer=checkpointer)

    def _build(
        self,
    ) -> StateGraph[AgentOSState, RuntimeContext, AgentOSState, AgentOSState]:
        graph = StateGraph(AgentOSState, context_schema=RuntimeContext)
        graph.add_node("route", self._route)
        graph.add_node("plan", self._plan)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("execute", self._execute)
        graph.add_node("synthesize", self._synthesize)
        graph.add_edge(START, "route")
        graph.add_edge("route", "plan")
        graph.add_edge("plan", "retrieve")
        graph.add_edge("retrieve", "execute")
        graph.add_edge("execute", "synthesize")
        graph.add_edge("synthesize", END)
        return graph

    async def _route(self, state: AgentOSState, runtime: Runtime[RuntimeContext]) -> dict[str, Any]:
        if state.get("requested_team"):
            selected = state["requested_team"]
            if selected not in runtime.context.allowed_teams:
                raise PermissionError("Requested agent team is not authorized")
            return {
                "selected_team": selected,
                "collaborators": [],
                "route_rationale": "Explicitly requested by actor.",
            }
        prompt = (
            "Route this request to exactly one primary HealthOS team and at most two "
            f"collaborators. Allowed teams: {', '.join(runtime.context.allowed_teams)}. "
            "Reject no request; choose the safest relevant team."
        )
        model = self._llm.chat(self._settings.router_model, state.get("provider", "auto"))
        try:
            decision = cast(
                RouteDecision,
                await model.with_structured_output(RouteDecision).ainvoke(
                    [SystemMessage(content=prompt), HumanMessage(content=state["prompt"])]
                ),
            )
            allowed = set(runtime.context.allowed_teams)
            primary = decision.primary_team.value
            if primary not in allowed:
                primary = runtime.context.allowed_teams[0]
            collaborators = [
                item.value
                for item in decision.collaborators
                if item.value in allowed and item.value != primary
            ][:2]
            AI_MODEL_CALLS.labels(self._settings.router_model, "success").inc()
            return {
                "selected_team": primary,
                "collaborators": collaborators,
                "route_rationale": decision.rationale,
            }
        except Exception:
            AI_MODEL_CALLS.labels(self._settings.router_model, "failure").inc()
            raise

    async def _plan(self, state: AgentOSState, runtime: Runtime[RuntimeContext]) -> dict[str, Any]:
        model = self._llm.chat(self._settings.planner_model, state.get("provider", "auto"))
        result = cast(
            Plan,
            await model.with_structured_output(Plan).ainvoke(
                [
                    SystemMessage(
                        content=(
                            "Create a short execution plan. Return action steps, not private "
                            "chain-of-thought. Include retrieval and human review when relevant."
                        )
                    ),
                    HumanMessage(
                        content=f"Team: {state['selected_team']}\nRequest: {state['prompt']}"
                    ),
                ]
            ),
        )
        return {"plan": result.steps}

    async def _retrieve(
        self, state: AgentOSState, runtime: Runtime[RuntimeContext]
    ) -> dict[str, Any]:
        team = state["selected_team"]
        knowledge_task = self._knowledge.search(
            tenant_id=runtime.context.tenant_id, team=team, query=state["prompt"]
        )
        if state.get("memory_mode") == "none":
            memory_hits: list[MemoryHit] = []
            knowledge_hits = await knowledge_task
        else:
            knowledge_hits, memory_hits = await asyncio.gather(
                knowledge_task,
                self._memories.search(
                    tenant_id=runtime.context.tenant_id,
                    owner_user_id=runtime.context.actor_user_id,
                    team=team,
                    query=state["prompt"],
                ),
            )
        return {
            "retrieved_context": [f"[chunk:{hit.id}] {hit.content}" for hit in knowledge_hits],
            "memories": [f"[{hit.category}] {hit.content}" for hit in memory_hits],
        }

    async def _run_team(
        self, team: str, state: AgentOSState, base: RuntimeContext
    ) -> tuple[str, str]:
        context = RuntimeContext(
            run_id=base.run_id,
            thread_id=base.thread_id,
            actor_user_id=base.actor_user_id,
            tenant_id=base.tenant_id,
            account_type=base.account_type,
            team=team,
            allowed_teams=base.allowed_teams,
            memory_mode=base.memory_mode,
        )
        shared = "\n".join([*state.get("retrieved_context", []), *state.get("memories", [])])
        prior_results = "\n\n".join(
            f"[{name} team]\n{value}" for name, value in state.get("team_results", {}).items()
        )
        task = (
            f"User request:\n{state['prompt']}\n\nExecution plan:\n- "
            + "\n- ".join(state.get("plan", []))
            + f"\n\nShared authorized context:\n{shared or 'No retrieved context.'}\n"
            + f"\nPrior team results:\n{prior_results or 'No prior team result.'}\n"
            f"Collaborating teams: {', '.join(state.get('collaborators', [])) or 'none'}."
        )
        timer = Timer()
        async with self._semaphore:
            result = await self._teams.create(
                TeamName(team), state.get("provider", "auto")
            ).ainvoke(
                {"messages": [HumanMessage(content=task)]},
                context=context,
                config={"configurable": {"thread_id": str(base.thread_id)}},
            )
        messages = result.get("messages", [])
        text = message_text(messages[-1]) if messages else "No team response."
        await self._audit.record(
            tenant_id=base.tenant_id,
            run_id=base.run_id,
            actor_user_id=base.actor_user_id,
            event_type="team.completed",
            team=team,
            duration_ms=timer.milliseconds,
        )
        return team, text

    async def _execute(
        self, state: AgentOSState, runtime: Runtime[RuntimeContext]
    ) -> dict[str, Any]:
        primary = await self._run_team(state["selected_team"], state, runtime.context)
        results = {primary[0]: primary[1]}
        collaborators = state.get("collaborators", [])
        if collaborators:
            completed = await asyncio.gather(
                *(
                    self._run_team(team, {**state, "team_results": results}, runtime.context)
                    for team in collaborators
                )
            )
            results.update(completed)
        return {"team_results": results}

    async def _synthesize(
        self, state: AgentOSState, runtime: Runtime[RuntimeContext]
    ) -> dict[str, Any]:
        model = self._llm.chat(self._settings.synthesizer_model, state.get("provider", "auto"))
        evidence = "\n\n".join(
            f"## {team}\n{value}" for team, value in state["team_results"].items()
        )
        response = await model.ainvoke(
            [
                SystemMessage(
                    content=(
                        "Synthesize the agent-team results into one safe, concise answer. "
                        "Preserve citations. Never add unsupported facts. Clearly flag human "
                        "review and urgent-care guidance when appropriate."
                    )
                ),
                HumanMessage(content=f"Request:\n{state['prompt']}\n\nTeam results:\n{evidence}"),
            ]
        )
        return {"final_response": message_text(response)}
