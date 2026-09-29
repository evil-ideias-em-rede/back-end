from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from graph.tools.sandbox.execute_bash import execute_bash
from graph.tools.sandbox.suggested_files import execute_suggested_files
from graph.tools.sandbox.templates import consultar_templates
from graph.tools.sandbox.acervo import consultar_acervo
from graph.tools.sandbox.teacher_materials import consultar_materiais_professor
from graph.agent.prompts.pedagogical_rules import PEDAGOGICAL_READING_RULES
from graph.agent.prompts.template_rules import TEMPLATE_RULES
from graph.agent.prompts.brainstorm_rules import BRAINSTORM_SCOPE
from graph.tools.sandbox.workdir import workspace_for_chat
from graph.tools.retrieval.audiencias import consultar_audiencia_por_id
from graph.tools.retrieval.tool_buscar_audiencias import buscar_audiencias
from graph.tools.retrieval.tool_consultar_audiencias_sql import consultar_audiencias_sql
from graph.tools.retrieval.tool_consultar_bncc import consultar_bncc
from graph.agent.prompts.editor.rules import EDIT_RULES
from graph.agent.prompts.delivery_rules import HTML_PAGE_RULES, SUGGESTED_CHAT_RULES
from langchain_core.tools import tool

from functools import lru_cache
from langchain_openai import ChatOpenAI
from services.llm import create_chat_model
from dotenv import load_dotenv
from langchain_community.tools.tavily_search import TavilySearchResults


@tool
def web_search(query: str) -> str:
    """
    Realiza busca na web.

    Args:
        - query(str): consulta do usuário.

    Returns:
        Retorna resultados da consulta.
    """
    query = query.strip()
    if not query:
        return "Informe o que deve ser pesquisado."

    try:
        results = TavilySearchResults(max_results=3).invoke({"query": query})
    except Exception as exc:
        return f"Não foi possível realizar a busca na web: {exc}"

    if not results:
        return "Nenhum resultado encontrado."

    formatted = []
    for index, result in enumerate(results, start=1):
        title = result.get("title", "Sem título")
        url = result.get("url", "")
        content = result.get("content", "").strip()
        source = f"\nFonte: {url}" if url else ""
        formatted.append(f"{index}. {title}\n{content}{source}")

    return "\n\n".join(formatted)


# Carrega a configuração quando o agente é usado diretamente (por exemplo,
# via `python test_agent.py`), sem depender de um servidor carregar o `.env`.
load_dotenv(override=False)


@lru_cache(maxsize=1)
def get_chat_model() -> ChatOpenAI:
    return create_chat_model()


def _safe_config(state, config: RunnableConfig | None) -> RunnableConfig:
    """Fixa o workspace no par user/chat, sem aceitar caminho do modelo."""
    user_id = str(state["user_id"])
    chat_id = str(state["chat_id"])
    configured = dict((config or {}).get("configurable", {}))
    agent_name = state.get("agent_name") or configured.get("agent_name")
    configured.update(
        {
            "user_id": user_id,
            "thread_id": chat_id,
            "work_dir": str(workspace_for_chat(user_id, chat_id)),
        }
    )
    if agent_name:
        configured["agent_name"] = str(agent_name)
    return {**(config or {}), "configurable": configured}


async def run_agent(
    state,
    system_prompt: str,
    config: RunnableConfig | None = None,
    tools: list | None = None,
) -> dict:
    """Executa uma rodada do agente em streaming; o grafo decide se chama as ferramentas."""
    safe_config = _safe_config(state, config)
    is_brainstorm = state.get("agent_name") in {"brainstorm", "brainstorm_node"}
    system_text = system_prompt
    if not is_brainstorm:
        system_text += "\n\n" + HTML_PAGE_RULES + "\n\n" + TEMPLATE_RULES
        system_text += "\n\n" + PEDAGOGICAL_READING_RULES
    if not state.get("editor_mode"):
        system_text += "\n\n" + SUGGESTED_CHAT_RULES
    if state.get("context"):
        system_text += f"\n\nContexto atual autorizado para esta conversa:\n{state['context']}"
    if state.get("editor_mode"):
        system_text += f"\n\n{EDIT_RULES}"
    if tools is not None:
        agent_tools = list(tools)
    elif state.get("editor_mode"):
        # No editor, o agente só pode operar sobre os arquivos do sandbox.
        agent_tools = [execute_bash, web_search]
    else:
        agent_tools = [
            execute_suggested_files,
            consultar_audiencia_por_id,
            buscar_audiencias,
            consultar_audiencias_sql,
            consultar_bncc,
            web_search
        ]
        system_text = system_text.replace("execute_bash", execute_suggested_files.name)
    for reference_tool in (consultar_templates, consultar_acervo, consultar_materiais_professor, consultar_bncc):
        if reference_tool not in agent_tools:
            agent_tools.append(reference_tool)
    if is_brainstorm:
        system_text += "\n\n" + BRAINSTORM_SCOPE
    tool_names = ", ".join(getattr(agent_tool, "name", "ferramenta") for agent_tool in agent_tools)
    system_text += (
        f"\n\nVocê tem exatamente estas ferramentas: {tool_names}. "
        "Use-as somente conforme suas descrições. Quando concluir, responda ao usuário."
    )

    messages = [SystemMessage(content=system_text), *state.get("messages", [])]
    model = get_chat_model().bind_tools(agent_tools)
    response = None
    async for chunk in model.astream(messages, config=safe_config):
        response = chunk if response is None else response + chunk
    if response is None:
        raise RuntimeError("A LLM não retornou nenhum conteúdo")
    return {"messages": [response]}
