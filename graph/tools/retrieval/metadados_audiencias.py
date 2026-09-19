"""
TAG (categoria temática) e keywords por audiência, pra alimentar o filtro
de `buscar_audiencias` (ver `tool_buscar_audiencias.py`).

TAG: classificação por LLM contra uma taxonomia FECHADA (`TAGS_AUDIENCIA`)
— precisa ser fechada pra funcionar como filtro (`WHERE tag = ?`); texto
livre não garante que audiências do mesmo tema caiam no mesmo valor. Usa
`metadados.assunto` como input (barato, ~1 frase) em vez da transcrição
inteira. Uma tag por audiência (não por chunk) — todos os chunks de uma
mesma audiência recebem o mesmo valor.

Keywords: extração determinística (TF-IDF de unigramas + bigramas sobre
`materia`, sem LLM) — aqui é extração de termo literal, não classificação
semântica, então regra determinística é apropriada (diferente da TAG).

Schema: `tag` vira coluna em `documentos` (repetida por chunk — é um valor
curto, sem custo real de duplicar). `assunto`/`materia`/`envolvidos`/
`keywords` vão pra uma tabela nova `audiencias` (uma linha por audiência,
não por chunk) — `materia` pode passar de 6.000 caracteres, duplicar isso
em ~60 chunks por audiência seria desperdício real de espaço.

Uso:
    python metadados_audiencias.py popular
"""

import json
import os
import re
import sqlite3
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from fts_index import INDICE_PADRAO, PUBLIC_HEARING_LDS

load_dotenv(override=True)

MODELO_PADRAO = os.getenv("OPENAI_MODEL_NAME", "gpt-5.6-luna")
TAMANHO_LOTE_CLASSIFICACAO = 25
N_KEYWORDS = 8

TAGS_AUDIENCIA = [
    "meio_ambiente_e_energia",
    "tecnologia_e_inteligencia_artificial",
    "direitos_humanos_e_igualdade_racial",
    "saude_publica",
    "direitos_da_mulher",
    "seguranca_publica",
    "educacao",
    "economia_e_tributacao",
    "trabalho_e_previdencia",
    "infraestrutura_e_desenvolvimento_regional",
    "cultura",
    "agropecuaria",
    "direitos_indigenas_e_povos_tradicionais",
    "defesa_civil_e_desastres_naturais",
    "regulacao_de_plataformas_digitais_e_midia",
    "relacoes_exteriores_e_defesa_nacional",
    "direitos_da_pessoa_idosa",
    "transporte_e_transito",
    "concorrencia_e_regulacao_economica",
    "outros",
]

_STOPWORDS_PT = {
    "a", "as", "o", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das",
    "em", "no", "na", "nos", "nas", "num", "numa", "por", "pelo", "pela", "pelos", "pelas",
    "para", "com", "sem", "sob", "sobre", "entre", "até", "após", "ante", "desde",
    "e", "ou", "mas", "que", "se", "como", "quando", "quanto", "porque", "pois",
    "não", "sim", "já", "ainda", "também", "só", "mais", "menos", "muito", "muitos",
    "muita", "muitas", "pouco", "poucos", "tão", "bem", "mal",
    "é", "foi", "foram", "ser", "são", "está", "estão", "estava", "estavam", "ter",
    "tem", "têm", "tinha", "tinham", "houve", "há", "seja", "sejam", "será", "serão",
    "fazer", "fez", "faz", "disse", "diz", "afirmou", "afirma", "segundo",
  "este", "esta", "estes", "estas", "esse", "essa", "esses", "essas", "isso", "isto",
  "aquele", "aquela", "aqueles", "aquelas", "aquilo", "seu", "sua", "seus", "suas",
  "meu", "minha", "meus", "minhas", "nosso", "nossa", "nossos", "nossas",
  "ele", "ela", "eles", "elas", "eu", "tu", "nós", "vós", "você", "vocês",
  "lhe", "lhes", "me", "te", "nos", "vos", "dele", "dela", "deles", "delas",
  "qual", "quais", "quem", "cujo", "cuja", "cujos", "cujas", "onde", "cada", "todo",
  "toda", "todos", "todas", "outro", "outra", "outros", "outras", "mesmo", "mesma",
  "durante", "após", "ainda", "então", "assim", "aos", "às", "ao",
}


def _normalizar_token(token: str) -> str:
    return token.lower()


def _tokenizar(texto: str) -> list[str]:
    return [
        _normalizar_token(t)
        for t in re.findall(r"[A-Za-zÀ-ÿ]+", texto)
        if len(t) > 2
    ]


def _termos_candidatos(texto: str) -> Counter:
    """Unigramas + bigramas, descartando termos que são (ou contêm) stopword."""
    tokens = _tokenizar(texto)
    termos = Counter()
    for i, t in enumerate(tokens):
        if t not in _STOPWORDS_PT:
            termos[t] += 1
        if i + 1 < len(tokens):
            t2 = tokens[i + 1]
            if t not in _STOPWORDS_PT and t2 not in _STOPWORDS_PT:
                termos[f"{t} {t2}"] += 1
    return termos


def _construir_idf(textos: list[str]) -> dict[str, float]:
    import math

    doc_freq: Counter = Counter()
    for texto in textos:
        for termo in _termos_candidatos(texto).keys():
            doc_freq[termo] += 1
    n_docs = len(textos)
    return {termo: math.log((n_docs + 1) / (df + 1)) + 1 for termo, df in doc_freq.items()}


