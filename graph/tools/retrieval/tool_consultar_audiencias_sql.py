"""Tool Text-to-SQL para consultar o índice estruturado de audiências.

Esta camada é complementar à busca vetorial: ``buscar_audiencias`` encontra
os trechos mais relevantes e esta tool permite que o agente consulte os dados
estruturados ou leia outros chunks usando linguagem natural.
"""

import json
import os
import re
import sqlite3
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.tools import tool
from openai import OpenAI

from .audiencias import INDICE_PADRAO


load_dotenv(override=False)

_TABELAS_PERMITIDAS = {"audiencias", "documentos"}
_LIMITE_MAXIMO = 50


_DESCRICOES_COLUNAS = {
    ("audiencias", "ref_id"): "identificador da sessão/audiência; cruza com documentos.ref_id",
    ("audiencias", "assunto"): "assunto principal da audiência",
    ("audiencias", "materia"): "matéria jornalística/resumo da audiência",
    ("audiencias", "envolvidos"): "JSON com participantes, cargos e opiniões",
    ("audiencias", "keywords"): "JSON com palavras-chave extraídas da matéria",
    ("audiencias", "estrutura_json"): "estrutura completa da audiência, quando disponível",
    ("documentos", "doc_id"): "identificador único do chunk",
    ("documentos", "source"): "origem do documento",
    ("documentos", "ref_id"): "identificador da audiência de origem",
    ("documentos", "texto"): "texto do chunk da transcrição",
    ("documentos", "paragrafo_inicio"): "índice do primeiro parágrafo do chunk",
    ("documentos", "paragrafo_fim"): "índice do último parágrafo do chunk",
    ("documentos", "tag"): "categoria temática, quando preenchida",
}


def _identificador(nome: str) -> str:
    """Escapa um identificador SQLite vindo do próprio schema."""
    return '"' + nome.replace('"', '""') + '"'


def _valores_distintos(
    conexao: sqlite3.Connection, tabela: str, coluna: str
) -> list[str]:
    identificador_tabela = _identificador(tabela)
    identificador_coluna = _identificador(coluna)
    linhas = conexao.execute(
        f"SELECT DISTINCT {identificador_coluna} "
        f"FROM {identificador_tabela} "
        f"WHERE {identificador_coluna} IS NOT NULL "
        f"ORDER BY {identificador_coluna} LIMIT 100"
    ).fetchall()
    return [str(linha[0]) for linha in linhas]


@lru_cache(maxsize=1)
def _schema_consultavel() -> str:
    """Gera o schema com cardinalidade sem despejar colunas textuais grandes.

    Para cada coluna informa o tipo, a quantidade de valores distintos e, se
    houver menos de 100 valores, os valores possíveis. Assim o modelo pode
    escolher filtros sem receber o conteúdo das transcrições.
    """
    caminho = Path(INDICE_PADRAO).resolve()
    conexao = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
    try:
        blocos = []
        for tabela in sorted(_TABELAS_PERMITIDAS):
            identificador_tabela = _identificador(tabela)
            existe = conexao.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (tabela,),
            ).fetchone()
            if not existe:
                continue

            total = conexao.execute(
                f"SELECT COUNT(*) FROM {identificador_tabela}"
            ).fetchone()[0]
            linhas = [f"tabela {tabela} (linhas: {total}):"]
            for _, coluna, tipo, notnull, _, pk in conexao.execute(
                f"PRAGMA table_info({identificador_tabela})"
            ):
                identificador_coluna = _identificador(coluna)
                distintos = conexao.execute(
                    f"SELECT COUNT(DISTINCT {identificador_coluna}) "
                    f"FROM {identificador_tabela}"
                ).fetchone()[0]
                atributos = [tipo or "NULL"]
                if pk:
                    atributos.append("PRIMARY KEY")
                if notnull:
                    atributos.append("NOT NULL")
                descricao = _DESCRICOES_COLUNAS.get((tabela, coluna))
                linha = f"- {coluna} ({', '.join(atributos)}) — distintos: {distintos}"
                if descricao:
                    linha += f" — {descricao}"
                if 0 < distintos < 100:
                    valores = _valores_distintos(conexao, tabela, coluna)
                    linha += f" — valores possíveis: {', '.join(valores)}"
                linhas.append(linha)
            blocos.append("\n".join(linhas))
        return "\n\n".join(blocos)
    finally:
        conexao.close()


