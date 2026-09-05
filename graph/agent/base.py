"""Execução comum de todos os agentes.

Cada agente recebe o mesmo contrato: pode chamar somente ``execute_bash`` e,
quando terminar, devolve uma única mensagem para o grafo. Assim não há uma
cadeia de agentes nem uma segunda escolha depois do roteamento.
"""

from collections.abc import Mapping

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from config.model import get_chat_model
from graph.tools.sandbox.execute_bash import execute_bash
from graph.tools.sandbox.workdir import workspace_for_chat


MAX_TOOL_ROUNDS = 8


def _content_as_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, Mapping) and item.get("type") in {"text", "output_text"}:
                parts.append(str(item.get("text", "")))
        return "".join(parts)
    return str(content or "")


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
    last_response = None

    for _ in range(MAX_TOOL_ROUNDS):
        response = await model.ainvoke(messages, config=safe_config)
        last_response = response
        messages.append(response)
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            text = _content_as_text(response.content).strip()
            return {"messages": [AIMessage(content=text or "Concluído.")]}

        for call in tool_calls:
            call_id = call.get("id") or f"execute-bash-{_}"
            args = call.get("args") or {}
            # O schema da ferramenta impede argumentos extras; esta validação
            # mantém o erro legível caso o provedor devolva uma chamada inválida.
            if not isinstance(args, dict) or not isinstance(args.get("comando"), str):
                result = (
                    '{"stdout":"","stderr":"A chamada deve conter '
                    'o argumento string comando","returncode":-1,"sucesso":false}'
                )
            else:
                result = await execute_bash.ainvoke(
                    {"comando": args["comando"]}, config=safe_config
                )
            messages.append(ToolMessage(content=str(result), tool_call_id=call_id))

    # Evita deixar o grafo preso se o modelo insistir indefinidamente em
    # ferramentas. Ainda assim há sempre uma mensagem final e o grafo termina.
    fallback = _content_as_text(getattr(last_response, "content", "")).strip()
    return {
        "messages": [
            AIMessage(
                content=fallback
                or "Não consegui concluir a tarefa dentro do limite de operações."
            )
        ]
    }
