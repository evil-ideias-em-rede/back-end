"""Busca de discursos na API e classificação por período partidário."""

import requests

from . import montar_registros
from .audiencias_publicas import registros_public_hearing
from .carregamento import carregar_audiencias_publicas
from .config import ANOS_POR_JANELA, DATA_FIM_GERAL, DATA_INICIO_GERAL
from .janelas import gerar_janelas


def data_pertence_ao_periodo(data_hora_inicio, data_inicio_partido, data_fim_partido):
    """
    As datas estão no formato ISO 8601 'YYYY-MM-DDTHH:MM', que é comparável
    diretamente como string (comparação lexicográfica = comparação cronológica).
    dataFim=None (null no JSON) significa que o deputado segue no partido até hoje.
    """
    if data_hora_inicio < data_inicio_partido:
        return False
    if data_fim_partido is not None and data_hora_inicio >= data_fim_partido:
        return False
    return True


def montar_falas_por_partido(deputado, audiencias_publicas=None):
    # Busca em janelas de N anos (a API rejeita com status 400 quando o
    # intervalo é grande demais) e concatena os registros de todas as janelas
    registros = []
    for inicio_janela, fim_janela in gerar_janelas(DATA_INICIO_GERAL, DATA_FIM_GERAL, ANOS_POR_JANELA):
        try:
            registros.extend(montar_registros(
                id_deputado=deputado["id"],
                nome_deputado=deputado["nome"],
                data_inicio_iso=inicio_janela,
                data_fim_iso=fim_janela,
            ))
        except requests.RequestException as erro:
            # Uma janela indisponível não deve interromper os 513 deputados.
            print(
                f"ERRO API: {deputado['nome']} | {inicio_janela} a {fim_janela} | "
                f"{erro}. Pulando janela."
            )

    # Incorpora as audiências públicas locais baixadas do Hugging Face.
    registros.extend(registros_public_hearing(
        deputado,
        audiencias_publicas if audiencias_publicas is not None else carregar_audiencias_publicas(),
    ))

    # Copia cada período e adiciona a lista "discursos"
    historico = [dict(periodo, discursos=[]) for periodo in deputado["historicoPartidos"]]
    sem_periodo = []

    for registro in registros:
        data_hora_inicio = registro.get("dataHoraInicio")

        if not data_hora_inicio:
            sem_periodo.append(registro)
            continue

        encontrou_periodo = False
        for periodo in historico:
            if data_pertence_ao_periodo(data_hora_inicio, periodo["dataInicio"], periodo["dataFim"]):
                periodo["discursos"].append(registro)
                encontrou_periodo = True
                break

        if not encontrou_periodo:
            sem_periodo.append(registro)

    # Falas anteriores ao primeiro período registrado (ou sem data) caem aqui,
    # em vez de serem descartadas silenciosamente
    if sem_periodo:
        historico.append({
            "partido": None,
            "dataInicio": None,
            "dataFim": None,
            "discursos": sem_periodo,
        })

    return historico
