"""Leitura estruturada de audiências a partir do índice SQLite.

O índice guarda a transcrição em ``documentos`` e os metadados estruturados
em ``audiencias``. A saída mantém as mesmas chaves consumidas pelo frontend
antigo, mas os dados vêm do dataset real de audiências públicas.
"""

import json
import re
import sqlite3
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from langchain_core.tools import tool


BASE_DIR = Path(__file__).resolve().parent
INDICE_PADRAO = BASE_DIR / "indice" / "indice_busca.sqlite"
PUBLIC_HEARING_LDS = BASE_DIR / "public_hearing" / "PublicHearingBR_LDS.jsonl"
PUBLIC_HEARING_ANOTADOS_DIR = BASE_DIR / "dados_camara" / "resultados_mimo_corpus"


@lru_cache(maxsize=1)
def _carregar_audiencias_lds() -> dict[str, dict]:
    """Carrega o dataset real indexado pelo ID da sessão."""
    audiencias = {}
    with PUBLIC_HEARING_LDS.open(encoding="utf-8") as arquivo:
        for linha in arquivo:
            if linha.strip():
                registro = json.loads(linha)
                audiencias[str(registro["id"])] = registro
    return audiencias


@lru_cache(maxsize=1)
def _carregar_audiencias_anotadas() -> dict[str, dict]:
    """Carrega as falas anotadas do MIMO pelo mesmo ID da audiência."""
    audiencias = {}
    if not PUBLIC_HEARING_ANOTADOS_DIR.is_dir():
        return audiencias
    for caminho in PUBLIC_HEARING_ANOTADOS_DIR.glob("*_anotado.json"):
        with caminho.open(encoding="utf-8") as arquivo:
            registro = json.load(arquivo)
        if registro.get("debate_id") is not None:
            audiencias[str(registro["debate_id"])] = registro
    return audiencias


def carregar_audiencia_anotada(audiencia_id: int | str) -> dict | None:
    """Retorna o JSON anotado original da audiência, sem adaptá-lo."""
    try:
        ref_id = str(int(str(audiencia_id).removeprefix("aud-")))
    except (TypeError, ValueError):
        return None
    return _carregar_audiencias_anotadas().get(ref_id)


def _linhas_materia(materia: str) -> list[str]:
    return [linha.strip() for linha in (materia or "").splitlines() if linha.strip()]


def _linhas_descritivas(materia: str) -> list[str]:
    return [
        linha
        for linha in _linhas_materia(materia)
        if not re.fullmatch(r"\d{2}/\d{2}/\d{4}.*", linha)
        and not linha.startswith("Atualizado em ")
        and linha != "•"
    ]


def _data_materia(materia: str) -> str | None:
    encontrado = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", materia or "")
    if not encontrado:
        return None
    return datetime.strptime(encontrado.group(1), "%d/%m/%Y").date().isoformat()


def _corpo_materia(materia: str) -> str:
    """Retorna somente o texto jornalístico, sem título, subtítulo e data."""
    linhas = (materia or "").splitlines()
    indice_data = next(
        (indice for indice, linha in enumerate(linhas) if re.search(r"\b\d{2}/\d{2}/\d{4}\b", linha)),
        None,
    )
    if indice_data is None:
        return materia.strip()
    return "\n\n".join(linha.strip() for linha in linhas[indice_data + 1 :] if linha.strip())


def _partido(cargo: str) -> str | None:
    """Extrai o partido quando o cargo contém o padrão Partido-UF."""
    encontrado = re.search(r"\(([^()]+)-[A-Za-z]{2}\)", cargo or "")
    if not encontrado:
        return None
    return encontrado.group(1).strip().upper()


_MARCADORES_PROPOSTA = (
    "é preciso",
    "e preciso",
    "é necessário",
    "e necessario",
    "deve ",
    "devem ",
    "tem que",
    "têm que",
    "temos que",
    "precisamos",
    "defende que",
    "defendem que",
    "propõe",
    "propoe",
    "propõem",
    "propoem",
    "pede que",
    "pedem que",
    "solicita",
    "solicitam",
    "sugere",
    "sugerem",
    "recomenda",
    "recomendam",
    "queremos",
)


