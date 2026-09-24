#!/usr/bin/env python3
"""
pdf_to_html.py — Conversão fiel de PDF para HTML autocontido, em folhas A4.

Como funciona:
  1. Usa o `pdftohtml` (poppler-utils) em modo "complex" para gerar, para
     cada página, uma imagem de fundo (vetores/diagramas rasterizados) com
     o texto real sobreposto em posições absolutas (continua selecionável
     e pesquisável).
  2. `-dataurls` embute essas imagens como base64 direto no HTML, então o
     resultado fica em UM único arquivo, sem pastas de imagens soltas.
  3. Cada página do PDF é encaixada em folhas A4 EXATAS (210mm x 297mm):
       - a página é escalada para ocupar exatamente a largura do A4;
       - se, depois de escalada, ela couber na altura do A4, vira 1 folha;
       - se for mais alta que o A4, o conteúdo continua em novas folhas A4
         (a imagem de fundo é "fatiada" via CSS e cada texto vai para a
         folha onde ele cai, com a posição recalculada).
     A imagem de fundo de cada página é declarada UMA vez no CSS, mesmo
     que a página ocupe várias folhas (o arquivo não incha).
  4. O documento gerado NÃO tem scroll próprio (overflow: hidden em
     html/body). Ele foi pensado para ser exibido dentro de uma página que
     já tem scroll (ex.: num <iframe>). Para o iframe poder ter a altura
     exata do conteúdo, o HTML envia a sua altura para a página pai via
     postMessage (desative com --sem-script).

Requisitos de sistema:
  - poppler-utils instalado (fornece o binário `pdftohtml`).
    Ubuntu/Debian: sudo apt-get install poppler-utils
    macOS (Homebrew): brew install poppler

Uso:
  python3 pdf_to_html.py entrada.pdf saida.html
  python3 pdf_to_html.py entrada.pdf saida.html --zoom 2.5
  python3 pdf_to_html.py entrada.pdf saida.html --espaco 0 --sem-script
"""

import argparse
import html
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class PdfConversionError(RuntimeError):
    """Indica que o PDF não pôde ser convertido pelo Poppler."""


# ---------------------------------------------------------------------------
# Dimensões A4. CSS define 1in = 96px e 1in = 25.4mm (valores exatos).
# ---------------------------------------------------------------------------
A4_LARGURA_MM = 210.0
A4_ALTURA_MM = 297.0
PX_POR_MM = 96.0 / 25.4
A4_LARGURA_PX = A4_LARGURA_MM * PX_POR_MM  # ~793.70px
A4_ALTURA_PX = A4_ALTURA_MM * PX_POR_MM    # ~1122.52px

# Tolerância para não criar uma folha extra quase vazia por causa de
# arredondamento (ex.: página A4 que o poppler gera com 1px a mais).
TOLERANCIA_QUEBRA = 0.01  # 1% da altura de uma folha

RE_PAGINA = re.compile(
    r'<div id="page(\d+)-div" style="[^"]*?width:(\d+(?:\.\d+)?)px;height:(\d+(?:\.\d+)?)px;[^"]*">'
    r"(.*)</div>",
    re.S,
)
RE_IMG_FUNDO = re.compile(r"<img\b[^>]*?src=\"(data:[^\"]+)\"[^>]*/?>", re.S)
RE_PARAGRAFO = re.compile(r"<p\b[^>]*>.*?</p>", re.S)
RE_TOP = re.compile(r"top:(-?\d+(?:\.\d+)?)px")


def _fmt(valor: float) -> str:
    """Formata números para CSS sem casas decimais inúteis."""
    return f"{valor:.6f}".rstrip("0").rstrip(".")


def _extrair_paginas(raw_html: str):
    """Retorna (estilos, paginas) a partir da saída concatenada do poppler."""
    docs = re.findall(r"<html[^>]*>.*?</html>", raw_html, re.S)
    if not docs:
        sys.exit("Erro: não foi possível interpretar a saída do pdftohtml.")

    estilos, paginas = [], []
    for doc in docs:
        # Só os <style> interessam do <head> (o poppler também coloca
        # <title>, <meta> e até um <br/> ali, que não devem ir pro final).
        estilos.extend(re.findall(r"<style[^>]*>.*?</style>", doc, re.S))

        m = RE_PAGINA.search(doc)
        if not m:
            continue
        num, largura, altura, miolo = m.groups()

        img = RE_IMG_FUNDO.search(miolo)
        fundo = img.group(1) if img else None
        if img:
            miolo = miolo[: img.start()] + miolo[img.end():]

        textos = []
        for p in RE_PARAGRAFO.finditer(miolo):
            t = RE_TOP.search(p.group(0))
            textos.append((float(t.group(1)) if t else 0.0, p.group(0)))
        resto = RE_PARAGRAFO.sub("", miolo).strip()

        paginas.append({
            "num": int(num),
            "largura": float(largura),
            "altura": float(altura),
            "fundo": fundo,
            "textos": textos,
            "resto": resto,
        })

    if not paginas:
        sys.exit("Erro: nenhuma página encontrada na saída do pdftohtml.")
    return estilos, paginas