def _gerar_sql(pergunta: str) -> str:
    modelo = os.getenv("OPENAI_MODEL_NAME") or os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
    prompt = f"""Converta a pergunta em uma consulta SQLite somente de leitura.

Regras obrigatórias:
- Retorne somente SQL, sem markdown e sem explicações.
- Gere apenas SELECT.
- Use somente as tabelas audiencias e documentos e as colunas descritas.
- Para uma audiência específica, filtre por ref_id.
- Para ler falas/transcrições, consulte documentos.texto.
- Se a coluna estrutura_json aparecer no schema, ela pode ser usada para
  obter a audiência completa no formato do frontend.
- Inclua LIMIT {_LIMITE_MAXIMO} ou menor.

Schema:
{_schema_consultavel()}

Pergunta do agente:
{pergunta}
"""
    resposta = OpenAI().responses.create(model=modelo, input=prompt)
    return resposta.output_text


def _validar_sql(sql: str) -> str:
    sql = re.sub(r"^```(?:sql)?\s*|\s*```$", "", sql.strip(), flags=re.IGNORECASE)
    sql = sql.rstrip().rstrip(";").rstrip()
    if not re.match(r"^SELECT\b", sql, flags=re.IGNORECASE):
        raise ValueError("A consulta gerada não é um SELECT.")
    if ";" in sql or "--" in sql or "/*" in sql or "*/" in sql:
        raise ValueError("A consulta contém separadores ou comentários não permitidos.")
    if re.search(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|REPLACE|PRAGMA|VACUUM)\b",
        sql,
        flags=re.IGNORECASE,
    ):
        raise ValueError("Somente consultas de leitura são permitidas.")

    tabelas = re.findall(
        r"\b(?:FROM|JOIN)\s+(?:main\.)?[`\"]?([A-Za-z_][A-Za-z0-9_]*)[`\"]?",
        sql,
        flags=re.IGNORECASE,
    )
    if not tabelas or any(tabela.lower() not in _TABELAS_PERMITIDAS for tabela in tabelas):
        raise ValueError("A consulta referencia uma tabela não permitida.")

    if not re.search(r"\bLIMIT\s+\d+\b", sql, flags=re.IGNORECASE):
        sql = f"{sql.rstrip()} LIMIT {_LIMITE_MAXIMO}"
    return sql


@tool("consultar_audiencias_sql")
def consultar_audiencias_sql(pergunta: str) -> str:
    """Consulta dados das audiências por linguagem natural usando Text-to-SQL.

    Use depois de ``buscar_audiencias`` quando precisar ler mais conteúdo de
    uma audiência, obter a fala completa de um chunk, consultar metadados ou
    recuperar ``estrutura_json``. Informe o ``ref_id`` encontrado na busca
    vetorial quando quiser restringir a consulta a uma audiência.

    A consulta é somente leitura e fica limitada às tabelas ``audiencias`` e
    ``documentos`` do índice local.

    Estrutura das tabelas:

    tabela ``audiencias``:
    - ``ref_id`` (TEXT, PRIMARY KEY) — identificador da sessão/audiência;
      cruza com ``documentos.ref_id``.
    - ``assunto`` (TEXT) — assunto principal da audiência.
    - ``materia`` (TEXT) — matéria jornalística/resumo da audiência.
    - ``envolvidos`` (TEXT) — JSON com participantes, cargos e opiniões.
    - ``keywords`` (TEXT) — JSON com palavras-chave extraídas da matéria.
    - ``estrutura_json`` (TEXT, opcional) — estrutura completa, quando
      disponível no índice.

    tabela ``documentos``:
    - ``doc_id`` (TEXT, PRIMARY KEY) — identificador único do chunk.
    - ``source`` (TEXT) — origem do documento, normalmente ``audiencia``.
    - ``ref_id`` (TEXT) — identificador da audiência de origem.
    - ``texto`` (TEXT) — texto do chunk da transcrição.
    - ``paragrafo_inicio`` (INTEGER) — primeiro parágrafo do chunk.
    - ``paragrafo_fim`` (INTEGER) — último parágrafo do chunk.
    - ``tag`` (TEXT, opcional) — categoria temática, quando preenchida.

    O schema enviado ao modelo também informa a quantidade de linhas, os
    valores distintos por coluna e os valores possíveis quando há menos de
    100.
    """
    pergunta = pergunta.strip()
    if not pergunta:
        return json.dumps({"erro": "A pergunta não pode ser vazia."}, ensure_ascii=False)

    try:
        sql = _validar_sql(_gerar_sql(pergunta))
        conexao = sqlite3.connect(INDICE_PADRAO)
        conexao.row_factory = sqlite3.Row
        try:
            linhas = [dict(linha) for linha in conexao.execute(sql).fetchall()]
        finally:
            conexao.close()
        return json.dumps(
            {"pergunta": pergunta, "sql": sql, "resultado": linhas},
            ensure_ascii=False,
        )
    except (ValueError, sqlite3.Error) as exc:
        return json.dumps({"erro": str(exc)}, ensure_ascii=False)
