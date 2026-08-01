from langgraph.graph import StateGraph

from healthos_ai.agents.factory import new_workflow


def test_workflow_factory_returns_uncompiled_graph() -> None:
    graph = new_workflow()

    assert isinstance(graph, StateGraph)