def extrair_keywords(texto: str, idf: dict[str, float], n: int = N_KEYWORDS) -> list[str]:
    tf = _termos_candidatos(texto)
    if not tf:
        return []
    pontuados = sorted(
        ((termo, freq * idf.get(termo, 1.0)) for termo, freq in tf.items()),
        key=lambda item: item[1],
        reverse=True,
    )
    return [termo for termo, _ in pontuados[:n]]


def garantir_schema_metadados(conexao: sqlite3.Connection) -> None:
    colunas = {row[1] for row in conexao.execute("PRAGMA table_info(documentos)")}
    if "tag" not in colunas:
        conexao.execute("ALTER TABLE documentos ADD COLUMN tag TEXT")

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
    conexao.commit()


def _carregar_audiencias_lds(caminho_jsonl: Path = PUBLIC_HEARING_LDS) -> list[dict]:
    audiencias = []
    with caminho_jsonl.open(encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if not linha:
                continue
            registro = json.loads(linha)
            metadados = registro.get("metadados") or {}
            envolvidos = [
                {"nome": e.get("nome"), "cargo": e.get("cargo")}
                for e in (metadados.get("envolvidos") or [])
            ]
            audiencias.append(
                {
                    "ref_id": str(registro["id"]),
                    "assunto": metadados.get("assunto") or "",
                    "materia": (registro.get("materia") or "").strip(),
                    "envolvidos": envolvidos,
                }
            )
    return audiencias


class _ClassificacaoLote(BaseModel):
    classificacoes: list[dict] = Field(
        description=(
            "Uma entrada por audiência recebida, na forma "
            "{'ref_id': '<mesmo ref_id recebido>', 'tag': '<uma das tags da lista>'}."
        )
    )


def _prompt_sistema_classificacao() -> str:
    tags_formatadas = "\n".join(f"- {t}" for t in TAGS_AUDIENCIA)
    return (
        "Você classifica audiências públicas da Câmara dos Deputados numa "
        "categoria temática. Pra cada audiência recebida (ref_id + assunto), "
        "escolha EXATAMENTE UMA tag da lista abaixo — nunca invente uma tag "
        "fora dela. Use 'outros' só se nenhuma categoria fizer sentido.\n\n"
        f"Tags disponíveis:\n{tags_formatadas}"
    )


def _classificar_tags_lote(
    itens: list[dict], modelo: str = MODELO_PADRAO
) -> dict[str, str]:
    """`itens`: [{"ref_id": ..., "assunto": ...}, ...]. Retorna {ref_id: tag},
    com fallback pra 'outros' se o LLM devolver ref_id não pedido ou tag
    fora da taxonomia — nunca deixamos uma tag inválida entrar no banco."""
    linhas = "\n".join(f"- ref_id={item['ref_id']}: {item['assunto']}" for item in itens)
    cliente = ChatOpenAI(model=modelo, temperature=0).with_structured_output(_ClassificacaoLote)
    resposta: _ClassificacaoLote = cliente.invoke(
        [("system", _prompt_sistema_classificacao()), ("user", linhas)]
    )

    ref_ids_pedidos = {item["ref_id"] for item in itens}
    resultado: dict[str, str] = {}
    for c in resposta.classificacoes:
        ref_id = str(c.get("ref_id"))
        tag = c.get("tag")
        if ref_id not in ref_ids_pedidos:
            continue
        resultado[ref_id] = tag if tag in TAGS_AUDIENCIA else "outros"

    for item in itens:
        resultado.setdefault(item["ref_id"], "outros")
    return resultado


def _lotes(sequencia: list, tamanho: int):
    for i in range(0, len(sequencia), tamanho):
        yield sequencia[i : i + tamanho]


def popular_metadados_audiencias(
    conexao: sqlite3.Connection,
    caminho_jsonl: Path = PUBLIC_HEARING_LDS,
    modelo: str = MODELO_PADRAO,
) -> int:
    garantir_schema_metadados(conexao)
    audiencias = _carregar_audiencias_lds(caminho_jsonl)

    idf = _construir_idf([a["materia"] for a in audiencias])

    tags: dict[str, str] = {}
    for lote in _lotes(audiencias, TAMANHO_LOTE_CLASSIFICACAO):
        itens = [{"ref_id": a["ref_id"], "assunto": a["assunto"]} for a in lote]
        tags.update(_classificar_tags_lote(itens, modelo=modelo))
        print(f"  {len(tags)}/{len(audiencias)} audiências classificadas")

    total = 0
    for a in audiencias:
        keywords = extrair_keywords(a["materia"], idf)
        tag = tags.get(a["ref_id"], "outros")

        conexao.execute(
            """
            INSERT INTO audiencias (ref_id, assunto, materia, envolvidos, keywords)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(ref_id) DO UPDATE SET
                assunto=excluded.assunto, materia=excluded.materia,
                envolvidos=excluded.envolvidos, keywords=excluded.keywords
            """,
            (
                a["ref_id"],
                a["assunto"],
                a["materia"],
                json.dumps(a["envolvidos"], ensure_ascii=False),
                json.dumps(keywords, ensure_ascii=False),
            ),
        )
        conexao.execute(
            "UPDATE documentos SET tag = ? WHERE source = 'audiencia' AND ref_id = ?",
            (tag, a["ref_id"]),
        )
        total += 1

    conexao.commit()
    return total


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Popula TAG e keywords das audiências")
    parser.add_argument("--indice", default=str(INDICE_PADRAO))
    parser.add_argument("comando", choices=["popular"])
    args = parser.parse_args()

    conexao = sqlite3.connect(args.indice)
    total = popular_metadados_audiencias(conexao)
    conexao.close()
    print(f"Metadados gravados para {total} audiências.")
