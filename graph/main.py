from typing import Optional
from langgraph.graph import MessagesState
from langgraph.prebuilt.tool_node import ToolNode
from langgraph.graph import END, START, StateGraph

from .agent.brain_stom_node import brainstorm_node, execute_planning_bash
from .agent.debate_outline_node import debate_outline_node
from .agent.generic_activity_node import generic_activity_node
from .agent.lesson_plan_node import lesson_plan_node
from .agent.political_leteracy_node import political_leteracy_node
from .tools.sandbox.execute_bash import execute_bash


AGENTS = [
    {"agent_name": "brainstorm_node", "agent_function": brainstorm_node},
    {"agent_name": "lesson_plan_node", "agent_function": lesson_plan_node},
    {"agent_name": "debate_outline_node", "agent_function": debate_outline_node},
    {"agent_name": "political_leteracy_node", "agent_function": political_leteracy_node},
    {"agent_name": "generic_activity_node", "agent_function": generic_activity_node}
]

AGENT_NAMES = {}
for agent in AGENTS:
    AGENT_NAMES[agent["agent_name"]] = agent

def resolve_agent_name(agent_name: str) -> str:
    normalized = agent_name.strip().lower()
    if normalized not in AGENT_NAMES:
        supported = ", ".join(list(AGENT_NAMES.keys()))
        raise ValueError(f"agent_name inválido. Use um destes valores: {supported}")

    return normalized


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
for agent_name, agent in AGENT_NAMES.items():
    graph.add_node(agent_name, agent["agent_function"])
graph.add_node("tools", ToolNode([execute_bash, execute_planning_bash]))
graph.add_edge(START, "router")


def route_to_agent(state):
    return state["selected_agent"]


def route_after_agent(state):
    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", None) or []
    if not tool_calls: return "end"
    return "tools"


AGENT_NODES = {}
for agent in AGENT_NAMES:
    AGENT_NODES[agent] = agent

graph.add_conditional_edges("router", route_to_agent, AGENT_NODES)
for node_name in AGENT_NODES:
    graph.add_conditional_edges(node_name, route_after_agent, {"tools": "tools", "end": END,},)


graph.add_conditional_edges("tools", route_to_agent, AGENT_NODES)
GRAPH_BUILDER = graph.compile()
