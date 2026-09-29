"""Consulta limitada às referências públicas, sempre na versão da aplicação."""

import csv
import json
from pathlib import Path, PurePosixPath

from langchain_core.tools import tool

ROOT = Path(__file__).resolve().parent / "shared" / "geral"
TEXT_LIMIT = 18000
CSV_LIMIT = 20
GUIDES = {"guia_consulta.md", "guia_edicao.md", "contratos.md", "dados/README.md"}
CSVS = {"dados/bncc.csv", "dados/teorias-principios.csv", "dados/teorias-regras.csv"}


def _path(arquivo: str) -> Path:
    parts = PurePosixPath(arquivo).parts
    if not parts or "\\" in arquivo or arquivo.startswith("/") or ".." in parts:
        raise ValueError("Use um caminho relativo listado no guia de consulta.")
    allowed = arquivo in GUIDES | CSVS or (
        len(parts) == 2 and parts[0] in {"teorias", "formatos-de-aula"} and parts[1].endswith(".md")
    )
    if not allowed:
        raise ValueError("Referência não permitida. Para templates, use consultar_templates.")
    path = ROOT
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Links não são permitidos no acervo.")
    if ROOT.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("Referência não encontrada no acervo.")
    return path


def read_reference(arquivo: str, inicio: int = 0, filtros: dict[str, str] | None = None) -> dict:
    if inicio < 0:
        raise ValueError("inicio deve ser maior ou igual a zero.")
    path = _path(arquivo)
    if arquivo not in CSVS:
        if filtros:
            raise ValueError("filtros só se aplica a CSV.")
        text = path.read_text(encoding="utf-8")
        end = min(inicio + TEXT_LIMIT, len(text))
        return {"arquivo": arquivo, "conteudo": text[inicio:end], "total": len(text),
                "unidade": "caracteres", "proximo_inicio": end if end < len(text) else None}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames or []
        if any(key not in columns for key in (filtros or {})):
            raise ValueError("Coluna inválida. Colunas disponíveis: " + ", ".join(columns))

        def matches(row):
            for key, value in (filtros or {}).items():
                candidates = ([v.strip() for v in row[key].split(";")] if key == "grade"
                              else json.loads(row[key]) if key == "theories" else [row[key]])
                if value.casefold() not in [v.casefold() for v in candidates]:
                    return False
            return True

        rows = [row for row in reader if matches(row)]
    selected, size = [], 0
    for row in rows[inicio:inicio + CSV_LIMIT]:
        length = len(json.dumps(row, ensure_ascii=False))
        if length > TEXT_LIMIT:
            raise ValueError("Registro excede o limite de consulta; use a referência Markdown correspondente.")
        if size + length > TEXT_LIMIT:
            break
        selected.append(row)
        size += length
    end = inicio + len(selected)
    return {"arquivo": arquivo, "colunas": columns, "registros": selected, "total": len(rows),
            "unidade": "registros_filtrados", "proximo_inicio": end if end < len(rows) else None}


@tool
def consultar_acervo(arquivo: str = "guia_consulta.md", inicio: int = 0,
                     filtros: dict[str, str] | None = None) -> str:
    """Lê guias, formatos de aula, teorias e CSVs públicos; não escreve arquivos.

    Disponível nas audiências sugeridas e no editor. Comece por guia_consulta.md;
    depois leia os índices e apenas as referências escolhidas. Caminhos relativos
    à biblioteca geral, por exemplo teorias/_indice.md ou dados/bncc.csv.
    Não acessa templates: use consultar_templates. Não acessa dados particulares.
    Markdown: inicio é deslocamento em caracteres, até 18000 por chamada.
    CSV: inicio é deslocamento nos registros filtrados, até 20 por chamada.
    filtros combina colunas por igualdade sem diferenciar maiúsculas; grade
    aceita um ano e theories um nome contido na lista. Use proximo_inicio para
    continuar; null indica fim. Não alegue ter lido as partes não retornadas.
    """
    try:
        result = read_reference(arquivo, inicio, filtros)
    except (ValueError, OSError) as exc:
        result = {"erro": str(exc) if isinstance(exc, ValueError) else "Não foi possível ler esta referência."}
    return json.dumps(result, ensure_ascii=False)
