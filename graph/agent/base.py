from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from graph.tools.sandbox.execute_bash import execute_bash
from graph.tools.sandbox.workdir import workspace_for_chat

import os
from dotenv import load_dotenv
from functools import lru_cache
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv


# Carrega a configuração quando o agente é usado diretamente (por exemplo,
# via `python test_agent.py`), sem depender de um servidor carregar o `.env`.
load_dotenv(override=False)


@lru_cache(maxsize=1)
def get_chat_model() -> ChatOpenAI:
    return ChatOpenAI(model=os.getenv("OPENAI_MODEL_NAME", "gpt-5.6-luna"), use_responses_api=True,)


def _safe_config(state, config: RunnableConfig | None) -> RunnableConfig:
    """Fixa o workspace no par user/chat, sem aceitar caminho do modelo."""
    user_id = str(state["user_id"])
    chat_id = str(state["chat_id"])
    configured = dict((config or {}).get("configurable", {}))
    configured.update(
        {
            "user_id": user_id,
            "thread_id": chat_id,
            "work_dir": str(workspace_for_chat(user_id, chat_id)),
        }
    )
    return {**(config or {}), "configurable": configured}


async def run_agent(
    state,
    system_prompt: str,
    config: RunnableConfig | None = None,
    tools: list | None = None,
) -> dict:
    """Executa uma rodada do agente em streaming; o grafo decide se chama as ferramentas."""
    safe_config = _safe_config(state, config)
    system_text = system_prompt
    if state.get("context"):
        system_text += f"\n\nContexto persistido deste chat:\n{state['context']}"
    agent_tools = tools or [execute_bash]
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