def _extrair_propostas(envolvidos: list[dict], audiencia_id: int) -> list[dict]:
    """Extrai apenas encaminhamentos explicitamente propositivos das opiniões.

    O LDS não fornece uma coluna própria de propostas. As opiniões continuam
    sendo preservadas como fonte; este fallback só transforma em proposta uma
    opinião que contém um marcador normativo explícito.
    """
    propostas = []
    for envolvido in envolvidos:
        autor = str(envolvido.get("nome") or "").strip()
        for opiniao in envolvido.get("opinioes") or []:
            texto = " ".join(str(opiniao or "").split())
            texto_normalizado = texto.casefold()
            if not texto or not any(marcador in texto_normalizado for marcador in _MARCADORES_PROPOSTA):
                continue
            frases = re.split(r"(?<=[.!?])\s+", texto)
            titulo = next(
                (
                    frase.strip().strip('"“”')
                    for frase in frases
                    if any(marcador in frase.casefold() for marcador in _MARCADORES_PROPOSTA)
                ),
                texto.split(":", 1)[0].strip(),
            )
            if len(titulo) > 110:
                titulo = f"{titulo[:107].rstrip()}…"
            propostas.append(
                {
                    "id": f"{audiencia_id}-prop-{len(propostas) + 1:02d}",
                    "titulo": titulo,
                    "descricao": texto,
                    "autorNome": autor,
                }
            )
    return propostas


def montar_audiencia(registro: dict, anotada: dict | None = None) -> dict:
    audiencia_id = int(registro["id"])
    if anotada is None:
        anotada = carregar_audiencia_anotada(audiencia_id)
    materia = str(registro.get("materia") or "")
    linhas = _linhas_descritivas(materia)
    metadados = registro.get("metadados") or {}
    envolvidos = metadados.get("envolvidos") or []

    dados_por_nome = {
        str(envolvido.get("nome") or "").strip().casefold(): envolvido
        for envolvido in envolvidos
        if str(envolvido.get("nome") or "").strip()
    }

    participantes = []
    discursos = []
    fontes_participantes = (anotada or {}).get("participantes") or envolvidos
    for participante_numero, envolvido in enumerate(fontes_participantes, start=1):
        participante_id = f"{audiencia_id}-part-{participante_numero:02d}"
        nome = str(envolvido.get("nome") or "")
        envolvido_lds = dados_por_nome.get(nome.strip().casefold(), {})
        cargo = str(envolvido.get("cargo") or envolvido_lds.get("cargo") or "")
        partido = _partido(cargo)
        papel = "presidente" if "presidente" in cargo.casefold() else "participante"
        participantes.append(
            {
                "id": participante_id,
                "nome": nome,
                "partido": partido,
                "papel": cargo or None,
                "tipo": papel,
            }
        )
        falas = envolvido.get("falas")
        if falas is None:
            falas = [
                {
                    "id": f"f{opiniao_numero:05d}",
                    "ordem_no_debate": opiniao_numero,
                    "texto": opiniao,
                    "taxonomia": {},
                    "resumo": str(opiniao),
                    "objeto_do_posicionamento": "",
                    "propostas": [],
                    "interrupcoes": [],
                    "pendencias_revisao": [],
                }
                for opiniao_numero, opiniao in enumerate(envolvido.get("opinioes") or [], start=1)
            ]
        for fala in falas:
            taxonomia = fala.get("taxonomia") or {}
            posicionamentos = taxonomia.get("Posicionamento") or []
            discursos.append(
                {
                    "id": str(fala.get("id") or f"{audiencia_id}-disc-{len(discursos) + 1:02d}"),
                    "participanteId": participante_id,
                    "orador": nome,
                    "partido": partido,
                    "ordem": int(fala.get("ordem_no_debate") or len(discursos) + 1),
                    "posicionamento": posicionamentos[0] if posicionamentos else None,
                    "texto": str(fala.get("texto") or ""),
                    "taxonomia": taxonomia,
                    "resumo": str(fala.get("resumo") or ""),
                    "objeto_do_posicionamento": str(fala.get("objeto_do_posicionamento") or ""),
                    "propostas": fala.get("propostas") or [],
                    "interrupcoes": fala.get("interrupcoes") or [],
                    "pendencias_revisao": fala.get("pendencias_revisao") or [],
                }
            )

    titulo = str(
        (anotada or {}).get("tema")
        or (linhas[0] if linhas else metadados.get("assunto") or f"Audiência {audiencia_id}")
    )
    # A seção "Resumo da audiência" do frontend deve exibir a matéria
    # jornalística original do LDS. As falas, taxonomias e propostas continuam
    # vindo do JSON anotado do MIMO.
    resumo = _corpo_materia(materia) or str((anotada or {}).get("tl_dr") or " ".join(linhas[1:3]) or metadados.get("assunto") or "")
    propostas = []
    propostas_vistas = set()
    for discurso in discursos:
        for proposta_numero, proposta in enumerate(discurso.get("propostas") or [], start=1):
            texto = str(proposta or "").strip()
            if not texto:
                continue
            chave = (discurso["orador"].casefold(), " ".join(texto.casefold().split()))
            if chave in propostas_vistas:
                continue
            propostas_vistas.add(chave)
            propostas.append(
                {
                    "id": f"{audiencia_id}-prop-{len(propostas) + 1:02d}",
                    "titulo": texto,
                    "descricao": texto,
                    "autorNome": discurso["orador"],
                    "autorId": discurso["participanteId"],
                    "falaId": discurso["id"],
                }
            )
    if not anotada:
        propostas = _extrair_propostas(envolvidos, audiencia_id)
    return {
        "id": audiencia_id,
        "ref_id": str(audiencia_id),
        "titulo": titulo,
        "tipo": "audiencia_publica",
        "casa": "Câmara dos Deputados",
        "comissao": None,
        "data": _data_materia(materia),
        "resumo": resumo,
        "materia": materia,
        "transcricao": str(registro.get("transcricao") or ""),
        "integraUrl": None,
        "participantes": participantes,
        "discursos": discursos,
        "posicionamentos": {
            "contra": [],
            "neutros": [],
            "favor": [],
            "ambiguos": [],
        },
        "propostas": propostas,
        "lastModifiedAt": None,
    }


