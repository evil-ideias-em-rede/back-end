"""
Popula e consulta um índice de busca textual (SQLite FTS5) sobre a
transcrição das audiências públicas (`transcricao` de
PublicHearingBR_LDS.jsonl), quebrada em chunks por parágrafo antes de
indexar (ver `chunk_por_paragrafos`).

O índice fica na tabela `documentos` (metadados + texto) e na virtual table
`documentos_fts` (índice invertido), num arquivo SQLite PRÓPRIO e gitignorado
(INDICE_PADRAO) — regenerável a qualquer momento rodando este script, então
não faz sentido versionar esse resultado. O texto duplicado + o índice
invertido do FTS5 multiplicam bastante o tamanho em disco (na prática, ~5x
maior que o dataset original).

`source`/`ref_id` ficam genéricos no schema (não específicos de audiência)
para caber outras fontes de texto do mesmo tipo (chunk longo) que cheguem
depois, sem precisar remodelar a tabela.
"""

import json
import sqlite3
from pathlib import Path

import tiktoken

INDICE_PADRAO = (
    Path(__file__).resolve().parent / "indice" / "indice_busca.sqlite"
)
PUBLIC_HEARING_LDS = (
    Path(__file__).resolve().parent
    / "public_hearing"
    / "PublicHearingBR_LDS.jsonl"
)

ORCAMENTO_TOKENS = 800
SOBREPOSICAO_PARAGRAFOS = 2

_ENCODING = tiktoken.get_encoding("cl100k_base")


def contar_tokens(texto: str) -> int:
    return len(_ENCODING.encode(texto))


def chunk_por_paragrafos(
    texto: str,
    orcamento_tokens: int = ORCAMENTO_TOKENS,
    sobreposicao_paragrafos: int = SOBREPOSICAO_PARAGRAFOS,
) -> list[dict]:
    """
    Agrupa parágrafos consecutivos (separados por \\n\\n) até acumular
    `orcamento_tokens`. Nunca corta um parágrafo no meio — se um parágrafo
    isolado já ultrapassa o orçamento, ele vira um chunk sozinho.

    A sobreposição entre chunks é medida em parágrafos inteiros (não em
    tokens crus), para o início de um chunk nunca começar no meio de uma
    frase/fala.

    Retorna uma lista de dicts:
      {"texto": str, "paragrafo_inicio": int, "paragrafo_fim": int}
    (índices 0-based e inclusivos, referentes à lista de parágrafos do texto
    original — usados depois para rastrear de onde veio cada chunk).
    """
    paragrafos = [p.strip() for p in texto.split("\n\n") if p.strip()]
    if not paragrafos:
        return []

    chunks: list[dict] = []
    inicio_idx = 0
    atual: list[str] = []
    tokens_atual = 0

    def fechar_chunk(fim_idx: int) -> None:
        if not atual:
            return
        chunks.append(
            {
                "texto": "\n\n".join(atual),
                "paragrafo_inicio": inicio_idx,
                "paragrafo_fim": fim_idx,
            }
        )

    for i, paragrafo in enumerate(paragrafos):
        tokens_paragrafo = contar_tokens(paragrafo)

        if atual and tokens_atual + tokens_paragrafo > orcamento_tokens:
            fechar_chunk(i - 1)
            sobreposicao = (
                atual[-sobreposicao_paragrafos:] if sobreposicao_paragrafos else []
            )
            inicio_idx = max(i - len(sobreposicao), 0)
            atual = list(sobreposicao)
            tokens_atual = sum(contar_tokens(p) for p in atual)

        atual.append(paragrafo)
        tokens_atual += tokens_paragrafo

    fechar_chunk(len(paragrafos) - 1)
    return chunks


def garantir_schema(conexao: sqlite3.Connection) -> None:
    conexao.executescript(
        """
        CREATE TABLE IF NOT EXISTS documentos (
            doc_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            ref_id TEXT NOT NULL,
            texto TEXT NOT NULL,
            paragrafo_inicio INTEGER,
            paragrafo_fim INTEGER
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS documentos_fts USING fts5(
            doc_id UNINDEXED,
            texto,
            tokenize = 'unicode61 remove_diacritics 2'
        );
        """
    )


def _remover_fonte(conexao: sqlite3.Connection, source: str) -> None:
    """Apaga todos os documentos de uma fonte, para repopular sem duplicar."""
    conexao.execute(
        "DELETE FROM documentos_fts WHERE doc_id IN "
        "(SELECT doc_id FROM documentos WHERE source = ?)",
        (source,),
    )
    conexao.execute("DELETE FROM documentos WHERE source = ?", (source,))


