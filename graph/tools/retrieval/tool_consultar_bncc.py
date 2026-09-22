"""Tool de LangChain para consultar as habilidades da BNCC."""

import csv
import json
from functools import lru_cache
from pathlib import Path

from langchain_core.tools import tool

CAMINHO_BNCC = Path(__file__).resolve().parent / "dados" / "bncc.csv"

ETAPAS = {
    "fundamental": "EF_AF",
    "fundamental 2": "EF_AF",
    "anos finais": "EF_AF",
    "ef": "EF_AF",
    "ef_af": "EF_AF",
    "medio": "EM",
    "médio": "EM",
    "ensino medio": "EM",
    "ensino médio": "EM",
    "em": "EM",
}


@lru_cache(maxsize=1)
def _carregar() -> list[dict]:
    with CAMINHO_BNCC.open(encoding="utf-8") as arquivo:
        return list(csv.DictReader(arquivo))


def _normalizar_etapa(etapa: str) -> str | None:
    return ETAPAS.get((etapa or "").strip().lower())


def _anos(valor: str) -> set[str]:
    return {parte.strip() for parte in (valor or "").split(";") if parte.strip()}


@tool("consultar_bncc")
def consultar_bncc(etapa: str, ano: str, componente: str = "") -> str:
    """Lista as habilidades da BNCC de uma etapa, ano e componente curricular.

    Use antes de citar qualquer código de habilidade. Só existem os códigos
    devolvidos por esta ferramenta; nunca escreva um código que não apareça
    aqui e nunca reescreva a redação oficial de uma habilidade.

    Args:
        etapa: "fundamental" para os Anos Finais ou "medio" para o Ensino Médio.
        ano: 6, 7, 8 ou 9 no Fundamental; 1, 2 ou 3 no Ensino Médio.
        componente: componente curricular, por exemplo "História" ou
            "Língua Portuguesa". Vazio devolve todos os componentes do ano.

    Returns:
        JSON com ``code``, ``component``, ``field``, ``knowledge_object`` e
        ``description`` de cada habilidade, além do total encontrado.
    """
    etapa_normalizada = _normalizar_etapa(etapa)
    if not etapa_normalizada:
        return json.dumps(
            {"erro": "Etapa inválida. Use 'fundamental' ou 'medio'."}, ensure_ascii=False
        )

    ano_procurado = str(ano).strip()
    componente_procurado = (componente or "").strip().lower()

    encontrados = []
    componentes_disponiveis = set()
    for linha in _carregar():
        if linha["education_stage"] != etapa_normalizada:
            continue
        if ano_procurado and ano_procurado not in _anos(linha["grade"]):
            continue
        componentes_disponiveis.add(linha["component"])
        if componente_procurado and componente_procurado not in linha["component"].lower():
            continue
        encontrados.append(
            {
                "code": linha["code"],
                "component": linha["component"],
                "field": linha["field"] or None,
                "knowledge_object": linha["knowledge_object"] or None,
                "description": linha["description"],
            }
        )

    if not encontrados:
        return json.dumps(
            {
                "total": 0,
                "habilidades": [],
                "componentes_disponiveis": sorted(componentes_disponiveis),
                "aviso": "Nenhuma habilidade para esse filtro. Confira o ano e o componente.",
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {"total": len(encontrados), "habilidades": encontrados}, ensure_ascii=False
    )
