"""Conversão de HTML para PDF usada pelo endpoint e pelos agentes.

O arquivo também funciona dentro do sandbox:

    python3 html_pdf_tools.py HTML.html HTML.pdf --orientation V

Manter esta implementação compartilhada evita que o PDF validado pelo agente
fique diferente do PDF baixado pelo botão Exportar do frontend.
"""

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Literal


PDF_PRINT_OVERRIDES = """
<style id="workflow-pdf-overrides">
@page {
  size: A4;
  margin: 0;
}

@media print {
  /* Cada marcador representa uma folha física do documento. */
  body > [data-ied-page] {
    break-after: page;
    page-break-after: always;
  }
  body > [data-ied-page]:last-child {
    break-after: auto;
    page-break-after: auto;
  }

  .pagina > .nota { display: none !important; }

  /* A seção pode continuar em outra página; seus elementos atômicos não. */
  h1, h2, h3, h4 {
    break-after: avoid-page;
    page-break-after: avoid;
  }
  table tr, li, figure, .card, .callout, .timeline-item, .bloco,
  .atividade, .pergunta, .destaque {
    break-inside: avoid;
    page-break-inside: avoid;
  }
}
</style>
"""


def html_for_pdf(html_content: bytes, orientation: Literal["V", "H"] = "V") -> bytes:
    """Adiciona os mesmos ajustes de impressão usados pelo exportador."""
    if orientation not in {"V", "H"}:
        raise ValueError("orientation deve ser 'V' ou 'H'")

    html = html_content.decode("utf-8", errors="replace")
    page_size = "A4 landscape" if orientation == "H" else "A4"
    overrides = PDF_PRINT_OVERRIDES.replace("size: A4;", f"size: {page_size};")
    head_end = html.lower().find("</head>")
    if head_end < 0:
        return f"{overrides}{html}".encode("utf-8")
    return f"{html[:head_end]}{overrides}{html[head_end:]}".encode("utf-8")


def _find_browser() -> str:
    browser = next(
        (
            executable
            for executable in ("chromium", "chromium-browser", "google-chrome")
            if shutil.which(executable)
        ),
        None,
    )
    if browser is None:
        raise FileNotFoundError("Nenhum navegador compatível foi encontrado")
    return browser


def render_html_to_pdf(
    html_content: bytes,
    output_pdf: str | os.PathLike[str],
    orientation: Literal["V", "H"] = "V",
    work_dir: str | os.PathLike[str] | None = None,
) -> Path:
    """Renderiza HTML com Chromium usando exatamente o fluxo de exportação."""
    output_path = Path(output_pdf).resolve()
    temporary_dir = Path(work_dir or output_path.parent).resolve()
    temporary_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    html_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".html",
            prefix="pdf-source-",
            dir=temporary_dir,
            delete=False,
        ) as html_file:
            html_file.write(html_for_pdf(html_content, orientation))
            html_path = Path(html_file.name)

        with tempfile.TemporaryDirectory(prefix="chromium-profile-", dir=temporary_dir) as profile_dir:
            profile_path = Path(profile_dir)
            config_dir = profile_path / "config"
            cache_dir = profile_path / "cache"
            config_dir.mkdir()
            cache_dir.mkdir()
            process_env = os.environ.copy()
            process_env.update(
                {
                    "XDG_CONFIG_HOME": str(config_dir),
                    "XDG_CACHE_HOME": str(cache_dir),
                }
            )
            result = subprocess.run(
                [
                    _find_browser(),
                    "--headless",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--allow-file-access-from-files",
                    f"--user-data-dir={profile_path}",
                    f"--print-to-pdf={output_path}",
                    str(html_path),
                ],
                capture_output=True,
                env=process_env,
                timeout=120,
                check=False,
            )

        if result.returncode != 0 or not output_path.is_file() or output_path.stat().st_size == 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(detail or "Não foi possível gerar o PDF")
        return output_path
    finally:
        if html_path:
            html_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Renderiza um HTML usando o exportador A4 do workflow.")
    parser.add_argument("html", help="HTML de entrada, normalmente HTML.html")
    parser.add_argument("pdf", help="PDF de saída")
    parser.add_argument("--orientation", choices=("V", "H"), default="V")
    args = parser.parse_args()

    render_html_to_pdf(
        Path(args.html).read_bytes(),
        args.pdf,
        orientation=args.orientation,
        work_dir=Path.cwd(),
    )
    print(f"PDF gerado: {args.pdf}")


if __name__ == "__main__":
    main()
