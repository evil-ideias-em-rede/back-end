"""
Avalia o índice FTS5 (BM25, ver `fts_index.py`) contra o gabarito gold em
`gabaritos/` (ver `montar_gabarito.py` e `README.md`).

Métricas por pergunta (k = tamanho do corte, ver --k):
  - hit@k: 1 se PELO MENOS UM doc_id esperado está nos k resultados, 0
    caso contrário. Como o gold pode ter vários doc_ids esperados (por
    causa da sobreposição do chunking), mede se achou qualquer chunk
    relevante — o suficiente pra fundamentar uma resposta.
  - coverage@k: fração dos doc_ids esperados que apareceram nos k
    resultados. Mede se achou TODO o contexto relevante, não só uma parte.
  - reciprocal_rank: 1/posição do primeiro doc_id esperado que apareceu no
    ranking completo dos k resultados (0 se nenhum apareceu). A média
    dessa coluna é o MRR do gabarito.

Um baseline aleatório (k doc_ids sorteados do universo de `documentos`,
ignorando a busca) é calculado do lado pra servir de piso de comparação:
se o FTS não bater MUITO melhor que isso, tem algo errado no índice ou no
gabarito.

Uso:
    python eval_fts.py gold --k 10
"""

import json
import random
import sqlite3
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fts_index import INDICE_PADRAO, buscar  # noqa: E402
from reranker import (  # noqa: E402
    MODELO_EMBEDDING_PADRAO,
    MODELO_PADRAO,
    reranquear,
    reranquear_embeddings,
)
from embeddings_index import (  # noqa: E402
    buscar_hibrido,
    buscar_vetorial,
    conectar,
    embedar_perguntas_lote,
)

ESTRATEGIAS = ["bm25", "rerank-llm", "rerank-embeddings", "vetorial", "hibrido"]

GABARITOS_DIR = Path(__file__).resolve().parent / "gabaritos"
LOGS_DIR = Path(__file__).resolve().parent / "logs"

GABARITOS = {
    "gold": GABARITOS_DIR / "gabarito_audiencias_gold.jsonl",
    "manual": GABARITOS_DIR / "gabarito_audiencias_manual.jsonl",
}

K_PADRAO = 10
SEED_BASELINE = 42


