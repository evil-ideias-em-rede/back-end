"""Agente que transforma perguntas em SQL e consulta o banco da Câmara."""

import json
import os
import re
import sqlite3
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv
load_dotenv(override=True)

BANCO_PADRAO = Path(__file__).resolve().parents[1] / "datasets" / "deputados.sqlite"


def obter_schema(conexao):
    tabelas = conexao.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    partes = []
    for (tabela,) in tabelas:
        colunas = conexao.execute(f'PRAGMA table_info("{tabela}")').fetchall()
        partes.append(f"tabela {tabela}\n" + "\n".join(f"- {c[1]} ({c[2]})" for c in colunas))
    return "\n\n".join(partes)


def validar_sql(sql):
    limpo = re.sub(r"^```(?:sql)?\s*|\s*```$", "", sql.strip(), flags=re.I)
    if not re.match(r"^(SELECT|WITH)\b", limpo, flags=re.I):
        raise ValueError("A LLM não gerou uma consulta SELECT válida.")
    if ";" in limpo[:-1] or re.search(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|REPLACE|PRAGMA)\b",
        limpo, flags=re.I,
    ):
        raise ValueError("SQL recusado: somente consultas de leitura são permitidas.")
    return limpo


def consultar(pergunta, caminho_banco=BANCO_PADRAO, modelo=None):
    """Gera SQL, executa a consulta e retorna SQL, resultado e resposta."""
    modelo = modelo or os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
    conexao = sqlite3.connect(caminho_banco)
    conexao.row_factory = sqlite3.Row
    try:
        schema = obter_schema(conexao)
        cliente = OpenAI()
        prompt = f"""Você gera SQL SQLite para dados da Câmara dos Deputados.
Gere apenas uma consulta SELECT (ou WITH ... SELECT), sem markdown e sem explicações.
Use somente tabelas e colunas do schema abaixo.

{schema}

Pergunta: {pergunta}
"""
        sql = validar_sql(cliente.responses.create(model=modelo, input=prompt).output_text)
        linhas = [dict(linha) for linha in conexao.execute(sql).fetchall()]
    
        return {"pergunta": pergunta, "resultado": linhas}
    finally:
        conexao.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Consulta o banco da Câmara com LLM")
    parser.add_argument("pergunta")
    parser.add_argument("--banco", default=str(BANCO_PADRAO))
    args = parser.parse_args()
    print(json.dumps(consultar(args.pergunta, args.banco), ensure_ascii=False, indent=2))
