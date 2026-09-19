"""
Índice vetorial sobre os mesmos chunks de `fts_index.py` (tabela
`documentos`), usando a extensão `sqlite-vec` dentro do MESMO arquivo
`indice_busca.sqlite` — não duplica texto, só guarda doc_id + embedding
(`documentos_vec`, virtual table `vec0`).

`buscar_vetorial()` É A BUSCA PADRÃO DO RECUPERADOR (decidido em
2026-09-17, ver `eval/README.md` e a comparação de estratégias nos logs de
`eval/`): venceu de longe o BM25 puro (`fts_index.buscar`) no gabarito que
imita pergunta de usuário real sobre o tema de uma audiência (manual,
hit@10 0.955 vs 0.727, n=22) — só perde pro BM25 no gabarito gold, cujas
perguntas são paráfrase de UMA fala específica com vocabulário quase
literal do texto, cenário que não é representativo do uso real do produto.

`buscar_hibrido` (BM25 + vetorial via Reciprocal Rank Fusion) e o rerank em
`reranker.py` (LLM ou embeddings sobre os candidatos do BM25) continuam no
código como experimentos comparativos — nenhum dos dois bateu o vetorial
puro no gabarito que representa o uso real, então não são o caminho
padrão; ver o raciocínio completo no histórico de avaliação.

Uso:
    python embeddings_index.py popular
    python embeddings_index.py buscar "<pergunta>" -k 10
    python embeddings_index.py buscar "<pergunta>" -k 10 --hibrido
"""

import json
import os
import sqlite3
from pathlib import Path

import sqlite_vec
from dotenv import load_dotenv
from openai import OpenAI

from fts_index import INDICE_PADRAO, buscar

load_dotenv(override=True)

MODELO_EMBEDDING_PADRAO = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
DIMENSAO_EMBEDDING = 1536
TAMANHO_LOTE = 100

K_RRF = 60  # constante usual do Reciprocal Rank Fusion (Cormack et al. 2009)
TRECHO_FALLBACK_CHARS = 300
K_INTERNO_COM_FILTRO = 3000  # ver nota em buscar_vetorial sobre filtro pós-KNN


def conectar(caminho: Path = INDICE_PADRAO) -> sqlite3.Connection:
    """Abre o índice com a extensão sqlite-vec carregada (necessária pra
    ler/escrever em `documentos_vec`; não afeta as tabelas normais/FTS5)."""
    conexao = sqlite3.connect(caminho)
    conexao.enable_load_extension(True)
    sqlite_vec.load(conexao)
    conexao.enable_load_extension(False)
    return conexao


