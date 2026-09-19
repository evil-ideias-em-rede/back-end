"""Leitura estruturada de audiências a partir do índice SQLite.

O índice guarda a transcrição em ``documentos`` e os metadados estruturados
em ``audiencias``. A saída mantém as mesmas chaves consumidas pelo frontend
antigo, mas os dados vêm do dataset real de audiências públicas.
"""

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool


BASE_DIR = Path(__file__).resolve().parent
INDICE_PADRAO = BASE_DIR / "indice" / "indice_busca.sqlite"
PUBLIC_HEARING_LDS = BASE_DIR / "public_hearing" / "PublicHearingBR_LDS.jsonl"


def _linhas_materia(materia: str) -> list[str]:
    return [linha.strip() for linha in (materia or "").splitlines() if linha.strip()]


def _linhas_descritivas(materia: str) -> list[str]:
    return [
        linha
        for linha in _linhas_materia(materia)
        if not re.fullmatch(r"\d{2}/\d{2}/\d{4}.*", linha)
        and not linha.startswith("Atualizado em ")
        and linha != "•"
    ]


def _data_materia(materia: str) -> str | None:
    encontrado = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", materia or "")
    if not encontrado:
        return None
    return datetime.strptime(encontrado.group(1), "%d/%m/%Y").date().isoformat()


def _partido(cargo: str) -> str | None:
    """Extrai o partido quando o cargo contém o padrão Partido-UF."""
    encontrado = re.search(r"\(([^()]+)-[A-Za-z]{2}\)", cargo or "")
    if not encontrado:
        return None
    return encontrado.group(1).strip().upper()


def montar_audiencia(registro: dict) -> dict:
    audiencia_id = int(registro["id"])
    materia = str(registro.get("materia") or "")
    linhas = _linhas_descritivas(materia)
    metadados = registro.get("metadados") or {}
    envolvidos = metadados.get("envolvidos") or []

    participantes = []
    discursos = []
    for participante_numero, envolvido in enumerate(envolvidos, start=1):
        participante_id = f"{audiencia_id}-part-{participante_numero:02d}"
        nome = str(envolvido.get("nome") or "")
        cargo = str(envolvido.get("cargo") or "")
        partido = _partido(cargo)
        participantes.append(
            {
                "id": participante_id,
                "nome": nome,
                "partido": partido,
                "papel": cargo or None,
            }
        )
        for opiniao_numero, opiniao in enumerate(envolvido.get("opinioes") or [], start=1):
            discursos.append(
                {
                    "id": f"{audiencia_id}-disc-{len(discursos) + 1:02d}",
                    "participanteId": participante_id,
                    "orador": nome,
                    "partido": partido,
                    "ordem": len(discursos) + 1,
                    "posicionamento": None,
                    "texto": str(opiniao),
                }
            )

    titulo = linhas[0] if linhas else str(metadados.get("assunto") or f"Audiência {audiencia_id}")
    resumo = " ".join(linhas[1:3]) or str(metadados.get("assunto") or "")
    return {
        "id": audiencia_id,
        "titulo": titulo,
        "tipo": "audiencia_publica",
        "casa": "Câmara dos Deputados",
        "comissao": None,
        "data": _data_materia(materia),
        "resumo": resumo,
        "integraUrl": None,
        "participantes": participantes,
        "discursos": discursos,
        "posicionamentos": {
            "contra": [],
            "neutros": [],
            "favor": [],
            "ambiguos": [],
        },
        "propostas": [],
        "lastModifiedAt": None,
    }


def _garantir_coluna_estrutura(conexao: sqlite3.Connection) -> None:
    colunas = {row[1] for row in conexao.execute("PRAGMA table_info(audiencias)")}
    if "estrutura_json" not in colunas:
        conexao.execute("ALTER TABLE audiencias ADD COLUMN estrutura_json TEXT")


def popular_audiencias(
    caminho_indice: Path = INDICE_PADRAO,
    caminho_dataset: Path = PUBLIC_HEARING_LDS,
) -> int:
    """Importa os registros reais para a tabela estruturada do índice."""
    conexao = sqlite3.connect(caminho_indice)
    try:
        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS audiencias (
                ref_id TEXT PRIMARY KEY,
                assunto TEXT,
                materia TEXT,
                envolvidos TEXT,
                keywords TEXT
            )
            """
        )
        _garantir_coluna_estrutura(conexao)
        total = 0
        with caminho_dataset.open(encoding="utf-8") as arquivo:
            for linha in arquivo:
                if not linha.strip():
                    continue
                registro = json.loads(linha)
                estrutura = montar_audiencia(registro)
                metadados = registro.get("metadados") or {}
                conexao.execute(
                    """
                    INSERT INTO audiencias
                        (ref_id, assunto, materia, envolvidos, keywords, estrutura_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ref_id) DO UPDATE SET
                        assunto=excluded.assunto,
                        materia=excluded.materia,
                        envolvidos=excluded.envolvidos,
                        estrutura_json=excluded.estrutura_json
                    """,
                    (
                        str(registro["id"]),
                        metadados.get("assunto"),
                        registro.get("materia"),
                        json.dumps(metadados.get("envolvidos") or [], ensure_ascii=False),
                        json.dumps([], ensure_ascii=False),
                        json.dumps(estrutura, ensure_ascii=False),
                    ),
                )
                total += 1
        conexao.commit()
        return total
    finally:
        conexao.close()


def listar_audiencias(caminho_indice: Path = INDICE_PADRAO) -> list[dict]:
    conexao = sqlite3.connect(caminho_indice)
    try:
        _garantir_coluna_estrutura(conexao)
        rows = conexao.execute(
            "SELECT estrutura_json FROM audiencias WHERE estrutura_json IS NOT NULL ORDER BY CAST(ref_id AS INTEGER)"
        ).fetchall()
        return [json.loads(row[0]) for row in rows]
    finally:
        conexao.close()


def consultar_audiencia(audiencia_id: int | str, caminho_indice: Path = INDICE_PADRAO) -> dict | None:
    try:
        ref_id = str(int(str(audiencia_id).removeprefix("aud-")))
    except (TypeError, ValueError):
        return None

    conexao = sqlite3.connect(caminho_indice)
    try:
        _garantir_coluna_estrutura(conexao)
        row = conexao.execute(
            "SELECT estrutura_json FROM audiencias WHERE ref_id = ?",
            (ref_id,),
        ).fetchone()
        return json.loads(row[0]) if row and row[0] else None
    finally:
        conexao.close()


@tool("consultar_audiencia_por_id")
def consultar_audiencia_por_id(audiencia_id: int) -> str:
    """Retorna uma audiência real pelo ID numérico no formato do frontend."""
    resultado = consultar_audiencia(audiencia_id)
    if resultado is None:
        return json.dumps(
            {"erro": f"Audiência {audiencia_id} não encontrada no índice."},
            ensure_ascii=False,
        )
    return json.dumps(resultado, ensure_ascii=False)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Estrutura audiências reais no índice SQLite")
    parser.add_argument("comando", choices=["popular", "listar", "consultar"])
    parser.add_argument("audiencia_id", nargs="?")
    args = parser.parse_args()
    if args.comando == "popular":
        print(popular_audiencias())
    elif args.comando == "listar":
        print(json.dumps(listar_audiencias(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(consultar_audiencia(args.audiencia_id), ensure_ascii=False, indent=2))
