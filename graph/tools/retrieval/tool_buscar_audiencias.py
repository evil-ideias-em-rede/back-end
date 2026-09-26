"""Tool de LangChain para buscar matérias de audiências públicas."""

import json
import sqlite3
from functools import lru_cache
from pathlib import Path

from langchain_core.tools import tool

from .audiencias import PUBLIC_HEARING_LDS
from .embeddings_index import buscar_materias_vetorial, conectar


@lru_cache(maxsize=1)
def _materias_do_dataset() -> dict[str, str]:
    """Carrega as matérias do LDS uma única vez por processo.

    A tabela ``audiencias_vec`` guarda apenas o vetor e o ``ref_id``. O
    dataset é a fonte original da matéria e funciona como fallback quando a
    tabela estruturada ``audiencias`` ainda não foi populada.
    """
    materias = {}
    caminho = Path(PUBLIC_HEARING_LDS)
    if not caminho.is_file():
        return materias

    with caminho.open(encoding="utf-8") as arquivo:
        for linha in arquivo:
            if not linha.strip():
                continue
            audiencia = json.loads(linha)
            ref_id = audiencia.get("id")
            if ref_id is not None:
                materias[str(ref_id)] = str(audiencia.get("materia") or "")
    return materias


def _buscar_materias(
    conexao: sqlite3.Connection, ref_ids: list[str]
) -> dict[str, str]:
    """Busca as matérias no índice e completa as ausentes pelo dataset LDS."""
    if not ref_ids:
        return {}

    materias = {}
    placeholders = ",".join("?" for _ in ref_ids)
    try:
        linhas = conexao.execute(
            f"SELECT ref_id, materia FROM audiencias "
            f"WHERE ref_id IN ({placeholders}) AND materia IS NOT NULL",
            ref_ids,
        ).fetchall()
        materias.update(
            {str(ref_id): str(materia or "") for ref_id, materia in linhas}
        )
    except sqlite3.Error:
        # O índice vetorial é suficiente para a busca; o dataset continua
        # permitindo retornar a matéria em índices antigos/incompletos.
        pass

    dataset = _materias_do_dataset()
    for ref_id in ref_ids:
        materias.setdefault(ref_id, dataset.get(ref_id, ""))
    return materias


@tool("buscar_audiencias")
def buscar_audiencias(pergunta: str, k: int = 30) -> str:
    """Busca matérias relevantes de audiências públicas.

    A busca usa os embeddings da matéria completa, com uma linha por
    audiência. Use ``ref_id`` para consultar depois os chunks da transcrição
    com ``consultar_audiencias_sql`` quando precisar saber o que foi dito por
    cada participante. Não invente conteúdo quando a busca não trouxer
    evidência suficiente.

    Args:
        pergunta: Pergunta ou tema em linguagem natural.
        k: Quantidade máxima de audiências retornadas; padrão 30, máximo 60.
            Cada audiência aparece no máximo uma vez.

    Returns:
        JSON serializado com ``doc_id`` (igual ao ``ref_id`` para manter a
        compatibilidade), ``source``, ``ref_id``, ``distance`` e ``materia``
        para cada audiência encontrada.

        Para ler a transcrição ou uma fala, use ``consultar_audiencias_sql``
        com o ``ref_id`` retornado nesta busca.
    """
    pergunta = pergunta.strip()
    if not pergunta:
        return json.dumps({"erro": "A pergunta não pode ser vazia."}, ensure_ascii=False)

    k = max(1, min(int(k), 60))
    # LangGraph executa tools síncronas em threads do executor. Abrir a
    # conexão nesta chamada evita reutilizar uma conexão SQLite criada em
    # outra thread e também isola chamadas concorrentes do agente.
    conexao = conectar()
    try:
        resultados = buscar_materias_vetorial(conexao, pergunta, k=k)
        materias = _buscar_materias(conexao, [r["ref_id"] for r in resultados])
        resultados = [
            {
                "doc_id": resultado["ref_id"],
                "source": "audiencia",
                "ref_id": resultado["ref_id"],
                "distance": resultado["distance"],
                "materia": materias.get(resultado["ref_id"], ""),
            }
            for resultado in resultados
        ]
        return json.dumps(resultados, ensure_ascii=False)
    finally:
        conexao.close()
