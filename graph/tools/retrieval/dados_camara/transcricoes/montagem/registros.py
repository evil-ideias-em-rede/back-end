"""
Monta os registros finais de cada discurso, cruzando:
  - API nova (transcrição/keywords) via get_discursos
  - SITAQWeb (número da sessão) via buscar_sessoes_sitaqweb
  - Pauta dos eventos de Plenário do período, casada por data + horário
"""

import time
from datetime import datetime
from ..config import PAUSA_ENTRE_CHAMADAS
from ..api_camara import get_discursos, buscar_eventos_plenario, get_pauta
from ..sitaqweb import buscar_sessoes_sitaqweb
from ..datas import data_hora_para_chave, data_iso_de_datahora, para_datetime
from ..casamento import escolher_eventos_do_discurso


def get_fala(discurso):
    """
    Devolve o texto do que foi dito, na melhor fonte disponível:
    - transcricao (texto integral, quando a Câmara já processou)
    - sumario (resumo redigido pela Câmara)
    """
    if discurso.get("transcricao"):
        return {"fonte": "transcricao", "texto": discurso["transcricao"]}
    if discurso.get("sumario"):
        return {"fonte": "sumario", "texto": discurso["sumario"]}
    return {"fonte": None, "texto": None}


def sessao_por_intervalo(sessoes):
    """Cria intervalos de sessão a partir dos horários do SITAQWeb."""
    inicio_por_sessao = {}
    for sessao in sessoes:
        try:
            inicio = datetime.strptime(
                f"{sessao['data']} {sessao['hora']}", "%d/%m/%Y %H:%M"
            )
        except (KeyError, TypeError, ValueError):
            continue
        numero = sessao.get("nuSessao")
        if numero and (numero not in inicio_por_sessao or inicio < inicio_por_sessao[numero][0]):
            inicio_por_sessao[numero] = (inicio, sessao)

    return sorted(inicio_por_sessao.values(), key=lambda item: item[0])


def encontrar_sessao(data_hora_iso, sessoes_por_chave, intervalos):
    """Encontra a sessão por horário exato ou pelo intervalo da sessão."""
    data_br, hora = data_hora_para_chave(data_hora_iso)
    sessao = sessoes_por_chave.get((data_br, hora))
    if sessao:
        return sessao

    try:
        momento = datetime.fromisoformat(data_hora_iso)
    except (TypeError, ValueError):
        return None

    for indice, (inicio, sessao) in enumerate(intervalos):
        proximo_inicio = intervalos[indice + 1][0] if indice + 1 < len(intervalos) else None
        if inicio <= momento and (proximo_inicio is None or momento < proximo_inicio):
            return sessao
    return None


