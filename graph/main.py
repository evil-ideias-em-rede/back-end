from typing import Optional
from langgraph.graph import MessagesState
from langgraph.prebuilt.tool_node import ToolNode
from langgraph.graph import END, START, StateGraph

from .agent.brain_stom_node import brain_storm_node
from .agent.debate_outline_node import debate_outline_node
from .agent.generic_activity_node import generic_activity_node
from .agent.lesson_plan_node import lesson_plan_node
from .agent.political_leteracy_node import political_leteracy_node
from .tools.sandbox.execute_bash import execute_bash


AGENT_NAMES = {
    "brainstorm": "brainstorm_node",
    "lesson_plan": "lesson_plan_node",
    "debate_outline": "debate_outline_node",
    "political_leteracy": "political_leteracy_node",
    "generic_activity": "generic_activity_node",
}


def resolve_agent_name(agent_name: str) -> str:
    normalized = agent_name.strip().lower()
    try: return AGENT_NAMES[normalized]
    except KeyError as exc:
        supported = "brainstorm, lesson_plan, debate, political_leteracy, generic"
        raise ValueError(f"agent_name inválido. Use um destes valores: {supported}") from exc


def router_state(state) -> dict:
    requested_agent = state.get("agent_name")
    if not requested_agent: raise ValueError("agent_name é obrigatório para selecionar o agente")
    selected = resolve_agent_name(requested_agent)
    return {"selected_agent": selected, "next_node": selected}


class ChatGraphState(MessagesState):
    chat_id: str
    user_id: str
    context: Optional[str]
    agent_name: str
    selected_agent: Optional[str]
    next_node: Optional[str]


graph = StateGraph(ChatGraphState)
graph.add_node("router", router_state)
graph.add_node("brain_storm_node", brain_storm_node)
graph.add_node("lesson_plan_node", lesson_plan_node)
graph.add_node("debate_outline_node", debate_outline_node)
graph.add_node("political_leteracy_node", political_leteracy_node)
graph.add_node("generic_activity_node", generic_activity_node)
graph.add_node("tools", ToolNode([execute_bash]))
graph.add_edge(START, "router")


def route_to_agent(state):
    return state["selected_agent"]


def route_after_agent(state):
    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", None) or []
    if not tool_calls: return "end"
    return "tools"


AGENT_NODES = {
    "brainstorm_node": "brainstorm_node",
    "lesson_plan_node": "lesson_plan_node",
    "debate_outline_node": "debate_outline_node",
    "political_leteracy_node": "political_leteracy_node",
    "generic_activity_node": "generic_activity_node",
}


graph.add_conditional_edges("router", route_to_agent, AGENT_NODES)
for node_name in AGENT_NODES:
    graph.add_conditional_edges(node_name, route_after_agent, {"tools": "tools", "end": END,},)


graph.add_conditional_edges("tools", route_to_agent, AGENT_NODES)
GRAPH_BUILDER = graph.compile()
