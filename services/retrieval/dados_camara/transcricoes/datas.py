"""
Funções auxiliares de data/hora usadas para cruzar discursos, sessões do
SITAQWeb e eventos de Plenário.
"""

from datetime import datetime


def data_hora_para_chave(data_hora_iso):
    """'2026-08-13T12:20' -> ('13/08/2026', '12:20'), pra casar com o SITAQWeb."""
    if not data_hora_iso or "T" not in data_hora_iso:
        return None, None
    data_iso, hora = data_hora_iso.split("T")
    ano, mes, dia = data_iso.split("-")
    return f"{dia}/{mes}/{ano}", hora


def data_iso_de_datahora(data_hora_iso):
    """'2026-08-13T12:20' -> '2026-08-13'"""
    if not data_hora_iso or "T" not in data_hora_iso:
        return None
    return data_hora_iso.split("T")[0]


def para_datetime(data_hora_iso):
    """'2026-08-13T12:20' -> datetime(2026, 8, 13, 12, 20). None se vazio/inválido."""
    if not data_hora_iso:
        return None
    try:
        return datetime.fromisoformat(data_hora_iso)
    except ValueError:
        return None
