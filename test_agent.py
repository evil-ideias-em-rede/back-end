"""Executa um prompt contra o grafo sem precisar subir o FastAPI.

Exemplos:
    python3 test_agent.py "Crie uma atividade sobre democracia"
    python3 test_agent.py --user-id usuario-1 --chat-id chat-1 "Faça um plano de aula"
    python3 test_agent.py
"""

import argparse
import asyncio
import sys
from uuid import uuid4

from langchain_core.messages import HumanMessage

from graph.main import GRAPH_BUILDER


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Testa um agente do backend")
    parser.add_argument("prompt", nargs="*", help="Prompt enviado ao agente")
    parser.add_argument(
        "--user-id",
        default="teste-user",
        help="Identificador do usuário dono do sandbox",
    )
    parser.add_argument(
        "--chat-id",
        default=None,
        help="Identificador do chat; reutilize-o para testar persistência",
    )
    parser.add_argument(
        "--agent-name",
        default=None,
        help="Agente: brainstorm, lesson_plan, debate, political_leteracy ou generic",
    )
    return parser.parse_args()


async def run(prompt: str, user_id: str, chat_id: str, agent_name: str | None) -> str:
    state = {
        "messages": [HumanMessage(content=prompt)],
        "user_id": user_id,
        "chat_id": chat_id,
        "context": None,
        "agent_name": agent_name,
        "selected_agent": None,
        "next_node": None,
    }
    config = { "configurable": { "user_id": user_id, "thread_id": chat_id, }}

    result = await GRAPH_BUILDER.ainvoke(state, config=config)
    return str(result["messages"][-1].content)


def main() -> int:
    args = parse_args()
    prompt = " ".join(args.prompt).strip()
    if not prompt:
        prompt = input("Prompt> ").strip()
    if not prompt:
        print("Erro: informe um prompt.", file=sys.stderr)
        return 2

    chat_id = args.chat_id or f"teste-chat-{10}"
    print(f"user_id: {args.user_id}")
    print(f"chat_id:  {chat_id}")
    print("\nResposta do agente:\n")

    try:
        resposta = asyncio.run(run(prompt, args.user_id, chat_id, args.agent_name))
    except Exception as exc:
        print(f"Erro ao executar o agente: {exc}", file=sys.stderr)
        return 1

    print(resposta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
