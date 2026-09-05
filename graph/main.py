from langgraph.graph import END, START, StateGraph

from .agent.brain_stom_node import brain_storm_node
from .agent.debate_outline_node import debate_outline_node
from .agent.generic_activity_node import generic_activity_node
from .agent.lesson_plan_node import lesson_plan_node
from .agent.political_leteracy_node import political_leteracy_node
from .router_state import router_state
from .state import ChatGraphState


graph = StateGraph(ChatGraphState)
graph.add_node("router", router_state)
graph.add_node("brain_storm_node", brain_storm_node)
graph.add_node("lesson_plan_node", lesson_plan_node)
graph.add_node("debate_outline_node", debate_outline_node)
graph.add_node("political_leteracy_node", political_leteracy_node)
graph.add_node("generic_activity_node", generic_activity_node)
graph.add_edge(START, "router")


def route_to_agent(state):
    return state["selected_agent"]


AGENT_NODES = {
    "brain_storm_node": "brain_storm_node",
    "lesson_plan_node": "lesson_plan_node",
    "debate_outline_node": "debate_outline_node",
    "political_leteracy_node": "political_leteracy_node",
    "generic_activity_node": "generic_activity_node",
}

graph.add_conditional_edges("router", route_to_agent, AGENT_NODES)
for node_name in AGENT_NODES:
    graph.add_edge(node_name, END)

# O roteador escolhe um único nó. Esse nó roda seu ciclo de ferramentas e a
# única transição possível depois dele é END.
GRAPH_BUILDER = graph.compile()
