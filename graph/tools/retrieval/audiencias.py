"""Leitura estruturada de audiências a partir do índice SQLite.

O índice guarda a transcrição em ``documentos`` e os metadados estruturados
em ``audiencias``. A saída mantém as mesmas chaves consumidas pelo frontend
antigo, mas os dados vêm do dataset real de audiências públicas.
"""

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool


BASE_DIR = Path(__file__).resolve().parent
INDICE_PADRAO = BASE_DIR / "indice" / "indice_busca.sqlite"
PUBLIC_HEARING_LDS = BASE_DIR / "public_hearing" / "PublicHearingBR_LDS.jsonl"
DEBATE_MIMO_FIXO = (
    BASE_DIR
    / "dados_camara"
    / "resultados_mimo_corpus"
    / "debate_linha_00001_11853884c09e_anotado.json"
)


def carregar_debate_mimo() -> dict:
    """Adapta temporariamente o debate anotado fixo ao contrato da tela."""
    bruto = json.loads(DEBATE_MIMO_FIXO.read_text(encoding="utf-8"))
    debate_id = str(bruto.get("debate_id", "1"))
    participantes = []
    discursos = []
    propostas = []

    for participante_numero, participante in enumerate(bruto.get("participantes", []), start=1):
        participante_id = f"mimo-{debate_id}-part-{participante_numero:02d}"
        nome = str(participante.get("nome") or "")
        participantes.append(
            {
                "id": participante_id,
                "nome": nome,
                "partido": None,
                "papel": "participante",
            }
        )
        for fala_numero, fala in enumerate(participante.get("falas", []), start=1):
            taxonomia = fala.get("taxonomia") if isinstance(fala.get("taxonomia"), dict) else {}
            posicionamentos = taxonomia.get("Posicionamento") or []
            posicionamento = posicionamentos[0] if posicionamentos else None
            fala_id = str(fala.get("id") or f"{participante_id}-fala-{fala_numero}")
            discursos.append(
                {
                    "id": fala_id,
                    "participanteId": participante_id,
                    "orador": nome,
                    "ordem": fala.get("ordem_no_debate", len(discursos) + 1),
                    "texto": str(fala.get("texto") or ""),
                    "resumo": str(fala.get("resumo") or ""),
                    "posicionamento": posicionamento,
                    "objeto_do_posicionamento": str(fala.get("objeto_do_posicionamento") or ""),
                    "taxonomia": taxonomia,
                }
            )
            for proposta_numero, proposta in enumerate(fala.get("propostas") or [], start=1):
                propostas.append(
                    {
                        "id": f"{fala_id}-proposta-{proposta_numero}",
                        "titulo": "Proposta identificada",
                        "descricao": str(proposta),
                        "autorId": participante_id,
                        "autorNome": nome,
                    }
                )

    resumo = (
        "Debate anotado sobre denúncias de censura e bloqueio de contas na rede social X, "
        "com falas, taxonomias e propostas identificadas por participante."
    )
    return {
        "id": f"mimo-{debate_id}",
        "titulo": str(bruto.get("tema") or "Debate anotado"),
        "tipo": "debate_anotado",
        "casa": "Câmara dos Deputados",
        "resumo": resumo,
        "participantes": participantes,
        "discursos": discursos,
        "posicionamentos": {"contra": [], "neutro": [], "favor": [], "ambiguo": []},
        "propostas": propostas,
        "status": bruto.get("status"),
    }


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


def _partido(cargo: str) -> str | None:
    """Extrai o partido quando o cargo contém o padrão Partido-UF."""
    encontrado = re.search(r"\(([^()]+)-[A-Za-z]{2}\)", cargo or "")
    if not encontrado:
        return None
    return encontrado.group(1).strip().upper()


def montar_audiencia(registro: dict) -> dict:
    audiencia_id = int(registro["id"])
    materia = str(registro.get("materia") or "")
    linhas = _linhas_descritivas(materia)
    metadados = registro.get("metadados") or {}
    envolvidos = metadados.get("envolvidos") or []

    participantes = []
    discursos = []
    for participante_numero, envolvido in enumerate(envolvidos, start=1):
        participante_id = f"{audiencia_id}-part-{participante_numero:02d}"
        nome = str(envolvido.get("nome") or "")
        cargo = str(envolvido.get("cargo") or "")
        partido = _partido(cargo)
        participantes.append(
            {
                "id": participante_id,
                "nome": nome,
                "partido": partido,
                "papel": cargo or None,
            }
        )
        for opiniao_numero, opiniao in enumerate(envolvido.get("opinioes") or [], start=1):
            discursos.append(
                {
                    "id": f"{audiencia_id}-disc-{len(discursos) + 1:02d}",
                    "participanteId": participante_id,
                    "orador": nome,
                    "partido": partido,
                    "ordem": len(discursos) + 1,
                    "posicionamento": None,
                    "texto": str(opiniao),
                }
            )

    titulo = linhas[0] if linhas else str(metadados.get("assunto") or f"Audiência {audiencia_id}")
    resumo = " ".join(linhas[1:3]) or str(metadados.get("assunto") or "")
    return {
        "id": audiencia_id,
        "titulo": titulo,
        "tipo": "audiencia_publica",
        "casa": "Câmara dos Deputados",
        "comissao": None,
        "data": _data_materia(materia),
        "resumo": resumo,
        "integraUrl": None,
        "participantes": participantes,
        "discursos": discursos,
        "posicionamentos": {
            "contra": [],
            "neutros": [],
            "favor": [],
            "ambiguos": [],
        },
        "propostas": [],
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
    # Temporário: qualquer item clicado na tela abre o mesmo debate anotado.
    if DEBATE_MIMO_FIXO.is_file():
        return carregar_debate_mimo()
    try:
        ref_id = str(int(str(audiencia_id).removeprefix("aud-")))
    except (TypeError, ValueError):
        return None

    conexao = sqlite3.connect(caminho_indice)
    try:
        _garantir_coluna_estrutura(conexao)
        row = conexao.execute(
            "SELECT estrutura_json FROM audiencias WHERE ref_id = ?",
            (ref_id,),
        ).fetchone()
        return json.loads(row[0]) if row and row[0] else None
    finally:
        conexao.close()


@tool("consultar_audiencia_por_id")
def consultar_audiencia_por_id(audiencia_id: int) -> str:
    """Retorna o debate inteiro pelo ID da audiência, já segmentado e anotado.

    Use depois de localizar a audiência com ``buscar_audiencias``. O retorno traz
    o debate completo, organizado por participante e, dentro de cada um, pelas
    suas ``falas`` — uma fala é tudo o que a pessoa disse até passar a palavra.

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
