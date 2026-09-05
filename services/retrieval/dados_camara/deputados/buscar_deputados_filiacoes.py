import requests
import json
import time
from datetime import date, timedelta
from pathlib import Path


BASE_URL = "https://dadosabertos.camara.leg.br/api/v2/deputados"
THIS_MODULE_DIR = Path(__file__).resolve().parent
DATASETS_DIR = (THIS_MODULE_DIR / ".." / "datasets")
DATASETS_DIR.mkdir(parents=True, exist_ok=True, )


def gerar_janelas(data_inicio_str, data_fim_str, anos_por_janela=4):
    """Quebra o intervalo [data_inicio_str, data_fim_str] em janelas de N anos (YYYY-MM-DD)."""
    data_inicio = date.fromisoformat(data_inicio_str)
    data_fim = date.fromisoformat(data_fim_str)

    janelas = []
    inicio_atual = data_inicio
    while inicio_atual < data_fim:
        try:
            proximo_inicio = inicio_atual.replace(year=inicio_atual.year + anos_por_janela)
        except ValueError:
            # 29 de fevereiro caindo num ano não bissexto
            proximo_inicio = inicio_atual.replace(day=28, year=inicio_atual.year + anos_por_janela)

        fim_atual = min(proximo_inicio - timedelta(days=1), data_fim)
        janelas.append((inicio_atual.isoformat(), fim_atual.isoformat()))
        inicio_atual = proximo_inicio

    return janelas


def buscar_historico_partidos(id_deputado):
    url = f"{BASE_URL}/{id_deputado}/historico"
    headers = {"Accept": "application/json"}

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        eventos = resp.json().get("dados", [])
    except Exception as e:
        print(f"Erro ao buscar histórico do ID {id_deputado}: {e}")
        return []

    if not eventos:
        return []

    eventos.sort(key=lambda e: e.get("dataHora") or "")
    periodos = []
    periodo_atual = None

    for ev in eventos:
        partido = ev.get("siglaPartido")
        data = ev.get("dataHora")

        if periodo_atual is None or partido != periodo_atual["partido"]:
            if periodo_atual is not None:
                periodo_atual["dataFim"] = data
                periodos.append(periodo_atual)
            periodo_atual = {"partido": partido, "dataInicio": data, "dataFim": None}

    if periodo_atual is not None:
        periodos.append(periodo_atual)  # último período: dataFim=None (ainda vigente ou fim de mandato)

    return periodos


def buscar_deputados_com_historico(
    itens_por_pagina=100,
    pausa=0.2,
    limite=None,
    data_inicio_geral="2000-01-01",
    anos_por_janela=4,
):
    deputados_dict = {}
    headers = {"Accept": "application/json"}

    # Sem dataInicio/dataFim, /deputados só retorna a legislatura atual — por
    # isso a busca é repetida em janelas de N anos, cobrindo todo o período,
    # e os resultados são mesclados (deduplicados por id)
    data_fim_geral = date.today().isoformat()
    janelas = gerar_janelas(data_inicio_geral, data_fim_geral, anos_por_janela)
    print(f"Buscando deputados em {len(janelas)} janela(s) de {anos_por_janela} ano(s), de {data_inicio_geral} até {data_fim_geral}.")

    for inicio_janela, fim_janela in janelas:
        print(f"\nJanela {inicio_janela} a {fim_janela}:")
        params = {
            "ordem": "ASC",
            "ordenarPor": "nome",
            "itens": itens_por_pagina,
            "pagina": 1,
            "dataInicio": inicio_janela,
            "dataFim": fim_janela,
        }
        url = BASE_URL

        while url:
            resp = requests.get(url, params=params if url == BASE_URL else None, headers=headers, timeout=30)
            resp.raise_for_status()
            payload = resp.json()

            novos = 0
            for d in payload.get("dados", []):
                dep_id = d["id"]
                if dep_id not in deputados_dict:
                    deputados_dict[dep_id] = {
                        "id": dep_id,
                        "nome": d.get("nome"),
                        "siglaUf": d.get("siglaUf"),
                        "urlFoto": d.get("urlFoto"),
                        "email": d.get("email"),
                        "historicoPartidos": [],
                    }
                    novos += 1

            links = payload.get("links", [])
            url = next((l["href"] for l in links if l["rel"] == "next"), None)
            print(f"  Página processada ({novos} novo(s) nesta página). Total únicos até agora: {len(deputados_dict)}")
            time.sleep(pausa)

    lista_deputados = list(deputados_dict.values())
    if limite:
        lista_deputados = lista_deputados[:limite]

    print(f"\nIniciando busca de histórico de partidos para {len(lista_deputados)} deputados...")
    for i, deputado in enumerate(lista_deputados):
        print(f"[{i+1}/{len(lista_deputados)}] Buscando histórico para: {deputado['nome']}")
        deputado["historicoPartidos"] = buscar_historico_partidos(deputado["id"])
        time.sleep(pausa)

    return lista_deputados


if __name__ == "__main__":
    # Remova o parâmetro 'limite' (ou defina limite=None) para rodar com todos os deputados.
    # Aviso: com todas as legislaturas desde 1950 e uma pausa de 0.2s, a busca leva bem mais
    # tempo que antes (várias janelas x várias páginas x histórico individual de cada deputado).
    deputados = buscar_deputados_com_historico(limite=None)

    json_name = "deputados"
    with open(f"{DATASETS_DIR}/{json_name}.json", "w", encoding="utf-8") as f:
        json.dump(deputados, f, ensure_ascii=False, indent=2)

    print(f"\nArquivo '{json_name}.json' salvo com sucesso em {DATASETS_DIR}.")