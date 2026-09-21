"""Carregamento de arquivos locais (deputados, audiências) e normalização de nomes."""

import json
import os
import unicodedata

from .config import DATASETS_PATH, PUBLIC_HEARING_PATH


def carregar_deputados():
    with open(DATASETS_PATH / "deputados.json", "r", encoding="UTF-8") as f:
        return json.load(f)


def normalizar_nome(nome):
    """Normaliza nomes para o cruzamento entre os dois datasets."""
    sem_acentos = unicodedata.normalize("NFKD", nome or "")
    sem_acentos = "".join(c for c in sem_acentos if not unicodedata.combining(c))
    return " ".join(sem_acentos.upper().split())


def carregar_audiencias_publicas():
    """Carrega as transcrições LDS do PublicHearingBR, se disponíveis."""
    caminho = PUBLIC_HEARING_PATH / "PublicHearingBR_LDS.jsonl"
    if not caminho.exists():
        return []
    with open(caminho, "r", encoding="utf-8") as f:
        return [json.loads(linha) for linha in f if linha.strip()]


def salvar_progresso(caminho, dados):
    """
    Salva um checkpoint válido mesmo se o processo for interrompido.

    OBS: não é chamada em nenhum ponto do pipeline atual — o resumo do
    processamento hoje é feito pela tabela `etl_processados` no SQLite
    (ver banco.py / pipeline.py). Mantida aqui caso volte a ser usada
    para checkpoints em JSON; remova se confirmar que está obsoleta.
    """
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    with open(temporario, "w", encoding="UTF-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporario, caminho)
