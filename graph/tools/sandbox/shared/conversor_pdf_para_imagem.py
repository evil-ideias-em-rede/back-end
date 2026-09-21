"""
Conversão de páginas de PDF em imagens.

Cada chamada gera uma pasta de saída nomeada como:
   <nome_do_arquivo>_imagens_<dd-mm-aaaa_HHhMMmSSs>

Exemplo: relatorio_imagens_15-09-2026_14h32m07s
"""

import os
from datetime import datetime

import pymupdf


def converter_pdf_para_imagens(caminho_pdf, dpi=150, formato="png", dir_pai=None):
    """
    Converte cada página de um PDF em um arquivo de imagem separado.

    Parâmetros:
        caminho_pdf (str): caminho do arquivo PDF de entrada.
        dpi (int): resolução da rasterização (padrão 150).
        formato (str): "png" ou "jpg"/"jpeg".
        dir_pai (str|None): pasta onde a pasta de saída será criada.
            Se None, usa a mesma pasta do PDF de entrada.

    Retorna:
        str: caminho completo da pasta criada com as imagens.
    """
    if not os.path.isfile(caminho_pdf):
        raise FileNotFoundError(f"PDF não encontrado: {caminho_pdf}")

    formato = formato.lower().lstrip(".")
    if formato not in ("png", "jpg", "jpeg"):
        raise ValueError("formato deve ser 'png', 'jpg' ou 'jpeg'")

    nome_base = os.path.splitext(os.path.basename(caminho_pdf))[0]
    horario = datetime.now().strftime("%d-%m-%Y_%Hh%Mm%Ss")
    nome_dir = f"{nome_base}_imagens_{horario}"

    pasta_base = dir_pai or os.path.dirname(os.path.abspath(caminho_pdf))
    dir_saida = os.path.join(pasta_base, nome_dir)
    os.makedirs(dir_saida, exist_ok=True)

    doc = pymupdf.open(caminho_pdf)
    zoom = dpi / 72
    matriz = pymupdf.Matrix(zoom, zoom)

    total_paginas = len(doc)
    largura_num = len(str(total_paginas))

    caminhos_gerados = []
    for i, pagina in enumerate(doc, start=1):
        pix = pagina.get_pixmap(matrix=matriz)
        nome_arquivo = f"pagina_{str(i).zfill(largura_num)}.{formato}"
        caminho_imagem = os.path.join(dir_saida, nome_arquivo)
        pix.save(caminho_imagem)
        caminhos_gerados.append(caminho_imagem)

    doc.close()

    print(f"{total_paginas} página(s) convertida(s) -> {dir_saida}")
    return dir_saida


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Converte páginas de um PDF em imagens.")
    parser.add_argument("pdf", help="Caminho do arquivo PDF")
    parser.add_argument("--dpi", type=int, default=150, help="Resolução (padrão: 150)")
    parser.add_argument("--formato", default="png", help="png ou jpg (padrão: png)")
    args = parser.parse_args()

    converter_pdf_para_imagens(args.pdf, dpi=args.dpi, formato=args.formato)