def _montar_folhas(pagina: dict):
    """Distribui uma página do PDF em uma ou mais folhas A4.

    Retorna (css_da_pagina, lista_de_html_das_folhas).
    """
    n = pagina["num"]
    largura, altura = pagina["largura"], pagina["altura"]

    # Escala que faz a largura da página bater exatamente com a do A4.
    escala = A4_LARGURA_PX / largura
    # Altura de uma folha A4 medida no sistema de coordenadas da página.
    altura_fatia = A4_ALTURA_PX / escala

    qtd_folhas = max(1, math.ceil((altura - altura_fatia * TOLERANCIA_QUEBRA) / altura_fatia))

    css = (
        f".pg{n}-conteudo{{width:{_fmt(largura)}px;height:{_fmt(altura_fatia)}px;"
        f"transform:scale({_fmt(escala)});}}\n"
    )
    if pagina["fundo"]:
        css += (
            f".pg{n}-fundo{{background-image:url(\"{pagina['fundo']}\");"
            f"background-size:{_fmt(largura)}px {_fmt(altura)}px;}}\n"
        )

    # Separa os textos por folha, de acordo com a coordenada "top".
    textos_por_folha = [[] for _ in range(qtd_folhas)]
    for top, p_html in pagina["textos"]:
        idx = min(qtd_folhas - 1, max(0, int(top // altura_fatia)))
        deslocamento = idx * altura_fatia
        if deslocamento:
            p_html = RE_TOP.sub(f"top:{_fmt(top - deslocamento)}px", p_html, count=1)
        textos_por_folha[idx].append(p_html)

    folhas = []
    for i in range(qtd_folhas):
        deslocamento = i * altura_fatia
        classes = f"folha-conteudo pg{n}-conteudo"
        estilo = ""
        if pagina["fundo"]:
            classes += f" pg{n}-fundo"
            estilo = f' style="background-position:0 {_fmt(-deslocamento)}px"'

        miolo = "\n".join(textos_por_folha[i])
        if i == 0 and pagina["resto"]:
            miolo = pagina["resto"] + "\n" + miolo

        folhas.append(
            f'<section class="folha" data-pagina-pdf="{n}" data-parte="{i + 1}/{qtd_folhas}">\n'
            f'<div class="{classes}"{estilo}>\n{miolo}\n</div>\n'
            f"</section>"
        )
    return css, folhas


SCRIPT_ALTURA = """<script>
(function () {
  // Informa à página pai (quando este HTML está dentro de um <iframe>)
  // a altura total do documento, para o iframe crescer sem scroll interno.
  function enviarAltura() {
    var doc = document.querySelector('.documento');
    var altura = Math.ceil(doc ? doc.getBoundingClientRect().height : document.documentElement.scrollHeight);
    if (window.parent && window.parent !== window) {
      window.parent.postMessage({ tipo: 'pdf-html-altura', altura: altura }, '*');
    }
  }
  window.addEventListener('load', enviarAltura);
  window.addEventListener('resize', enviarAltura);
  enviarAltura();
})();
</script>"""


def converter_pdf_para_html(
    pdf_path: Path,
    html_path: Path,
    zoom: float = 2.0,
    espaco_px: int = 20,
    com_script: bool = True,
    titulo: str | None = None,
) -> None:
    if shutil.which("pdftohtml") is None:
        sys.exit(
            "Erro: o binário 'pdftohtml' não foi encontrado no PATH.\n"
            "Instale o poppler-utils (ex.: 'sudo apt-get install poppler-utils' "
            "ou 'brew install poppler')."
        )

    if not pdf_path.is_file():
        sys.exit(f"Erro: arquivo não encontrado: {pdf_path}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_base = Path(tmpdir) / "doc"

        # -c          modo "complex": fundo rasterizado + texto real sobreposto (fidelidade visual)
        # -s          gera um único arquivo com todas as páginas
        # -dataurls   embute as imagens como base64 (arquivo final autocontido)
        # -zoom       fator de escala do raster de fundo (nitidez); default do poppler é 1.5
        cmd = [
            "pdftohtml",
            "-c",
            "-s",
            "-dataurls",
            "-zoom", str(zoom),
            str(pdf_path),
            str(tmp_base),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            sys.exit(f"Erro ao rodar pdftohtml:\n{result.stderr}")

        raw_html_path = tmp_base.with_name(tmp_base.name + "-html.html")
        if not raw_html_path.exists():
            sys.exit(f"Erro: saída esperada não encontrada em {raw_html_path}")

        raw_html = raw_html_path.read_text(encoding="utf-8")

    estilos, paginas = _extrair_paginas(raw_html)

    css_paginas, todas_folhas = [], []
    for pagina in paginas:
        css, folhas = _montar_folhas(pagina)
        css_paginas.append(css)
        todas_folhas.extend(folhas)

    titulo = html.escape(titulo or pdf_path.stem, quote=True)
    espaco = max(0, int(espaco_px))

    final_html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titulo}</title>
{''.join(estilos)}
<style>
  /* Sem scroll: quem rola é a página que hospeda este HTML. */
  html, body {{
    margin: 0;
    padding: 0;
    overflow: hidden;   /* sem barra de rolagem e sem rolagem pelo usuário */
    background: #E5E5E5;
  }}
  .documento {{
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: {espaco}px;
    padding: {espaco}px 0;
    width: max-content;
    min-width: 100%;
    box-sizing: border-box;
  }}
  /* Folha A4 exata: nada cresce nem vaza para fora dela. */
  .folha {{
    position: relative;
    flex: none;
    width: {_fmt(A4_LARGURA_MM)}mm;
    height: {_fmt(A4_ALTURA_MM)}mm;
    min-width: {_fmt(A4_LARGURA_MM)}mm;
    min-height: {_fmt(A4_ALTURA_MM)}mm;
    max-width: {_fmt(A4_LARGURA_MM)}mm;
    max-height: {_fmt(A4_ALTURA_MM)}mm;
    overflow: hidden;
    background: #fff;
    box-shadow: 0 2px 10px rgba(0,0,0,.35);
  }}
  .folha-conteudo {{
    position: absolute;
    top: 0;
    left: 0;
    overflow: hidden;
    transform-origin: 0 0;
    background-repeat: no-repeat;
  }}
{''.join(css_paginas)}
  /* Impressão também em A4, uma folha por página. */
  @page {{ size: A4; margin: 0; }}
  @media print {{
    html, body {{ background: #fff; }}
    .documento {{ display: block; padding: 0; width: auto; }}
    .folha {{ box-shadow: none; break-after: page; page-break-after: always; }}
    .folha:last-child {{ break-after: auto; page-break-after: auto; }}
    .folha-conteudo {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  }}
</style>
</head>
<body>
<main class="documento">
{chr(10).join(todas_folhas)}
</main>
{SCRIPT_ALTURA if com_script else ''}
</body>
</html>
"""

    html_path.write_text(final_html, encoding="utf-8")
    print(
        f"OK: {len(paginas)} página(s) do PDF -> {len(todas_folhas)} folha(s) A4 -> {html_path}"
    )



def convert_pdf_bytes_to_html(
    content: bytes,
    title: str = "Documento convertido",
    zoom: float = 2.0,
) -> bytes:
    """Converte bytes de PDF em HTML A4 autocontido para o backend."""
    with tempfile.TemporaryDirectory(prefix="pdf-to-html-") as tmpdir:
        tmpdir_path = Path(tmpdir)
        pdf_path = tmpdir_path / "input.pdf"
        html_path = tmpdir_path / "output.html"
        pdf_path.write_bytes(content)
        try:
            converter_pdf_para_html(
                pdf_path,
                html_path,
                zoom=zoom,
                espaco_px=20,
                com_script=True,
                titulo=title,
            )
        except SystemExit as exc:
            raise PdfConversionError(str(exc)) from exc
        if not html_path.is_file():
            raise PdfConversionError("O conversor não gerou o arquivo HTML")
        return html_path.read_bytes()

def main():
    parser = argparse.ArgumentParser(
        description="Converte um PDF em HTML fiel e autocontido, em folhas A4."
    )
    parser.add_argument("pdf", type=Path, help="Caminho do arquivo PDF de entrada")
    parser.add_argument("html", type=Path, help="Caminho do arquivo HTML de saída")
    parser.add_argument(
        "--zoom", type=float, default=2.0,
        help="Fator de escala do raster de fundo (padrão: 2.0). Aumente para mais nitidez."
    )
    parser.add_argument(
        "--espaco", type=int, default=20,
        help="Espaço em px entre as folhas e nas bordas do documento (padrão: 20)."
    )
    parser.add_argument(
        "--sem-script", action="store_true",
        help="Não incluir o script que envia a altura do documento à página pai (iframe)."
    )
    args = parser.parse_args()
    converter_pdf_para_html(
        args.pdf, args.html, args.zoom, args.espaco, com_script=not args.sem_script
    )


if __name__ == "__main__":
    main()