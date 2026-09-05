from langchain_core.messages import AIMessage, HumanMessage

from db.queries import add_chat_message, update_at_by_chat_tab_id
from graph.main import GRAPH_BUILDER
from graph.tools.sandbox.workdir import workspace_for_chat

ROLE_TO_MESSAGE = {"user": HumanMessage, "assistant": AIMessage}


def _to_langchain_messages(rows) -> list:
    return [ROLE_TO_MESSAGE[row["role"]](content=row["content"]) for row in rows]


async def run_chat_turn(
    pool,
    *,
    user_id: str,
    chat_id: str,
    chat_messages: list,
    context: str | None,
    user_input: str,
    agent_name: str,
) -> str:
    """
    Recebe o histórico já carregado e validado (dono do chat conferido antes
    de chegar aqui), roda uma rodada do grafo e persiste user+assistant.
    """
    history = _to_langchain_messages(chat_messages)
    history.append(HumanMessage(content=user_input))

    initial_state = {
        "messages": history,
        "chat_id": chat_id,
        "user_id": user_id,
        "context": context,
        "agent_name": agent_name,
        "selected_agent": None,
        "next_node": None,
    }

    # A única configuração de filesystem do turno é calculada pelo backend.
    # O modelo nunca recebe um caminho escolhido pelo cliente/agente.
    graph_config = {
        "configurable": {
            "thread_id": chat_id,
            "user_id": user_id,
            "work_dir": str(workspace_for_chat(user_id, chat_id)),
        }
    }
    result = await GRAPH_BUILDER.ainvoke(initial_state, config=graph_config)
    assistant_text = result["messages"][-1].content

    async with pool.acquire() as conn:
        await add_chat_message(conn, chat_id, "user", user_input, None)
        await add_chat_message(conn, chat_id, "assistant", assistant_text, None)
        await update_at_by_chat_tab_id(conn, chat_id)

    return assistant_text
