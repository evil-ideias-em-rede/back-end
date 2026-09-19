"""
Monta o gabarito de avaliação do recuperador FTS5 (ver `fts_index.py`).

GOLD (audiências): usa `PublicHearingBR_NLI.jsonl`. Cada opinião (`opiniao`)
de um envolvido vira a pergunta; a resposta esperada é o conjunto de chunks
indexados (`audiencia:{id}:chunk:{n}`) que cobrem o trecho de onde a opinião
foi extraída (`chunks_proximos`). Só entram opiniões com
`verificacao_manual: false` (não sinalizadas como alucinação na checagem
manual do dataset) E que tenham pelo menos um chunk_proximo localizável na
transcrição original — texto sintetizado pelo LLM que resume múltiplas falas
intercaladas (ex.: interrupções de outro orador) não é localizável por
substring e é descartado.

MANUAL (audiências): perguntas parafraseadas à mão em
`gabaritos/perguntas_audiencias_manual.jsonl` (`{"audiencia_id": int,
"pergunta": str}`), escolhidas a partir de `gerar_candidatos_audiencias.py`.
Ao contrário do gold, a pergunta cobre o tema geral da audiência (não um
trecho específico), então a resposta esperada é TODO chunk indexado daquela
audiência — mede se o FTS acha a audiência certa a partir de uma pergunta
realista, não parafraseada de um trecho literal do texto.

Uso:
    python montar_gabarito.py gold-audiencias
    python montar_gabarito.py manual-audiencias
"""

import bisect
import json
import re
import sqlite3
from pathlib import Path

RAIZ_RETRIEVAL = Path(__file__).resolve().parent.parent
INDICE_PADRAO = RAIZ_RETRIEVAL / "indice" / "indice_busca.sqlite"
NLI_PADRAO = RAIZ_RETRIEVAL / "public_hearing" / "PublicHearingBR_NLI.jsonl"
LDS_PADRAO = RAIZ_RETRIEVAL / "public_hearing" / "PublicHearingBR_LDS.jsonl"

SAIDA_DIR = Path(__file__).resolve().parent / "gabaritos"
SAIDA_GOLD = SAIDA_DIR / "gabarito_audiencias_gold.jsonl"
SAIDA_MANUAL = SAIDA_DIR / "gabarito_audiencias_manual.jsonl"
PERGUNTAS_MANUAL_PADRAO = SAIDA_DIR / "perguntas_audiencias_manual.jsonl"


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


class _IndiceTranscricao:
    """
    Pré-processa a transcrição de UMA audiência para permitir localizar, por
    substring normalizado (espaços em branco colapsados), em que intervalo
    de parágrafos (0-based, mesmo split usado por `chunk_por_paragrafos`)
    cai um trecho de texto (`chunks_proximos`).
    """

    def __init__(self, transcricao: str):
        paragrafos = [p.strip() for p in transcricao.split("\n\n") if p.strip()]
        self._paragrafos_norm = [_normalizar(p) for p in paragrafos]
        self._offsets: list[int] = []
        pos = 0
        for p in self._paragrafos_norm:
            self._offsets.append(pos)
            pos += len(p) + 1  # +1 pelo espaço usado como separador abaixo
        self._texto_norm = " ".join(self._paragrafos_norm)

    def localizar(self, trecho: str) -> tuple[int, int] | None:
        """Retorna (paragrafo_inicio, paragrafo_fim) ou None se não achar."""
        alvo = _normalizar(trecho)
        if not alvo:
            return None
        idx = self._texto_norm.find(alvo)
        if idx == -1:
            return None
        fim = idx + len(alvo) - 1
        i_inicio = max(bisect.bisect_right(self._offsets, idx) - 1, 0)
        i_fim = max(bisect.bisect_right(self._offsets, fim) - 1, 0)
        return i_inicio, i_fim


