AGENT_NAMES = {
    "brainstorm": "brain_storm_node",
    "lesson_plan": "lesson_plan_node",
    "debate": "debate_outline_node",
    "political_leteracy": "political_leteracy_node",
    "generic": "generic_activity_node",
}


def resolve_agent_name(agent_name: str) -> str:
    normalized = agent_name.strip().lower()
    try:
        return AGENT_NAMES[normalized]
    except KeyError as exc:
        supported = "brainstorm, lesson_plan, debate, political_leteracy, generic"
        raise ValueError(f"agent_name inválido. Use um destes valores: {supported}") from exc


def router_state(state) -> dict:
    """Escolhe exatamente o agente informado pelo backend."""
    requested_agent = state.get("agent_name")
    if not requested_agent:
        raise ValueError("agent_name é obrigatório para selecionar o agente")

    selected = resolve_agent_name(requested_agent)
    return {"selected_agent": selected, "next_node": selected}
