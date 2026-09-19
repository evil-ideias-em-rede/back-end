"""
Sorteia uma amostra de audiências de `PublicHearingBR_LDS.jsonl` e grava um
resumo legível em texto, pra escolher candidatas ao gabarito manual sem
precisar abrir o jsonl bruto (linhas de ~25-60KB cada, com `transcricao`
inteira).

Pra cada audiência sorteada, mostra `assunto`, os nomes dos `envolvidos` e um
trecho da `materia` (o resumo jornalístico da audiência) — o suficiente pra
decidir se dá uma pergunta boa antes de ir atrás da transcrição completa.

Uso:
    python gerar_candidatos_audiencias.py -n 15
    python gerar_candidatos_audiencias.py -n 15 --seed 7
"""

import json
import random
import textwrap
from pathlib import Path

RAIZ_RETRIEVAL = Path(__file__).resolve().parent.parent
LDS_PADRAO = RAIZ_RETRIEVAL / "public_hearing" / "PublicHearingBR_LDS.jsonl"
SAIDA_PADRAO = Path(__file__).resolve().parent / "gabaritos" / "candidatos_audiencias_manual.txt"

TRECHO_MATERIA_CHARS = 500


def carregar_audiencias(caminho: Path = LDS_PADRAO) -> list[dict]:
    audiencias = []
    with caminho.open(encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if linha:
                audiencias.append(json.loads(linha))
    return audiencias


def _formatar_candidato(audiencia: dict) -> str:
    id_ = audiencia["id"]
    metadados = audiencia.get("metadados") or {}
    assunto = metadados.get("assunto") or "(sem assunto registrado)"
    envolvidos = [e.get("nome", "?") for e in metadados.get("envolvidos") or []]
    materia = (audiencia.get("materia") or "").strip()
    trecho = materia[:TRECHO_MATERIA_CHARS]
    if len(materia) > TRECHO_MATERIA_CHARS:
        trecho += "..."
    trecho = textwrap.fill(trecho, width=88, initial_indent="  ", subsequent_indent="  ")

    linhas = [
        f"=== audiência {id_} ===",
        f"assunto: {assunto}",
        f"envolvidos: {', '.join(envolvidos) if envolvidos else '(nenhum registrado)'}",
        f"tamanho da matéria: {len(materia)} caracteres | transcrição: {len(audiencia.get('transcricao') or '')} caracteres",
        "trecho da matéria:",
        trecho,
    ]
    return "\n".join(linhas)


def gerar_candidatos(
    n: int, seed: int | None, caminho_lds: Path = LDS_PADRAO
) -> tuple[list[dict], int]:
    audiencias = carregar_audiencias(caminho_lds)
    rng = random.Random(seed)
    amostra = rng.sample(audiencias, min(n, len(audiencias)))
    amostra.sort(key=lambda a: a["id"])
    return amostra, len(audiencias)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Sorteia audiências candidatas ao gabarito manual"
    )
    parser.add_argument("-n", type=int, default=15, help="quantas audiências sortear")
    parser.add_argument(
        "--seed", type=int, default=None, help="fixar a semente pra reproduzir a mesma amostra"
    )
    parser.add_argument("--saida", default=str(SAIDA_PADRAO))
    parser.add_argument("--lds", default=str(LDS_PADRAO))
    args = parser.parse_args()

    amostra, total = gerar_candidatos(args.n, args.seed, Path(args.lds))

    caminho_saida = Path(args.saida)
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    with caminho_saida.open("w", encoding="utf-8") as arquivo:
        arquivo.write(f"{len(amostra)} de {total} audiências sorteadas (seed={args.seed})\n\n")
        arquivo.write("\n\n".join(_formatar_candidato(a) for a in amostra))
        arquivo.write("\n")

    print(f"{len(amostra)} candidatas gravadas em {caminho_saida}")
