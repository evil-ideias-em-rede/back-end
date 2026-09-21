"""
Agente de teste simples: conecta o recuperador (busca vetorial, ver
`embeddings_index.buscar_vetorial` — estratégia padrão do recuperador,
decidida em 2026-09-17) como uma tool de LangChain num LLM com tool
calling. Serve só pra validar/demonstrar a integração num REPL de
terminal — não faz parte do grafo de agentes (`graph/main.py`), que
continua fora de escopo (empacotar como tool pro grafo real fica por
conta do time depois).

Uso:
    python agente_teste.py
"""

import asyncio
import json
import os

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from embeddings_index import buscar_vetorial, conectar

load_dotenv(override=True)

CONEXAO = conectar()


def _assunto_audiencia(ref_id: str) -> str | None:
    """Enriquece o resultado com o assunto da audiência quando o metadado
    já foi populado (`metadados_audiencias.py popular`) — opcional, o
    recuperador funciona sem isso."""
    linha = CONEXAO.execute(
        "SELECT assunto FROM audiencias WHERE ref_id = ?", (ref_id,)
    ).fetchone()
    return linha[0] if linha else None


@tool
def buscar_audiencias(pergunta: str, k: int = 5) -> str:
    """
    Busca trechos de audiências públicas da Câmara dos Deputados relevantes
    pra uma pergunta, usando busca vetorial (embeddings) sobre a
    transcrição real das audiências. Use sempre que precisar de informação
    factual sobre o que foi discutido, dito ou defendido numa audiência —
    não invente esse conteúdo.

    Args:
        pergunta: a pergunta do usuário, em linguagem natural.
        k: quantos trechos retornar (padrão 5).

    Returns:
        JSON com uma lista de resultados, cada um com: doc_id, ref_id (id
        da audiência de origem), assunto (quando disponível), distance
        (distância de cosseno — quanto menor, mais parecido) e trecho
        (texto do chunk).
    """
    resultados = buscar_vetorial(CONEXAO, pergunta, k=k)
    for r in resultados:
        r["assunto"] = _assunto_audiencia(r["ref_id"])
    return json.dumps(resultados, ensure_ascii=False)


SYSTEM_PROMPT = (
    "Você é um assistente que responde perguntas sobre audiências públicas "
    "da Câmara dos Deputados. Use a ferramenta buscar_audiencias sempre que "
    "precisar de informação factual sobre o que foi discutido nelas — não "
    "invente conteúdo de audiência. Cite a audiência (ref_id e/ou assunto) "
    "na resposta quando fizer sentido."
)


def _extrair_texto(resposta) -> str:
    conteudo = resposta.content
    if isinstance(conteudo, str):
        return conteudo
    partes = [b.get("text", "") for b in conteudo if isinstance(b, dict)]
    return "".join(partes) or str(conteudo)


async def conversar() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY não configurada.")
        return

    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL_NAME", "gpt-5.6-luna"),
        use_responses_api=True,
    ).bind_tools([buscar_audiencias])

    mensagens = [SystemMessage(content=SYSTEM_PROMPT)]

    print("Agente de teste do recuperador pronto. Digite uma pergunta (ou 'sair').")
    while True:
        pergunta = await asyncio.to_thread(input, "\nVocê> ")
        if pergunta.strip().lower() in {"sair", "exit", "quit"}:
            break
        mensagens.append(HumanMessage(content=pergunta))

        while True:
            resposta = await llm.ainvoke(mensagens)
            mensagens.append(resposta)
            chamadas = getattr(resposta, "tool_calls", None) or []
            if not chamadas:
                print(f"\nAgente> {_extrair_texto(resposta)}")
                break
            for chamada in chamadas:
                print(f"  [tool] buscar_audiencias({chamada['args']})")
                resultado = buscar_audiencias.invoke(chamada["args"])
                mensagens.append(
                    ToolMessage(content=resultado, tool_call_id=chamada["id"])
                )


if __name__ == "__main__":
    asyncio.run(conversar())