def carregar_gabarito(caminho: Path) -> list[dict]:
    itens = []
    with caminho.open(encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if not linha or "EXEMPLO-remova-esta-linha" in linha:
                continue
            itens.append(json.loads(linha))
    return itens


def _metricas(doc_ids_retornados: list[str], doc_ids_esperados: list[str]) -> dict:
    esperados = set(doc_ids_esperados)
    posicoes_acerto = [
        posicao + 1
        for posicao, doc_id in enumerate(doc_ids_retornados)
        if doc_id in esperados
    ]
    hit = 1.0 if posicoes_acerto else 0.0
    coverage = (
        len(set(doc_ids_retornados) & esperados) / len(esperados) if esperados else 0.0
    )
    reciprocal_rank = 1.0 / posicoes_acerto[0] if posicoes_acerto else 0.0
    return {
        "hit": hit,
        "coverage": coverage,
        "reciprocal_rank": reciprocal_rank,
        "posicao_primeiro_acerto": posicoes_acerto[0] if posicoes_acerto else None,
    }


def avaliar_item(
    conexao: sqlite3.Connection,
    item: dict,
    k: int,
    estrategia: str,
    k_candidatos: int,
    cache_vetores: dict[str, list[float]] | None = None,
) -> dict:
    pergunta = item["pergunta"]
    vetor_pergunta = (cache_vetores or {}).get(pergunta)
    if estrategia == "rerank-llm":
        candidatos = buscar(conexao, pergunta, k=k_candidatos)
        resultados = reranquear(pergunta, candidatos, k_final=k)
    elif estrategia == "rerank-embeddings":
        candidatos = buscar(conexao, pergunta, k=k_candidatos)
        resultados = reranquear_embeddings(conexao, pergunta, candidatos, k_final=k)
    elif estrategia == "vetorial":
        resultados = buscar_vetorial(conexao, pergunta, k=k, vetor_pergunta=vetor_pergunta)
    elif estrategia == "hibrido":
        resultados = buscar_hibrido(
            conexao, pergunta, k=k, k_candidatos=k_candidatos, vetor_pergunta=vetor_pergunta
        )
    else:
        resultados = buscar(conexao, pergunta, k=k)
    doc_ids_retornados = [r["doc_id"] for r in resultados]
    metricas = _metricas(doc_ids_retornados, item["doc_ids_esperados"])
    return {
        "id": item["id"],
        "pergunta": item["pergunta"],
        "doc_ids_esperados": item["doc_ids_esperados"],
        "doc_ids_retornados": doc_ids_retornados,
        **metricas,
    }


def _todos_doc_ids(conexao: sqlite3.Connection) -> list[str]:
    cursor = conexao.execute("SELECT doc_id FROM documentos")
    return [row[0] for row in cursor.fetchall()]


def avaliar_baseline_aleatorio(
    item: dict, k: int, universo: list[str], rng: random.Random
) -> dict:
    doc_ids_sorteados = rng.sample(universo, min(k, len(universo)))
    return _metricas(doc_ids_sorteados, item["doc_ids_esperados"])


def _media(chave: str, resultados: list[dict]) -> float:
    if not resultados:
        return 0.0
    return sum(r[chave] for r in resultados) / len(resultados)


def avaliar_gabarito(
    conexao: sqlite3.Connection,
    nome: str,
    itens: list[dict],
    k: int,
    estrategia: str = "bm25",
    k_candidatos: int = 50,
) -> dict:
    universo = _todos_doc_ids(conexao)
    rng = random.Random(SEED_BASELINE)

    cache_vetores = None
    if estrategia in ("vetorial", "hibrido"):
        print(f"[{nome}] embedando {len(itens)} perguntas em lote...")
        cache_vetores = embedar_perguntas_lote([item["pergunta"] for item in itens])

    resultados_fts = [
        avaliar_item(conexao, item, k, estrategia, k_candidatos, cache_vetores) for item in itens
    ]
    resultados_baseline = [
        avaliar_baseline_aleatorio(item, k, universo, rng) for item in itens
    ]

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    sufixo = f"_{estrategia}{k_candidatos}" if estrategia != "bm25" else ""
    caminho_log = LOGS_DIR / f"eval_{nome}_k{k}{sufixo}.jsonl"
    with caminho_log.open("w", encoding="utf-8") as arquivo:
        for resultado in resultados_fts:
            arquivo.write(json.dumps(resultado, ensure_ascii=False) + "\n")

    resumo = {
        "gabarito": nome,
        "k": k,
        "total_perguntas": len(itens),
        "fts": {
            f"hit@{k}": round(_media("hit", resultados_fts), 4),
            f"coverage@{k}": round(_media("coverage", resultados_fts), 4),
            "mrr": round(_media("reciprocal_rank", resultados_fts), 4),
        },
        "baseline_aleatorio": {
            f"hit@{k}": round(_media("hit", resultados_baseline), 4),
            f"coverage@{k}": round(_media("coverage", resultados_baseline), 4),
            "mrr": round(_media("reciprocal_rank", resultados_baseline), 4),
        },
        "log": str(caminho_log),
    }
    return resumo


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Avalia o índice FTS5 contra os gabaritos")
    parser.add_argument("--indice", default=str(INDICE_PADRAO))
    parser.add_argument("--k", type=int, default=K_PADRAO)
    parser.add_argument(
        "--estrategia",
        choices=ESTRATEGIAS,
        default="bm25",
        help=(
            "bm25 (padrão) | rerank-llm/rerank-embeddings (reordena candidatos do BM25, "
            "ver reranker.py) | vetorial (busca só por embedding) | hibrido (BM25 + "
            "vetorial via RRF, ver embeddings_index.py)"
        ),
    )
    parser.add_argument(
        "--k-candidatos",
        type=int,
        default=50,
        help="candidatos antes do corte em --k (rerank-*: pool do BM25; hibrido: pool de cada lado do RRF)",
    )
    parser.add_argument("gabarito", choices=[*GABARITOS.keys(), "tudo"])
    args = parser.parse_args()

    precisa_vec = args.estrategia in ("vetorial", "hibrido")
    conexao = conectar(args.indice) if precisa_vec else sqlite3.connect(args.indice)

    nomes = list(GABARITOS.keys()) if args.gabarito == "tudo" else [args.gabarito]
    for nome in nomes:
        itens = carregar_gabarito(GABARITOS[nome])
        if not itens:
            print(f"[{nome}] gabarito vazio, pulando")
            continue
        resumo = avaliar_gabarito(conexao, nome, itens, args.k, args.estrategia, args.k_candidatos)
        if args.estrategia == "rerank-llm":
            resumo["modelo_rerank"] = MODELO_PADRAO
        elif args.estrategia in ("rerank-embeddings", "vetorial", "hibrido"):
            resumo["modelo_embedding"] = MODELO_EMBEDDING_PADRAO
        print(json.dumps(resumo, ensure_ascii=False, indent=2))

    conexao.close()