def _garantir_coluna_estrutura(conexao: sqlite3.Connection) -> None:
    colunas = {row[1] for row in conexao.execute("PRAGMA table_info(audiencias)")}
    if "estrutura_json" not in colunas:
        conexao.execute("ALTER TABLE audiencias ADD COLUMN estrutura_json TEXT")


def popular_audiencias(
    caminho_indice: Path = INDICE_PADRAO,
    caminho_dataset: Path = PUBLIC_HEARING_LDS,
) -> int:
    """Importa os registros reais para a tabela estruturada do índice."""
    conexao = sqlite3.connect(caminho_indice)
    try:
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
        _garantir_coluna_estrutura(conexao)
        total = 0
        with caminho_dataset.open(encoding="utf-8") as arquivo:
            for linha in arquivo:
                if not linha.strip():
                    continue
                registro = json.loads(linha)
                estrutura = montar_audiencia(registro)
                metadados = registro.get("metadados") or {}
                conexao.execute(
                    """
                    INSERT INTO audiencias
                        (ref_id, assunto, materia, envolvidos, keywords, estrutura_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ref_id) DO UPDATE SET
                        assunto=excluded.assunto,
                        materia=excluded.materia,
                        envolvidos=excluded.envolvidos,
                        estrutura_json=excluded.estrutura_json
                    """,
                    (
                        str(registro["id"]),
                        metadados.get("assunto"),
                        registro.get("materia"),
                        json.dumps(metadados.get("envolvidos") or [], ensure_ascii=False),
                        json.dumps([], ensure_ascii=False),
                        json.dumps(estrutura, ensure_ascii=False),
                    ),
                )
                total += 1
        conexao.commit()
        return total
    finally:
        conexao.close()


def listar_audiencias(caminho_indice: Path = INDICE_PADRAO) -> list[dict]:
    conexao = sqlite3.connect(caminho_indice)
    try:
        _garantir_coluna_estrutura(conexao)
        rows = conexao.execute(
            "SELECT estrutura_json FROM audiencias WHERE estrutura_json IS NOT NULL ORDER BY CAST(ref_id AS INTEGER)"
        ).fetchall()
        return [json.loads(row[0]) for row in rows]
    finally:
        conexao.close()


