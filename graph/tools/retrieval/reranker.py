"""
Reranking via LLM em cima dos candidatos do FTS5 (ver `fts_index.py`).

Pipeline: `buscar()` traz um pool de candidatos (k alto, ex. 50) por
BM25 — barato, mas cego a sinonímia ("mãe" não bate com "materna"). O LLM
lê a pergunta + o trecho de cada candidato e devolve só os doc_ids que de
fato respondem, ordenados por relevância — filtra, não só reordena.

Uso:
    python reranker.py "<pergunta>" -k 50 --k-final 10
"""

import json
import os
import sqlite3
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from openai import OpenAI
from pydantic import BaseModel, Field

load_dotenv(override=True)

MODELO_PADRAO = os.getenv("OPENAI_MODEL_NAME", "gpt-5.6-luna")
MODELO_EMBEDDING_PADRAO = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

_PROMPT_SISTEMA = """\
Você recebe uma pergunta e uma lista de trechos de transcrições de \
audiências públicas da Câmara dos Deputados, cada um identificado por um \
doc_id.

Devolva os doc_ids dos trechos que REALMENTE ajudam a responder a \
pergunta, ordenados do mais para o menos relevante. Não inclua trechos \
apenas remotamente relacionados ao tema — só os que sustentam uma \
resposta. Pode devolver uma lista vazia se nenhum trecho responder à \
pergunta. Nunca invente um doc_id que não esteja na lista."""


class ResultadoRerank(BaseModel):
    doc_ids_relevantes: list[str] = Field(
        description=(
            "doc_ids dos candidatos relevantes para a pergunta, ordenados "
            "do mais para o menos relevante. Vazio se nenhum responder."
        )
    )


def _montar_prompt_usuario(pergunta: str, candidatos: list[dict]) -> str:
    linhas = [f"Pergunta: {pergunta}", "", "Candidatos:"]
    for candidato in candidatos:
        trecho = candidato.get("trecho") or candidato.get("texto") or ""
        linhas.append(f"- doc_id={candidato['doc_id']}: {trecho}")
    return "\n".join(linhas)


def _modelo_rerank(modelo: str) -> ChatOpenAI:
    return ChatOpenAI(model=modelo, temperature=0).with_structured_output(ResultadoRerank)


def reranquear(
    pergunta: str,
    candidatos: list[dict],
    k_final: int = 10,
    modelo: str = MODELO_PADRAO,
) -> list[dict]:
    """
    Reordena/filtra `candidatos` (saída de `fts_index.buscar()`) via LLM.
    Retorna os `k_final` primeiros doc_ids que o LLM marcou como
    relevantes, na ordem dele, cada um com o dict original enriquecido com
    `posicao_rerank`. Se o LLM não achar nada relevante, retorna [].

    doc_ids que o LLM alucinar (fora da lista de candidatos) são
    descartados silenciosamente — nunca inventamos metadado pra eles.
    """
    if not candidatos:
        return []

    candidatos_por_id = {c["doc_id"]: c for c in candidatos}
    resposta: ResultadoRerank = _modelo_rerank(modelo).invoke(
        [
            ("system", _PROMPT_SISTEMA),
            ("user", _montar_prompt_usuario(pergunta, candidatos)),
        ]
    )

    resultado = []
    for posicao, doc_id in enumerate(resposta.doc_ids_relevantes):
        candidato = candidatos_por_id.get(doc_id)
        if candidato is None:
            continue
        resultado.append({**candidato, "posicao_rerank": posicao})
        if len(resultado) >= k_final:
            break
    return resultado


def _buscar_textos_completos(conexao: sqlite3.Connection, doc_ids: list[str]) -> dict[str, str]:
    marcadores = ",".join("?" * len(doc_ids))
    cursor = conexao.execute(
        f"SELECT doc_id, texto FROM documentos WHERE doc_id IN ({marcadores})", doc_ids
    )
    return dict(cursor.fetchall())


def _cosseno(a: list[float], b: list[float]) -> float:
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def reranquear_embeddings(
    conexao: sqlite3.Connection,
    pergunta: str,
    candidatos: list[dict],
    k_final: int = 10,
    modelo: str = MODELO_EMBEDDING_PADRAO,
) -> list[dict]:
    """
    Reordena `candidatos` (saída de `fts_index.buscar()`) por similaridade
    de cosseno entre o embedding da pergunta e o embedding do TEXTO
    COMPLETO de cada chunk (não o snippet truncado do FTS5 — ver
    `reranquear()`, cujo viés de falso-negativo veio exatamente de julgar
    com contexto curto demais). Sempre retorna `k_final` candidatos (só
    reordena, não filtra — embeddings não têm noção de "relevante o
    suficiente", só de distância).
    """
    if not candidatos:
        return []

    doc_ids = [c["doc_id"] for c in candidatos]
    textos = _buscar_textos_completos(conexao, doc_ids)

    cliente = OpenAI()
    resposta = cliente.embeddings.create(
        model=modelo, input=[pergunta] + [textos[doc_id] for doc_id in doc_ids]
    )
    vetores = [item.embedding for item in resposta.data]
    vetor_pergunta, vetores_candidatos = vetores[0], vetores[1:]

    pontuados = [
        (candidato, _cosseno(vetor_pergunta, vetor))
        for candidato, vetor in zip(candidatos, vetores_candidatos)
    ]
    pontuados.sort(key=lambda item: item[1], reverse=True)

    return [
        {**candidato, "score_embedding": score, "posicao_rerank": posicao}
        for posicao, (candidato, score) in enumerate(pontuados[:k_final])
    ]


if __name__ == "__main__":
    import argparse

    from fts_index import INDICE_PADRAO, buscar

    parser = argparse.ArgumentParser(description="Testa o rerank (LLM ou embeddings) sobre uma busca FTS5")
    parser.add_argument("pergunta")
    parser.add_argument("--indice", default=str(INDICE_PADRAO))
    parser.add_argument("-k", type=int, default=50, help="candidatos trazidos pelo FTS5")
    parser.add_argument("--k-final", type=int, default=10)
    parser.add_argument("--modelo", default=MODELO_PADRAO)
    parser.add_argument(
        "--metodo", choices=["llm", "embeddings"], default="llm", help="backend do rerank"
    )
    args = parser.parse_args()

    conexao = sqlite3.connect(args.indice)
    candidatos = buscar(conexao, args.pergunta, k=args.k)

    if args.metodo == "llm":
        resultado = reranquear(args.pergunta, candidatos, k_final=args.k_final, modelo=args.modelo)
    else:
        resultado = reranquear_embeddings(conexao, args.pergunta, candidatos, k_final=args.k_final)
    conexao.close()

    print(json.dumps(resultado, ensure_ascii=False, indent=2))
