"""Tool Text-to-SQL para consultar o índice estruturado de audiências.

Esta camada é complementar à busca vetorial: ``buscar_audiencias`` encontra
os trechos mais relevantes e esta tool permite que o agente consulte os dados
estruturados ou leia outros chunks usando linguagem natural.
"""

import json
import os
import re
import sqlite3

from dotenv import load_dotenv
from langchain_core.tools import tool
from openai import OpenAI

from .audiencias import INDICE_PADRAO


load_dotenv(override=False)

_TABELAS_PERMITIDAS = {"audiencias", "documentos"}
_LIMITE_MAXIMO = 50


def _schema_consultavel() -> str:
    return """
tabela audiencias:
- ref_id TEXT PRIMARY KEY — identificador da audiência
- assunto TEXT — assunto principal
- materia TEXT — matéria/resumo da audiência
- envolvidos TEXT — JSON com participantes e opiniões
- keywords TEXT — palavras-chave
- estrutura_json TEXT — audiência completa em JSON no formato do frontend

tabela documentos:
- doc_id TEXT PRIMARY KEY — identificador do chunk
- source TEXT — origem do documento, normalmente 'audiencia'
- ref_id TEXT — identificador da audiência de origem
- texto TEXT — texto completo do chunk/transcrição
- paragrafo_inicio INTEGER
- paragrafo_fim INTEGER
- tag TEXT — classificação temática, quando preenchida
""".strip()


def _gerar_sql(pergunta: str) -> str:
    modelo = os.getenv("OPENAI_MODEL_NAME") or os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
    prompt = f"""Converta a pergunta em uma consulta SQLite somente de leitura.

Regras obrigatórias:
- Retorne somente SQL, sem markdown e sem explicações.
- Gere apenas SELECT.
- Use somente as tabelas audiencias e documentos e as colunas descritas.
- Para uma audiência específica, filtre por ref_id.
- Para ler falas/transcrições, consulte documentos.texto.
- Para obter a audiência completa no formato do frontend, consulte
  audiencias.estrutura_json.
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
