import asyncio
import os
import subprocess
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import Response

from db.memory_store import memory_store
from graph.tools.sandbox.workdir import workspace_for_chat


MAX_PDF_HTML_BYTES = 20 * 1024 * 1024
PDF_PRINT_OVERRIDES = """
<style id="workflow-pdf-overrides">
@page {
  size: A4;
  margin: 0;
}

@media print {
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

router = APIRouter(prefix="/api/workflow", tags=["html-pdf"])


def _session_or_404(session_id: str) -> None:
    try:
        memory_store.snapshot(session_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sessão não encontrada na memória do servidor",
        ) from exc


def _html_for_pdf(html_content: bytes) -> bytes:
    """Adiciona somente ajustes de impressão, preservando o HTML recebido."""
    html = html_content.decode("utf-8", errors="replace")
    head_end = html.lower().find("</head>")
    if head_end < 0:
        return f"{PDF_PRINT_OVERRIDES}{html}".encode("utf-8")
    return f"{html[:head_end]}{PDF_PRINT_OVERRIDES}{html[head_end:]}".encode("utf-8")


@router.post("/sessions/{session_id}/pdf")
async def generate_workflow_pdf(session_id: str, file: UploadFile = File(...)):
    """Converte o HTML enviado pelo frontend em PDF e devolve o arquivo."""
    _session_or_404(session_id)
    html_content = await file.read(MAX_PDF_HTML_BYTES + 1)
    if len(html_content) > MAX_PDF_HTML_BYTES:
        raise HTTPException(status_code=413, detail="O HTML deve ter no máximo 20 MB")
    if not html_content.strip():
        raise HTTPException(status_code=422, detail="O HTML não pode estar vazio")

    sandbox_dir = workspace_for_chat("workflow-demo-user", f"workflow-{session_id}") / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    html_path = None
    pdf_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".html",
            prefix="pdf-source-",
            dir=sandbox_dir,
            delete=False,
        ) as html_file:
            html_file.write(_html_for_pdf(html_content))
            html_path = Path(html_file.name)

        with tempfile.NamedTemporaryFile(suffix=".pdf", prefix="workflow-", delete=False) as pdf_file:
            pdf_path = Path(pdf_file.name)

        # O Chromium precisa de um perfil próprio e gravável mesmo em modo headless.
        with tempfile.TemporaryDirectory(prefix="chromium-profile-", dir=sandbox_dir) as profile_dir:
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
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "chromium",
                    "--headless",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--allow-file-access-from-files",
                    f"--user-data-dir={profile_dir}",
                    f"--print-to-pdf={pdf_path}",
                    str(html_path),
                ],
                capture_output=True,
                env=process_env,
                timeout=120,
                check=False,
            )
        if result.returncode != 0 or not pdf_path.is_file() or pdf_path.stat().st_size == 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise HTTPException(status_code=502, detail=detail or "Não foi possível gerar o PDF")

        pdf_content = pdf_path.read_bytes()
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="A geração do PDF excedeu o tempo limite") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="O conversor de PDF não está disponível") from exc
    finally:
        if html_path:
            html_path.unlink(missing_ok=True)
        if pdf_path:
            pdf_path.unlink(missing_ok=True)

    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="atividade.pdf"'},
    )