def montar_registros(id_deputado, nome_deputado, data_inicio_iso, data_fim_iso):
    """
    Monta uma lista de registros {sessao, fala, ...} cruzando:
      - API nova (transcricao/keywords) por id_deputado + intervalo de datas (ISO)
      - SITAQWeb (nuSessao) por nome_deputado + data inicial (formato BR)
      - Pauta dos eventos de Plenário do período (o que estava previsto/em
        discussão naquele dia), casada por DATA + HORÁRIO
        (ver escolher_eventos_do_discurso)
    """
    discursos = get_discursos(id_deputado, data_inicio_iso, data_fim_iso)

    data_inicio_br, _ = data_hora_para_chave(data_inicio_iso + "T00:00")
    sessoes = buscar_sessoes_sitaqweb(nome_deputado, data_inicio_br)

    # Remove apenas duplicatas exatas. Entradas com mesma data/hora, mas URL
    # diferente, são mantidas na lista para não perder dados do SITAQWeb.
    sessoes_unicas = []
    urls_vistas = set()
    for sessao in sessoes:
        url = sessao.get("url_texto_integral")
        if url in urls_vistas:
            continue
        urls_vistas.add(url)
        sessoes_unicas.append(sessao)

    # O discurso da API é casado pela data e hora. Se houver duas sessões
    # diferentes com a mesma chave, preserva a primeira (sem sobrescrever
    # silenciosamente) e avisa no terminal.
    sessoes_por_chave = {}
    colisoes = 0
    for sessao in sessoes_unicas:
        chave = (sessao.get("data"), sessao.get("hora"))
        if chave in sessoes_por_chave:
            colisoes += 1
            continue
        sessoes_por_chave[chave] = sessao
    if colisoes:
        print(f"SITAQWeb: {colisoes} colisão(ões) de data/hora para {nome_deputado}; primeira mantida.")
    intervalos_sessoes = sessao_por_intervalo(sessoes_unicas)

    # Eventos de Plenário no período, pra buscar a pauta (o que seria discutido)
    eventos_plenario = buscar_eventos_plenario(data_inicio_iso, data_fim_iso)
    eventos_por_data = {}
    for ev in eventos_plenario:
        data_ev = data_iso_de_datahora(ev.get("dataHoraInicio"))
        eventos_por_data.setdefault(data_ev, []).append(ev)

    # cache de pauta por idEvento pra não repetir chamada à toa
    pauta_por_evento = {}

    registros = []
    for d in discursos:
        sessao_sitaq = encontrar_sessao(
            d.get("dataHoraInicio"), sessoes_por_chave, intervalos_sessoes
        )
        data_iso_discurso = data_iso_de_datahora(d.get("dataHoraInicio"))

        # Candidatos: eventos de Plenário do mesmo dia. escolher_eventos_do_discurso
        # decide qual(is) desses candidatos realmente corresponde(m) à sessão do
        # discurso -- por horário exato, depois por tipo (evita solenes), depois
        # por proximidade -- em vez de misturar a pauta de todos os eventos do dia.
        candidatos = eventos_por_data.get(data_iso_discurso, [])
        momento_discurso = para_datetime(d.get("dataHoraInicio"))
        eventos_do_discurso = escolher_eventos_do_discurso(candidatos, momento_discurso)

        pauta_do_dia = []
        for ev in eventos_do_discurso:
            id_evento = ev["id"]
            if id_evento not in pauta_por_evento:
                pauta_por_evento[id_evento] = get_pauta(id_evento)
                time.sleep(PAUSA_ENTRE_CHAMADAS)
            pauta_do_dia.extend(pauta_por_evento[id_evento])

        # urlRegistro: link do vídeo da sessão (geralmente YouTube), vem
        # direto no evento -- pega do primeiro evento casado que tiver o
        # campo preenchido.
        url_video = next(
            (ev.get("urlRegistro") for ev in eventos_do_discurso if ev.get("urlRegistro")),
            None,
        )

        sessao = {
            "nuSessao": sessao_sitaq["nuSessao"] if sessao_sitaq else None,
            "tipoSessao": sessao_sitaq["tipoSessao"] if sessao_sitaq else None,
            "fase": (sessao_sitaq["fase"] if sessao_sitaq else None) or (d.get("faseEvento") or {}).get("titulo"),
            "url_texto_integral": sessao_sitaq["url_texto_integral"] if sessao_sitaq else None,
            "url_video": url_video,
            "pauta": pauta_do_dia,
        }

        fala = get_fala(d)

        registros.append({
            "deputadoId": id_deputado,
            "keywords": d.get("keywords"),
            "dataHoraInicio": d.get("dataHoraInicio"),
            "dataHoraFim": d.get("dataHoraFim"),
            "tipoDiscurso": d.get("tipoDiscurso"),
            "sessao": sessao,
            "sumario": d.get("sumario"),
            "transcricao": d.get("transcricao"),
            "fala_fonte": fala["fonte"],
            "fala": fala["texto"],
        })

    return registros


def pontuar_item_pauta(texto_tema, keywords_discurso):
    """
    Conta quantos termos das 'keywords' do discurso aparecem no texto do
    tema (ementa) de um item de pauta. É só uma dica visual pra achar, no
    meio de 20-30 itens, qual provavelmente é o que o deputado estava
    discursando sobre -- não é um cruzamento oficial dos dados da Câmara,
    é comparação de texto simples (substring, case-insensitive).
    """
    if not texto_tema or not keywords_discurso: return 0
    texto_norm = texto_tema.lower()
    termos = [k.strip().lower() for k in keywords_discurso.split(",") if k.strip()]
    return sum(1 for termo in termos if termo in texto_norm)