def montar_gabarito_audiencias_gold(
    conexao_indice: sqlite3.Connection,
    caminho_nli: Path = NLI_PADRAO,
    caminho_lds: Path = LDS_PADRAO,
) -> tuple[list[dict], dict]:
    """
    Requer o índice já populado (`fts_index.py popular-public-hearing`), pois
    usa os intervalos de parágrafo gravados em `documentos` pra saber quais
    doc_ids cobrem o trecho de onde cada opinião foi extraída.
    """
    transcricoes: dict[int, str] = {}
    with caminho_lds.open(encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if not linha:
                continue
            registro = json.loads(linha)
            transcricoes[registro["id"]] = registro.get("transcricao") or ""

    itens: list[dict] = []
    stats = {
        "total_opinioes": 0,
        "descartadas_alucinacao": 0,
        "descartadas_sem_chunks_proximos": 0,
        "descartadas_nenhum_chunk_localizado": 0,
        "itens_gerados": 0,
        "chunks_proximos_localizados": 0,
        "chunks_proximos_nao_localizados": 0,
    }

    with caminho_nli.open(encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if not linha:
                continue
            registro = json.loads(linha)
            audiencia_id = registro["id"]
            transcricao = transcricoes.get(audiencia_id, "")
            if not transcricao:
                continue
            indice_transcricao = _IndiceTranscricao(transcricao)

            for envolvido in registro["metadados_extraidos"]["envolvidos"]:
                for i_opiniao, opiniao in enumerate(envolvido.get("opinioes") or []):
                    stats["total_opinioes"] += 1

                    verificacao = opiniao.get("verificacao_alucinacao") or {}
                    if verificacao.get("verificacao_manual"):
                        stats["descartadas_alucinacao"] += 1
                        continue

                    chunks_proximos = opiniao.get("chunks_proximos") or []
                    if not chunks_proximos:
                        stats["descartadas_sem_chunks_proximos"] += 1
                        continue

                    doc_ids_esperados: set[str] = set()
                    for chunk_proximo in chunks_proximos:
                        intervalo = indice_transcricao.localizar(chunk_proximo)
                        if intervalo is None:
                            stats["chunks_proximos_nao_localizados"] += 1
                            continue
                        stats["chunks_proximos_localizados"] += 1
                        i_inicio, i_fim = intervalo
                        cursor = conexao_indice.execute(
                            """
                            SELECT doc_id FROM documentos
                            WHERE source = 'audiencia' AND ref_id = ?
                              AND paragrafo_fim >= ? AND paragrafo_inicio <= ?
                            """,
                            (str(audiencia_id), i_inicio, i_fim),
                        )
                        doc_ids_esperados.update(row[0] for row in cursor.fetchall())

                    if not doc_ids_esperados:
                        stats["descartadas_nenhum_chunk_localizado"] += 1
                        continue

                    itens.append(
                        {
                            "id": f"audiencia-gold-{audiencia_id}-{envolvido['nome']}-{i_opiniao}",
                            "pergunta": opiniao["opiniao"],
                            "doc_ids_esperados": sorted(doc_ids_esperados),
                            "source_esperada": "audiencia",
                            "origem_gabarito": "gold_nli",
                            "metadata": {
                                "audiencia_id": audiencia_id,
                                "envolvido": envolvido["nome"],
                                "cargo": envolvido.get("cargo"),
                            },
                        }
                    )
                    stats["itens_gerados"] += 1

    return itens, stats


def montar_gabarito_audiencias_manual(
    conexao_indice: sqlite3.Connection,
    caminho_perguntas: Path = PERGUNTAS_MANUAL_PADRAO,
    caminho_lds: Path = LDS_PADRAO,
) -> tuple[list[dict], dict]:
    """
    Requer o índice já populado. Pra cada `{audiencia_id, pergunta}` em
    `caminho_perguntas`, a resposta esperada é TODO doc_id indexado daquela
    audiência (a pergunta cobre o tema geral, não um trecho específico).
    """
    assuntos: dict[int, str | None] = {}
    with caminho_lds.open(encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if not linha:
                continue
            registro = json.loads(linha)
            metadados = registro.get("metadados") or {}
            assuntos[registro["id"]] = metadados.get("assunto")

    itens: list[dict] = []
    stats = {"total_perguntas": 0, "descartadas_audiencia_sem_chunks": 0, "itens_gerados": 0}

    with caminho_perguntas.open(encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if not linha:
                continue
            registro = json.loads(linha)
            stats["total_perguntas"] += 1
            audiencia_id = registro["audiencia_id"]

            cursor = conexao_indice.execute(
                "SELECT doc_id FROM documentos WHERE source = 'audiencia' AND ref_id = ?",
                (str(audiencia_id),),
            )
            doc_ids_esperados = sorted(row[0] for row in cursor.fetchall())
            if not doc_ids_esperados:
                stats["descartadas_audiencia_sem_chunks"] += 1
                continue

            itens.append(
                {
                    "id": f"audiencia-manual-{audiencia_id}",
                    "pergunta": registro["pergunta"],
                    "doc_ids_esperados": doc_ids_esperados,
                    "source_esperada": "audiencia",
                    "origem_gabarito": "manual",
                    "metadata": {
                        "audiencia_id": audiencia_id,
                        "assunto": assuntos.get(audiencia_id),
                    },
                }
            )
            stats["itens_gerados"] += 1

    return itens, stats


def _escrever_jsonl(itens: list[dict], caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as arquivo:
        for item in itens:
            arquivo.write(json.dumps(item, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Monta o gabarito de avaliação do FTS5")
    parser.add_argument("--indice", default=str(INDICE_PADRAO))
    parser.add_argument("comando", choices=["gold-audiencias", "manual-audiencias"])
    args = parser.parse_args()

    conexao = sqlite3.connect(args.indice)
    if args.comando == "gold-audiencias":
        itens, stats = montar_gabarito_audiencias_gold(conexao)
        saida = SAIDA_GOLD
    else:
        itens, stats = montar_gabarito_audiencias_manual(conexao)
        saida = SAIDA_MANUAL
    conexao.close()
    _escrever_jsonl(itens, saida)
    print(f"[{args.comando}] {json.dumps(stats, ensure_ascii=False)}")
    print(f"[{args.comando}] gravado em {saida}")