def _inserir_documento(
    conexao: sqlite3.Connection,
    doc_id: str,
    source: str,
    ref_id: str,
    texto: str,
    paragrafo_inicio: int | None = None,
    paragrafo_fim: int | None = None,
) -> None:
    conexao.execute(
        """
        INSERT INTO documentos
            (doc_id, source, ref_id, texto, paragrafo_inicio, paragrafo_fim)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (doc_id, source, ref_id, texto, paragrafo_inicio, paragrafo_fim),
    )
    conexao.execute(
        "INSERT INTO documentos_fts (doc_id, texto) VALUES (?, ?)", (doc_id, texto)
    )


def popular_public_hearing(
    conexao: sqlite3.Connection, caminho_jsonl: Path = PUBLIC_HEARING_LDS
) -> int:
    """
    Popula `documentos` a partir do PublicHearingBR_LDS.jsonl, quebrando a
    `transcricao` de cada audiência em chunks por parágrafo (ver
    chunk_por_paragrafos). Cada chunk vira um documento próprio, rastreável
    até a audiência e o intervalo de parágrafos de origem.
    """
    if not caminho_jsonl.is_file():
        raise FileNotFoundError(f"Dataset não encontrado: {caminho_jsonl}")

    garantir_schema(conexao)
    _remover_fonte(conexao, "audiencia")

    total = 0
    with caminho_jsonl.open(encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if not linha:
                continue
            amostra = json.loads(linha)
            id_ = amostra["id"]
            transcricao = (amostra.get("transcricao") or "").strip()
            if not transcricao:
                continue

            for indice, chunk in enumerate(chunk_por_paragrafos(transcricao)):
                _inserir_documento(
                    conexao,
                    doc_id=f"audiencia:{id_}:chunk:{indice}",
                    source="audiencia",
                    ref_id=str(id_),
                    texto=chunk["texto"],
                    paragrafo_inicio=chunk["paragrafo_inicio"],
                    paragrafo_fim=chunk["paragrafo_fim"],
                )
                total += 1

    conexao.commit()
    return total


def _query_fts_segura(consulta: str) -> str:
    """
    Escapa a consulta tratando cada palavra como termo literal entre aspas
    (evita erro de sintaxe do FTS5 em textos com hífen, dois-pontos,
    parênteses etc., que o FTS5 interpretaria como operadores) e junta os
    termos com OR.

    OR em vez do AND implícito do FTS5 (espaço = AND) é essencial pra
    perguntas em linguagem natural: uma frase de 15-20 palavras quase nunca
    vai ter TODAS elas — incluindo preposições e artigos — no mesmo
    documento, então AND praticamente sempre retorna vazio. Com OR, o BM25
    nativo do FTS5 já pondera por raridade de cada termo (IDF), então
    documentos que batem nos termos de conteúdo mais específicos da
    pergunta sobem no ranking sem exigir que as palavras banais também
    apareçam.
    """
    termos = consulta.split()
    return " OR ".join(f'"{termo}"' for termo in termos)


def buscar(
    conexao: sqlite3.Connection,
    consulta: str,
    k: int = 5,
    source: str | None = None,
) -> list[dict]:
    """
    Busca textual (BM25 nativo do FTS5) em `documentos_fts`. Retorna os k
    documentos mais relevantes, com um trecho destacado e os campos
    necessários para rastrear de onde cada resultado veio.
    """
    condicoes = ["documentos_fts MATCH ?"]
    parametros: list = [_query_fts_segura(consulta)]
    if source:
        condicoes.append("d.source = ?")
        parametros.append(source)
    parametros.append(k)

    sql = f"""
        SELECT d.doc_id, d.source, d.ref_id,
               snippet(documentos_fts, 1, '[', ']', '...', 12) AS trecho,
               bm25(documentos_fts) AS score
        FROM documentos_fts
        JOIN documentos d ON d.doc_id = documentos_fts.doc_id
        WHERE {' AND '.join(condicoes)}
        ORDER BY score
        LIMIT ?
    """
    colunas = ["doc_id", "source", "ref_id", "trecho", "score"]
    linhas = conexao.execute(sql, parametros).fetchall()
    return [dict(zip(colunas, linha)) for linha in linhas]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Popula e consulta o índice FTS5 de documentos")
    parser.add_argument(
        "--indice", default=str(INDICE_PADRAO), help="Arquivo SQLite do índice (gitignorado)"
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("popular-public-hearing")

    p_buscar = sub.add_parser("buscar")
    p_buscar.add_argument("consulta")
    p_buscar.add_argument("-k", type=int, default=5)
    p_buscar.add_argument("--source", default=None)

    args = parser.parse_args()
    Path(args.indice).parent.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(args.indice)

    if args.comando == "popular-public-hearing":
        print(f"Documentos inseridos (audiências): {popular_public_hearing(conexao)}")
    elif args.comando == "buscar":
        resultados = buscar(conexao, args.consulta, k=args.k, source=args.source)
        print(json.dumps(resultados, ensure_ascii=False, indent=2))

    conexao.close()
