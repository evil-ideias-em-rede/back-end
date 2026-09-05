from collections.abc import Mapping


AGENTS = (
    "brain_storm_node",
    "lesson_plan_node",
    "debate_outline_node",
    "political_leteracy_node",
    "generic_activity_node",
)

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


def _last_text(state) -> str:
    messages = state.get("messages", [])
    if not messages:
        return ""
    content = messages[-1].content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            str(item.get("text", ""))
            for item in content
            if isinstance(item, Mapping) and item.get("type") in {"text", "input_text"}
        )
    return str(content or "")


def router_state(state) -> dict:
    """Escolhe exatamente um agente para este turno."""
    requested_agent = state.get("agent_name")
    if requested_agent:
        selected = resolve_agent_name(requested_agent)
        return {"selected_agent": selected, "next_node": selected}

    text = _last_text(state).lower()
    scores = {agent: 0 for agent in AGENTS}
    keywords = {
        "brain_storm_node": ("brainstorm", "ideias", "ideia", "possibilidades"),
        "lesson_plan_node": ("plano de aula", "plano", "aula", "sequência didática"),
        "debate_outline_node": ("debate", "debater", "argumentos", "júri"),
        "political_leteracy_node": ("dados", "gráfico", "estatística", "letramento", "eleitoral"),
    }
    for agent, terms in keywords.items():
        scores[agent] = sum(term in text for term in terms)

    selected = max(AGENTS, key=lambda agent: scores[agent])
    # Empates e pedidos sem intenção específica caem em um único agente
    # genérico; nunca há fan-out para mais de um agente.
    if max(scores.values()) == 0 or list(scores.values()).count(max(scores.values())) > 1:
        selected = "generic_activity_node"
    return {"selected_agent": selected, "next_node": selected}
