from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from graph.tools.sandbox.execute_bash import execute_bash
from graph.tools.sandbox.workdir import workspace_for_chat

import os
from dotenv import load_dotenv
from functools import lru_cache
from langchain_openai import ChatOpenAI
load_dotenv(override=True)


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


async def run_agent(state, system_prompt: str, config: RunnableConfig | None = None) -> dict:
    """Executa uma rodada do agente; o grafo decide se chama as ferramentas."""
    safe_config = _safe_config(state, config)
    system_text = system_prompt
    if state.get("context"):
        system_text += f"\n\nContexto persistido deste chat:\n{state['context']}"
    system_text += (
        "\n\nVocê tem exatamente uma ferramenta: execute_bash. "
        "Use-a somente no workspace /workspace. Quando concluir, responda ao usuário."
    )

    messages = [SystemMessage(content=system_text), *state.get("messages", [])]
    model = get_chat_model().bind_tools([execute_bash])
    response = await model.ainvoke(messages, config=safe_config)
    return {"messages": [response]}
