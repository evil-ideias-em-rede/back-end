"""
Chamadas diretas à API de Dados Abertos da Câmara: discursos, eventos de
Plenário, pauta de um evento e busca de deputado por nome/id.
"""

import time

import requests

from .config import BASE, HEADERS, PAUSA_ENTRE_CHAMADAS, ID_ORGAO_PLENARIO


def get_discursos(id_deputado, data_inicio, data_fim, itens=100):
    """Busca (com paginação) todos os discursos de um deputado num intervalo de datas."""
    discursos = []
    pagina = 1

    while True:
        params = {
            "dataInicio": data_inicio,
            "dataFim": data_fim,
            "ordenarPor": "dataHoraInicio",
            "ordem": "ASC",
            "itens": itens,
            "pagina": pagina,
        }
        for tentativa in range(3):
            try:
                resp = requests.get(
                    f"{BASE}/deputados/{id_deputado}/discursos",
                    params=params,
                    headers=HEADERS,
                    timeout=30,
                )
                resp.raise_for_status()
                break
            except requests.RequestException:
                if tentativa == 2:
                    raise
                time.sleep(2 ** tentativa)
        data = resp.json()

        dados = data.get("dados", [])
        if not dados:
            break

        discursos.extend(dados)
        links = {l["rel"]: l["href"] for l in data.get("links", [])}
        if "next" not in links:
            break

        pagina += 1
        time.sleep(PAUSA_ENTRE_CHAMADAS)

    return discursos


def buscar_eventos_plenario(data_inicio_iso, data_fim_iso, id_orgao=ID_ORGAO_PLENARIO):
    """
    Busca eventos (sessões) do Plenário (idOrgao=180 por padrão) num
    intervalo de datas. Cada evento retornado tem um "id" -- é esse id que
    a pauta (get_pauta) exige, e que os discursos normalmente NÃO trazem
    de forma confiável via uriEvento.
    """
    eventos = []
    pagina = 1

    while True:
        params = {
            "dataInicio": data_inicio_iso,
            "dataFim": data_fim_iso,
            "idOrgao": id_orgao,
            "itens": 100,
            "pagina": pagina,
        }
        resp = requests.get(f"{BASE}/eventos", params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        dados = data.get("dados", [])
        if not dados:
            break

        eventos.extend(dados)
        links = {l["rel"]: l["href"] for l in data.get("links", [])}
        if "next" not in links:
            break

        pagina += 1
        time.sleep(PAUSA_ENTRE_CHAMADAS)

    return eventos


def get_pauta(id_evento):
    """
    Devolve os itens da pauta (Ordem do Dia) de um evento -- ou seja, o que
    estava PREVISTO/em discussão ou votação naquela sessão, independente de
    quem discursou. Isso é diferente de "sumario"/"keywords" do discurso:
    aquilo descreve o que UM DEPUTADO falou; a pauta descreve o assunto da
    sessão como um todo (que normalmente cobre vários itens ao mesmo tempo).

    IMPORTANTE: cada item de pauta traz DOIS blocos de proposição, e não dá
    pra usar só um:
      - "proposicao_"           -> o documento do PRÓPRIO item da pauta
                                    (ex.: um requerimento de urgência, um
                                    parecer, uma redação final). A ementa
                                    dele costuma ser só de procedimento,
                                    tipo "Requer a urgência do Projeto de
                                    Lei nº 3262/2026" -- não diz do que
                                    trata o PL 3262.
      - "proposicaoRelacionada_" -> a proposição-ALVO daquele item (no
                                    exemplo acima, o próprio PL 3262/2026).
                                    É AQUI que está a ementa que realmente
                                    descreve o assunto/tema.
    Por isso devolvemos os dois: o item da pauta em si e, quando existir,
    a proposição relacionada com sua ementa -- que é o "tema de verdade".
    """
    resp = requests.get(f"{BASE}/eventos/{id_evento}/pauta", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    itens = resp.json().get("dados", [])

    print(resp.url)

    pauta = []
    for item in itens:
        prop = item.get("proposicao_") or {}
        prop_relacionada = item.get("proposicaoRelacionada_") or {}

        sigla = prop.get("siglaTipo")
        identificacao = f"{sigla} {prop.get('numero')}/{prop.get('ano')}" if sigla else None

        sigla_alvo = prop_relacionada.get("siglaTipo")
        identificacao_alvo = (
            f"{sigla_alvo} {prop_relacionada.get('numero')}/{prop_relacionada.get('ano')}"
            if sigla_alvo else None
        )

        pauta.append({
            "topico": item.get("topico"),
            "regime": item.get("regime"),
            "situacaoItem": item.get("situacaoItem"),
            "relator": (item.get("relator") or {}).get("nome"),
            "proposicao": identificacao,
            "ementa": prop.get("ementa"),
            "proposicaoRelacionada": identificacao_alvo,
            "ementaRelacionada": prop_relacionada.get("ementa"),
            # A ementa da proposição relacionada é o melhor indicador do tema.
            "tema": prop_relacionada.get("ementa") or prop.get("ementa"),
        })

    return pauta


def get_deputado_por_nome(nome_do_deputado=None, ids_deputados=None):
    """
    Busca deputado(s) na API por nome (busca parcial) ou por uma lista de
    ids. Retorna o JSON decodificado (com a chave 'dados').
    """
    params = {}
    if nome_do_deputado:
        params["nome"] = nome_do_deputado
    elif ids_deputados:
        params["id"] = ids_deputados  # requests repete o parâmetro pra cada item da lista

    resp = requests.get(f"{BASE}/deputados", params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()