def consultar_audiencia(audiencia_id: int | str, caminho_indice: Path = INDICE_PADRAO) -> dict | None:
    """Consulta a estrutura anotada ou o registro real do LDS pelo ID.

    O ``id`` do dataset é o mesmo ``ref_id`` usado pelo índice vetorial e
    pelos chunks de ``documentos``. Quando não há ``estrutura_json`` anotada
    no SQLite, o registro original do LDS é adaptado ao contrato da aplicação.
    """
    try:
        ref_id = str(int(str(audiencia_id).removeprefix("aud-")))
    except (TypeError, ValueError):
        return None

    registro_lds = _carregar_audiencias_lds().get(ref_id)
    registro_anotado = _carregar_audiencias_anotadas().get(ref_id)
    if registro_lds and registro_anotado:
        return montar_audiencia(registro_lds, registro_anotado)
    conexao = sqlite3.connect(caminho_indice)
    try:
        colunas = {row[1] for row in conexao.execute("PRAGMA table_info(audiencias)")}
        if "estrutura_json" in colunas:
            row = conexao.execute(
                "SELECT estrutura_json FROM audiencias WHERE ref_id = ?",
                (ref_id,),
            ).fetchone()
            if row and row[0]:
                return json.loads(row[0])
    finally:
        conexao.close()

    if registro_lds:
        return montar_audiencia(registro_lds, registro_anotado)
    return None


@tool("consultar_audiencia_por_id")
def consultar_audiencia_por_id(audiencia_id: int) -> str:
    """Retorna o debate inteiro pelo ID da audiência, já segmentado e anotado.

    Use depois de localizar a audiência com ``buscar_audiencias``. O retorno traz
    o registro real correspondente ao ``ref_id`` encontrado, incluindo ``materia``
    e a ``transcricao`` original quando a audiência vem do dataset LDS. Ele é
    organizado por participante e, dentro de cada um, pelas suas ``falas`` —
    no LDS, essas falas correspondem às opiniões estruturadas da matéria;
    a transcrição integral fica no campo ``transcricao``.

    Cada fala pode trazer:

    - ``taxonomia``: quatro dimensões, **cada uma com um ou mais valores**.
      ``Alinhamento Temático`` (Focalizado, Periférico, Desalinhado);
      ``Postura do Orador`` (Agressiva, Emocional, Confiante, Técnica);
      ``Credibilidade e Validação`` (Autoridade Própria, Referência Externa,
      Recursos Retóricos); ``Posicionamento`` (Favorável, Contrário, Neutro,
      Ambíguo).
    - ``resumo``: síntese do que foi dito. A parte final repete a classificação
      e o objeto do posicionamento, e não deve ser reaproveitada.
    - ``objeto_do_posicionamento``: sobre o quê a pessoa se posicionou. Duas
      falas ``Favorável`` sobre objetos diferentes não concordam entre si:
      compare o objeto antes de apresentar participantes como concordantes.
    - ``propostas``: o que a pessoa propôs concretamente, quando propôs.
    - ``pendencias_revisao``: ressalvas já registradas sobre aquela fala.
    - ``interrupcoes``: registro de quem cortou a fala; não é usado no material.

    Copie esses campos como estão. Não reclassifique uma fala nem reescreva o
    objeto do posicionamento ou uma proposta.

    Quando uma audiência ainda não tiver sido anotada, os campos de taxonomia
    virão ausentes ou nulos. Nesse caso, trabalhe apenas com o texto das falas e
    diga ao professor que aquele debate ainda não tem a classificação — não
    deduza posicionamento nem preencha o que falta.
    """
    resultado = consultar_audiencia(audiencia_id)
    if resultado is None:
        return json.dumps(
            {"erro": f"Audiência {audiencia_id} não encontrada no índice."},
            ensure_ascii=False,
        )
    return json.dumps(resultado, ensure_ascii=False)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Estrutura audiências reais no índice SQLite")
    parser.add_argument("comando", choices=["popular", "listar", "consultar"])
    parser.add_argument("audiencia_id", nargs="?")
    args = parser.parse_args()
    if args.comando == "popular":
        print(popular_audiencias())
    elif args.comando == "listar":
        print(json.dumps(listar_audiencias(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(consultar_audiencia(args.audiencia_id), ensure_ascii=False, indent=2))
