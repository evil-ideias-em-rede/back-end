import asyncio
import html
import re
import subprocess
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from auth.workflow_access import require_workflow_access
from fastapi.responses import Response
from typing import Literal
from uuid import UUID

from db.pool import get_pool
from db.queries import get_workflow_session
from graph.tools.sandbox.shared.html_pdf_tools import render_html_to_pdf
from graph.tools.sandbox.shared.html_page_contract import PaginationError
from graph.tools.sandbox.workdir import workspace_for_chat
from services.html_to_docx import HtmlToDocxError, convert_paginated_html_bytes_to_docx
from services.html_to_pptx import HtmlToPptxError, convert_html_bytes_to_pptx
from services.workflow_files import persist_workflow_files, restore_workflow_files


MAX_PDF_HTML_BYTES = 20 * 1024 * 1024
PPTX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

router = APIRouter(prefix="/api/workflow", tags=["html-pdf"], dependencies=[Depends(require_workflow_access)])


def _safe_download_name(value: str, extension: str) -> str:
    stem = Path(Path(value.strip() or "material").name).stem
    stem = re.sub(r"\s+", "_", stem)
    stem = re.sub(r"[^A-Za-z0-9_.-]", "_", stem).strip("._") or "material"
    return f"{stem}.{extension}"


async def _session_or_404(session_id: str, restore_files: bool = True) -> None:
    try:
        session_uuid = UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada") from exc

    pool = get_pool()
    async with pool.acquire() as conn:
        session = await get_workflow_session(conn, session_uuid)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada")
    if restore_files:
        await restore_workflow_files(session_id)


@router.post("/sessions/{session_id}/pdf")
async def generate_workflow_pdf(
    session_id: str,
    file: UploadFile = File(...),
    orientation: Literal["V", "H"] = Query("V"),
):
    """Converte o HTML enviado pelo frontend em PDF e devolve o arquivo."""
    return await download_workflow_file(
        session_id=session_id, file=file, format="pdf", filename="atividade", orientation=orientation,
    )


@router.post("/sessions/{session_id}/download")
async def download_workflow_file(
    session_id: str,
    file: UploadFile = File(...),
    format: Literal["html", "pdf", "docx"] = Query(...),
    filename: str = Query("material"),
    orientation: Literal["V", "H"] = Query("V"),
):
    """Baixa a versão atualmente aberta no editor nos formatos suportados."""
    # A exportação usa o upload atual; não restaura nem sobrescreve os
    # arquivos da sessão enquanto o autosave ou o agente pode estar ativo.
    await _session_or_404(session_id, restore_files=False)
    html_content = await file.read(MAX_PDF_HTML_BYTES + 1)
    if len(html_content) > MAX_PDF_HTML_BYTES:
        raise HTTPException(status_code=413, detail="O HTML deve ter no máximo 20 MB")
    if not html_content.strip():
        raise HTTPException(status_code=422, detail="O HTML não pode estar vazio")

    try:
        if format == "html":
            source = html_content.decode("utf-8", errors="replace")
            if not re.search(r"<html\b", source, re.I):
                source = ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
                          f'<title>{html.escape(filename)}</title></head><body>{source}</body></html>')
            content = source.encode("utf-8")
            media_type = "text/html; charset=utf-8"
        elif format == "pdf":
            with tempfile.TemporaryDirectory(prefix="workflow-download-") as directory:
                pdf_path = Path(directory) / "material.pdf"
                await asyncio.to_thread(
                    render_html_to_pdf,
                    html_content,
                    pdf_path,
                    orientation,
                    directory,
                    fit_overflow=True,
                )
                content = pdf_path.read_bytes()
            media_type = "application/pdf"
        else:
            content = await asyncio.to_thread(
                convert_paginated_html_bytes_to_docx,
                html_content,
                filename,
                orientation,
            )
            media_type = DOCX_MEDIA_TYPE
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="A geração do arquivo excedeu o tempo limite") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="O conversor não está disponível") from exc
    except PaginationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (HtmlToDocxError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    download_name = _safe_download_name(filename, format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )


@router.post("/sessions/{session_id}/pptx")
async def generate_workflow_pptx(
    session_id: str,
    file: UploadFile = File(...),
):
    """Converte o HTML horizontal em PPTX, com uma página por slide."""
    await _session_or_404(session_id)
    html_content = await file.read(MAX_PDF_HTML_BYTES + 1)
    if len(html_content) > MAX_PDF_HTML_BYTES:
        raise HTTPException(status_code=413, detail="O HTML deve ter no máximo 20 MB")
    if not html_content.strip():
        raise HTTPException(status_code=422, detail="O HTML não pode estar vazio")

    sandbox_dir = workspace_for_chat("10", f"workflow-{session_id}") / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    try:
        pptx_content = await asyncio.to_thread(
            convert_html_bytes_to_pptx,
            html_content,
            "apresentacao",
            sandbox_dir,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="A geração do PPTX excedeu o tempo limite") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="O conversor de PPTX não está disponível") from exc
    except (HtmlToPptxError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await persist_workflow_files(session_id)
    return Response(
        content=pptx_content,
        media_type=PPTX_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="apresentacao.pptx"'},
    )
