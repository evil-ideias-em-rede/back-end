"""Geração de janelas de datas para respeitar o limite de intervalo da API."""

from datetime import date, timedelta


def gerar_janelas(data_inicio_str, data_fim_str, anos_por_janela=4):
    """Quebra o intervalo [data_inicio_str, data_fim_str] em janelas de N anos."""
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
