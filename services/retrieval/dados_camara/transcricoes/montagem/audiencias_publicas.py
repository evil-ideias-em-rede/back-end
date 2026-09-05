"""Cruzamento de audiências públicas (PublicHearingBR) com deputados."""

import re

from .carregamento import normalizar_nome


def registros_public_hearing(deputado, audiencias):
    """Retorna audiências em que o deputado aparece como participante."""
    nome_deputado = normalizar_nome(deputado["nome"])
    registros = []
    for audiencia in audiencias:
        envolvidos = audiencia.get("metadados", {}).get("envolvidos", [])
        if not any(normalizar_nome(p.get("nome")) == nome_deputado for p in envolvidos):
            continue

        # As amostras não têm data estruturada; extrai a primeira data da matéria.
        data = None
        encontrada = re.search(r"(\d{2}/\d{2}/\d{4})", audiencia.get("materia", ""))
        if encontrada:
            dia, mes, ano = encontrada.group(1).split("/")
            data = f"{ano}-{mes}-{dia}T00:00"

        registros.append({
            "deputadoId": deputado["id"],
            "keywords": None,
            "dataHoraInicio": data,
            "dataHoraFim": None,
            "tipoDiscurso": "Audiência pública",
            "sessao": {"nuSessao": None, "tipoSessao": "Audiência pública", "fase": None, "url_texto_integral": None, "url_video": None, "pauta": []},
            "sumario": audiencia.get("materia"),
            "transcricao": audiencia.get("transcricao"),
            "fala_fonte": "PublicHearingBR",
            "fala": audiencia.get("transcricao"),
            "publicHearingId": audiencia.get("id"),
        })
    return registros
