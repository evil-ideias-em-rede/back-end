"""
Busca de sessões no SITAQWeb — o sistema legado que alimenta a página de
pesquisa de discursos do site da Câmara.
"""

import re
import requests
from .config import SITAQ_URL
from urllib.parse import parse_qs
_PADRAO_TEXTOHTML = re.compile(r"TextoHTML\.asp\?([^\"'<>]+)", re.IGNORECASE)


def buscar_sessoes_sitaqweb(nome_deputado, data_inicio_br, data_fim_br="", page_size=100):
    """
    Busca no SITAQWeb (o sistema legado, o mesmo que alimenta a página de
    pesquisa de discursos do site da Câmara). Ao contrário da API nova, aqui
    o número da sessão (nuSessao) já vem GRAVADO junto de cada discurso --
    não é um cruzamento feito na hora, é assim que esse banco sempre guardou
    o dado. Por isso essa é a fonte mais confiável para "qual foi a sessão".

    Datas no formato brasileiro DD/MM/AAAA (como o próprio site espera).
    Devolve uma lista de dicts com: nuSessao, data, hora, fase, tipoSessao,
    orador e a url completa do texto integral (TextoHTML.asp).
    """
    params = {
        "txOrador": nome_deputado,
        "txPartido": "",
        "txUF": "",
        "dtInicio": data_inicio_br,
        "dtFim": data_fim_br,
        "txTexto": "",
        "txSumario": "",
        "basePesq": "plenario",
        "CampoOrdenacao": "dtSessao",
        "PageSize": page_size,
        "TipoOrdenacao": "DESC",
        "btnPesq": "Pesquisar",
    }
    resp = requests.get(SITAQ_URL, params=params, timeout=30)
    resp.raise_for_status()
    html = resp.text

    registros = []
    for match in _PADRAO_TEXTOHTML.finditer(html):
        qs = match.group(1).replace("&amp;", "&")
        qs = re.sub(r"\s+", "", qs) # remove quebras de linha/indentação do HTML
        campos = parse_qs(qs)
        def pega(chave): return campos.get(chave, [None])[0]

        registros.append({
            "nuSessao": pega("nuSessao"),
            "data": pega("Data"),
            "hora": pega("dtHoraQuarto"),
            "fase": pega("txFaseSessao"),
            "tipoSessao": pega("txTipoSessao"),
            "orador": pega("txApelido"),
            "url_texto_integral": f"https://www.camara.leg.br/internet/sitaqweb/TextoHTML.asp?{qs}",
        })

    return registros
