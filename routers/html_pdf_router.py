import asyncio
import subprocess
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from typing import Literal
from uuid import UUID

from db.pool import get_pool
from db.queries import get_workflow_session
from graph.tools.sandbox.shared.html_pdf_tools import render_html_to_pdf
from graph.tools.sandbox.workdir import workspace_for_chat
from services.workflow_files import persist_workflow_files, restore_workflow_files
from services.html_to_docx import HtmlToDocxError, convert_html_bytes_to_docx


MAX_PDF_HTML_BYTES = 20 * 1024 * 1024

router = APIRouter(prefix="/api/workflow", tags=["html-pdf"])


def _download_name(filename: str, extension: str) -> str:
    stem = Path(filename or "material").stem
    safe_stem = "".join(char if char.isalnum() or char in "-_ ." else "_" for char in stem).strip(" .") or "material"
    return f"{safe_stem}.{extension}"


async def _session_or_404(session_id: str) -> None:
    try:
        session_uuid = UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada") from exc

    pool = get_pool()
    async with pool.acquire() as conn:
        session = await get_workflow_session(conn, session_uuid)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada")
    await restore_workflow_files(session_id)


@router.post("/sessions/{session_id}/pdf")
async def generate_workflow_pdf(
    session_id: str,
    file: UploadFile = File(...),
    orientation: Literal["V", "H"] = Query("V"),
):
    """Converte o HTML enviado pelo frontend em PDF e devolve o arquivo."""
    await _session_or_404(session_id)
    html_content = await file.read(MAX_PDF_HTML_BYTES + 1)
    if len(html_content) > MAX_PDF_HTML_BYTES:
        raise HTTPException(status_code=413, detail="O HTML deve ter no máximo 20 MB")
    if not html_content.strip():
        raise HTTPException(status_code=422, detail="O HTML não pode estar vazio")

    sandbox_dir = workspace_for_chat("10", f"workflow-{session_id}") / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".pdf",
            prefix="workflow-",
            dir=sandbox_dir,
            delete=False,
        ) as pdf_file:
            pdf_path = Path(pdf_file.name)

        await asyncio.to_thread(
            render_html_to_pdf,
            html_content,
            pdf_path,
            orientation,
            sandbox_dir,
        )
        pdf_content = pdf_path.read_bytes()
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="A geração do PDF excedeu o tempo limite") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="O conversor de PDF não está disponível") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        if pdf_path:
            pdf_path.unlink(missing_ok=True)

    await persist_workflow_files(session_id)
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="atividade.pdf"'},
    )


@router.post("/sessions/{session_id}/download")
async def download_workflow_file(
    session_id: str,
    format: Literal["html", "pdf", "docx"] = Query(...),
    filename: str = Query("material"),
    file: UploadFile = File(...),
):
    """Exporta o HTML atual de uma sessão usando o nome real do template."""
    await _session_or_404(session_id)
    html_content = await file.read(MAX_PDF_HTML_BYTES + 1)
    if len(html_content) > MAX_PDF_HTML_BYTES:
        raise HTTPException(status_code=413, detail="O HTML deve ter no máximo 20 MB")
    if not html_content.strip():
        raise HTTPException(status_code=422, detail="O HTML não pode estar vazio")

    if format == "html":
        content = html_content
        media_type = "text/html; charset=utf-8"
    elif format == "docx":
        try:
            content = await asyncio.to_thread(convert_html_bytes_to_docx, html_content, filename)
        except HtmlToDocxError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        with tempfile.TemporaryDirectory(prefix="workflow-download-") as tmpdir:
            pdf_path = Path(tmpdir) / "template.pdf"
            try:
                await asyncio.to_thread(render_html_to_pdf, html_content, pdf_path, "V", tmpdir)
                content = pdf_path.read_bytes()
            except subprocess.TimeoutExpired as exc:
                raise HTTPException(status_code=504, detail="A conversão para PDF excedeu o tempo limite") from exc
            except FileNotFoundError as exc:
                raise HTTPException(status_code=503, detail="O conversor de PDF não está disponível") from exc
            except RuntimeError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
        media_type = "application/pdf"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{_download_name(filename, format)}"'},
    )