def garantir_schema_vec(conexao: sqlite3.Connection, dimensao: int = DIMENSAO_EMBEDDING) -> None:
    conexao.execute(
        f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS documentos_vec USING vec0(
            doc_id TEXT PRIMARY KEY,
            embedding FLOAT[{dimensao}] distance_metric=cosine
        )
        """
    )


def _remover_fonte_vec(conexao: sqlite3.Connection, source: str) -> None:
    conexao.execute(
        "DELETE FROM documentos_vec WHERE doc_id IN "
        "(SELECT doc_id FROM documentos WHERE source = ?)",
        (source,),
    )


def _lotes(sequencia: list, tamanho: int):
    for i in range(0, len(sequencia), tamanho):
        yield sequencia[i : i + tamanho]


def popular_embeddings(
    conexao: sqlite3.Connection,
    source: str = "audiencia",
    modelo: str = MODELO_EMBEDDING_PADRAO,
) -> int:
    """
    Embeda o TEXTO COMPLETO de cada chunk de `documentos` (não um snippet)
    e grava em `documentos_vec`. Repopula do zero pra essa `source`, igual
    ao padrão já usado em `fts_index.popular_public_hearing()`.
    """
    garantir_schema_vec(conexao)
    _remover_fonte_vec(conexao, source)

    linhas = conexao.execute(
        "SELECT doc_id, texto FROM documentos WHERE source = ?", (source,)
    ).fetchall()

    cliente = OpenAI()
    total = 0
    for lote in _lotes(linhas, TAMANHO_LOTE):
        doc_ids = [doc_id for doc_id, _ in lote]
        textos = [texto for _, texto in lote]
        resposta = cliente.embeddings.create(model=modelo, input=textos)
        conexao.executemany(
            "INSERT INTO documentos_vec (doc_id, embedding) VALUES (?, ?)",
            [
                (doc_id, sqlite_vec.serialize_float32(item.embedding))
                for doc_id, item in zip(doc_ids, resposta.data)
            ],
        )
        total += len(lote)
        conexao.commit()
        print(f"  {total}/{len(linhas)} chunks embedados")
    return total


def _embed_pergunta(pergunta: str, modelo: str = MODELO_EMBEDDING_PADRAO) -> list[float]:
    cliente = OpenAI()
    resposta = cliente.embeddings.create(model=modelo, input=[pergunta])
    return resposta.data[0].embedding


def embedar_perguntas_lote(
    perguntas: list[str], modelo: str = MODELO_EMBEDDING_PADRAO
) -> dict[str, list[float]]:
    """
    Embeda várias perguntas em poucas chamadas de API (lotes de
    TAMANHO_LOTE) em vez de uma chamada por pergunta — essencial pra
    avaliar um gabarito grande (a latência de rede por chamada, ~1.5-2s,
    domina o tempo total se for sequencial). Retorna {pergunta: vetor};
    perguntas repetidas só são embedadas uma vez.
    """
    unicas = list(dict.fromkeys(perguntas))
    cliente = OpenAI()
    vetores: dict[str, list[float]] = {}
    for lote in _lotes(unicas, TAMANHO_LOTE):
        resposta = cliente.embeddings.create(model=modelo, input=lote)
        for pergunta, item in zip(lote, resposta.data):
            vetores[pergunta] = item.embedding
    return vetores


def _trecho_fallback(conexao: sqlite3.Connection, doc_id: str) -> str:
    texto = conexao.execute(
        "SELECT texto FROM documentos WHERE doc_id = ?", (doc_id,)
    ).fetchone()[0]
    return texto[:TRECHO_FALLBACK_CHARS] + ("..." if len(texto) > TRECHO_FALLBACK_CHARS else "")


def buscar_vetorial(
    conexao: sqlite3.Connection,
    pergunta: str,
    k: int = 10,
    source: str | None = None,
    tag: str | None = None,
    vetor_pergunta: list[float] | None = None,
) -> list[dict]:
    """`vetor_pergunta`: passe um embedding já calculado (ver
    `embedar_perguntas_lote`) pra pular a chamada de API aqui — usado pela
    avaliação em lote, que embeda todas as perguntas do gabarito de uma vez.
    `tag`: filtra por `documentos.tag` (ver `metadados_audiencias.py`) —
    precisa do índice já populado com `metadados_audiencias.py popular`.

    IMPORTANTE: `source`/`tag` filtram DEPOIS do KNN do sqlite-vec (join
    com `documentos`) — pedir só `k=10` com filtro poderia devolver menos
    de 10 linhas (os 10 vizinhos mais próximos no espaço INTEIRO podem não
    bater o filtro). Por isso, com filtro ativo, pedimos um pool bem maior
    ao vec0 (`K_INTERNO_COM_FILTRO`) e só truncamos pro `k` pedido depois
    de filtrar — garante `k` resultados de verdade dentro do subconjunto
    filtrado, não só dentro do índice inteiro."""
    vetor = sqlite_vec.serialize_float32(vetor_pergunta or _embed_pergunta(pergunta))
    condicoes = []
    if source:
        condicoes.append("d.source = :source")
    if tag:
        condicoes.append("d.tag = :tag")
    k_vec = K_INTERNO_COM_FILTRO if condicoes else k
    condicao_extra = ("AND " + " AND ".join(condicoes)) if condicoes else ""
    sql = f"""
        SELECT d.doc_id, d.source, d.ref_id, v.distance
        FROM documentos_vec v
        JOIN documentos d ON d.doc_id = v.doc_id
        WHERE v.embedding MATCH :vetor AND k = :k_vec {condicao_extra}
        ORDER BY v.distance
    """
    linhas = conexao.execute(
        sql, {"vetor": vetor, "k_vec": k_vec, "source": source, "tag": tag}
    ).fetchall()
    colunas = ["doc_id", "source", "ref_id", "distance"]
    resultados = [dict(zip(colunas, linha)) for linha in linhas][:k]
    for r in resultados:
        r["trecho"] = _trecho_fallback(conexao, r["doc_id"])
    return resultados


def buscar_hibrido(
    conexao: sqlite3.Connection,
    pergunta: str,
    k: int = 10,
    k_candidatos: int = 30,
    source: str | None = None,
    vetor_pergunta: list[float] | None = None,
) -> list[dict]:
    """
    FTS5 e busca vetorial rodam cada um de forma independente (top
    `k_candidatos`); os rankings são combinados por Reciprocal Rank Fusion
    — cada doc_id soma 1/(K_RRF + posição) em cada lista onde aparece.
    RRF usa só a POSIÇÃO em cada ranking, não o score bruto — por isso não
    precisa normalizar BM25 (log-based) contra distância de cosseno
    (escalas incompatíveis). `vetor_pergunta`: ver `buscar_vetorial`.
    """
    resultados_fts = buscar(conexao, pergunta, k=k_candidatos, source=source)
    resultados_vec = buscar_vetorial(
        conexao, pergunta, k=k_candidatos, source=source, vetor_pergunta=vetor_pergunta
    )

    pontuacao: dict[str, float] = {}
    info: dict[str, dict] = {}
    for lista in (resultados_fts, resultados_vec):
        for posicao, r in enumerate(lista):
            pontuacao[r["doc_id"]] = pontuacao.get(r["doc_id"], 0.0) + 1 / (K_RRF + posicao + 1)
            info.setdefault(r["doc_id"], r)

    ordenados = sorted(pontuacao.items(), key=lambda item: item[1], reverse=True)
    return [{**info[doc_id], "score_rrf": round(score, 6)} for doc_id, score in ordenados[:k]]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Índice vetorial (sqlite-vec) e busca híbrida")
    parser.add_argument("--indice", default=str(INDICE_PADRAO))
    sub = parser.add_subparsers(dest="comando", required=True)

    p_popular = sub.add_parser("popular")
    p_popular.add_argument("--source", default="audiencia")
    p_popular.add_argument("--modelo", default=MODELO_EMBEDDING_PADRAO)

    p_buscar = sub.add_parser("buscar")
    p_buscar.add_argument("pergunta")
    p_buscar.add_argument("-k", type=int, default=10)
    p_buscar.add_argument("--k-candidatos", type=int, default=30)
    p_buscar.add_argument("--source", default=None)
    p_buscar.add_argument("--hibrido", action="store_true", help="combina FTS5 + vetorial via RRF")

    args = parser.parse_args()
    conexao = conectar(args.indice)

    if args.comando == "popular":
        total = popular_embeddings(conexao, source=args.source, modelo=args.modelo)
        print(f"Embeddings gravados: {total}")
    elif args.comando == "buscar":
        if args.hibrido:
            resultados = buscar_hibrido(
                conexao, args.pergunta, k=args.k, k_candidatos=args.k_candidatos, source=args.source
            )
        else:
            resultados = buscar_vetorial(conexao, args.pergunta, k=args.k, source=args.source)
        print(json.dumps(resultados, ensure_ascii=False, indent=2))

    conexao.close()
