"""API persistente para os recursos do painel do professor.

Os nomes e o formato das respostas acompanham os tipos usados pelo frontend
React. A autenticação é feita pelo mesmo Bearer JWT dos chats tradicionais.
"""

import asyncio
import base64
import re
import sqlite3
import subprocess
import tempfile

import fitz
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from auth.dependencies import CurrentUser, get_current_user
from db.pool import get_pool
from db.queries import (
    create_material,
    create_template,
    create_turma,
    delete_material,
    delete_template,
    delete_turma,
    get_material,
    get_template,
    get_turma,
    list_materiais,
    list_templates,
    list_turmas,
    replace_material_turmas,
    replace_template_turmas,
    template_name_exists,
    update_material,
    update_template,
    update_turma,
)
from schemas import (
    MaterialCreateIn,
    MaterialOut,
    MaterialUpdateIn,
    TemplateCreateIn,
    TemplateOut,
    TemplateUpdateIn,
    TurmaCreateIn,
    TurmaOut,
    TurmaUpdateIn,
)
from graph.tools.retrieval.audiencias import listar_audiencias, consultar_audiencia
from graph.tools.sandbox.shared.html_pdf_tools import render_html_to_pdf
from services.html_to_docx import HtmlToDocxError, convert_html_bytes_to_docx
from services.pdf_to_html import PdfConversionError, convert_pdf_bytes_to_html


router = APIRouter(prefix="/api", tags=["professor"])


def _decode_asset(value: str | None) -> bytes | None:
    if not value:
        return None
    try:
        encoded = value.split(",", 1)[1] if value.startswith("data:") else value
        return base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Conteúdo de arquivo inválido") from exc


def _safe_name(value: str) -> str:
    value = re.sub(r"\s+", "_", value.strip())
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value) or "arquivo"


def _template_name(value: str | None) -> str:
    raw = Path((value or "template").strip()).name
    stem = Path(raw).stem if Path(raw).suffix else raw
    return f"{_safe_name(stem)}.html"


def _pdf_to_html_fallback(content: bytes) -> bytes:
    try:
        document = fitz.open(stream=content, filetype="pdf")
        pages = []
        for index, page in enumerate(document, start=1):
            page_html = page.get_text("html") or "<p>(Página sem texto extraível)</p>"
            pages.append(f'<section class="pdf-page" data-page="{index}">{page_html}</section>')
        document.close()
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Não foi possível converter o PDF para HTML") from exc
    html = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Documento convertido</title><style>
body{margin:0;background:#f5f5f5;color:#222;font-family:Arial,sans-serif}.pdf-page{position:relative;box-sizing:border-box;width:794px;min-height:1123px;margin:24px auto;padding:32px;background:#fff;box-shadow:0 2px 12px #0002;overflow:hidden}.pdf-page>div{margin:0!important}
</style></head><body>""" + "".join(pages) + "</body></html>"
    return html.encode("utf-8")


def _pdf_to_html(content: bytes) -> bytes:
    try:
        return convert_pdf_bytes_to_html(content)
    except PdfConversionError:
        # Mantém o upload funcional em ambientes sem Poppler ou em PDFs
        # problemáticos; o container oficial instala o conversor principal.
        return _pdf_to_html_fallback(content)


def _stored_html(row, convert_pdf: bool = False) -> str:
    stored = row["file_content"]
    if stored:
        content = bytes(stored)
        file_name = str(row["file_name"] or "").lower()
        try:
            file_type = row["file_type"]
        except (KeyError, IndexError):
            file_type = None
        if convert_pdf and (file_name.endswith(".pdf") or file_type == "pdf"):
            content = _pdf_to_html(content)
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            pass
    return row["html_content"] or ""


def _save_asset(user_id, folder: str, original_name: str | None, content: bytes | None,
                category: str | None = None, material_type: str | None = None,
                requested_name: str | None = None, reject_duplicate: bool = False):
    if not original_name or content is None:
        return None, None
    source = Path(original_name).name
    extension = Path(source).suffix.lower()
    allowed_extensions = {".pdf", ".html"} if folder == "templates" else {".pdf", ".html", ".docx"}
    if extension not in allowed_extensions:
        raise HTTPException(status_code=422, detail="O arquivo deve ser PDF, HTML ou DOCX")
    if extension == ".pdf" and folder == "templates":
        content = _pdf_to_html(content)
        extension = ".html"
    stem = Path(source).stem
    if folder == "materiais":
        type_name = {"source": "fonte_ou_livro", "slide": "slide_apresentacao", "atv": "atividade"}.get(material_type or "source", "fonte_ou_livro")
        stem = f"{category or 'material'}_{stem}_{type_name}"
    stamp = datetime.now().strftime("%d_%m_%Y_%H_%M_%S")
    safe_stem = _safe_name(stem)
    root = Path("/app/workdirs") / str(user_id) / "sandbox" / folder
    root.mkdir(parents=True, exist_ok=True)
    if requested_name:
        requested = Path(requested_name).name
        stored_name = f"{_safe_name(Path(requested).stem)}{extension}"
        if (root / stored_name).exists() and reject_duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Já existe um template com o nome '{stored_name}'. Escolha outro nome.",
            )
    else:
        stored_name = f"{safe_stem}_{stamp}{extension}"
    suffix = 2
    while (root / stored_name).exists():
        if requested_name and reject_duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Já existe um template com o nome '{stored_name}'. Escolha outro nome.",
            )
        stored_name = f"{safe_stem}_{stamp}_{suffix}{extension}"
        suffix += 1
    (root / stored_name).write_bytes(content)
    return stored_name, content


def _audiencias() -> list[dict]:
    try:
        return listar_audiencias()
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=503, detail="Índice de audiências indisponível") from exc


@router.get("/audiencias", response_model=list[dict])
async def list_audiencias():
    return _audiencias()


@router.get("/audiencias/{audiencia_id}", response_model=dict)
async def get_audiencia(audiencia_id: str):
    try:
        audiencia = consultar_audiencia(audiencia_id)
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=503, detail="Índice de audiências indisponível") from exc
    if audiencia is None:
        raise HTTPException(status_code=404, detail="Audiência não encontrada")
    return audiencia


def _timestamp(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


def _turma_image(value) -> str | None:
    if not value:
        return None
    image = str(value)
    # URLs blob pertencem apenas à aba que as criou e não são persistentes.
    return None if image.startswith("blob:") else image


def _turma_output(row) -> dict:
    return {
        "id": str(row["id"]),
        "school": row["school"],
        "series": row["series"],
        "idSeries": row["id_series"],
        "qtd": row["student_count"],
        "disciplina": row["disciplina"],
        "color": row["color"],
        "image": _turma_image(row["image"]),
        "lastModifiedAt": _timestamp(row["updated_at"]),
    }


def _template_output(row) -> dict:
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "qtd": row["qtd"],
        "htmlContent": _stored_html(row, convert_pdf=True),
        "fileName": row.get("file_name") if hasattr(row, "get") else row["file_name"],
        "turmaIds": [str(value) for value in (row["turma_ids"] or [])],
        "lastModifiedAt": _timestamp(row["updated_at"]),
    }


def _material_output(row) -> dict:
    updated_at = row["updated_at"]
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "autoral": row["autoral"],
        "orientation": row["orientation"],
        "type": row["type"],
        "category": row["category"],
        "fileType": row["file_type"],
        "qtd": row["qtd"],
        "htmlContent": _stored_html(row, convert_pdf=False),
        "fileUrl": row["file_url"],
        "fileName": row.get("file_name") if hasattr(row, "get") else row["file_name"],
        "turmaIds": [str(value) for value in (row["turma_ids"] or [])],
        "lastModified": updated_at.isoformat(),
        "lastModifiedAt": _timestamp(updated_at),
    }


async def _owned_turma_ids(conn, user_id: str, turma_ids: list[UUID]) -> list[UUID]:
    unique_ids = list(dict.fromkeys(turma_ids))
    if not unique_ids:
        return []
    rows = await conn.fetch(
        "SELECT id FROM turmas WHERE user_id=$1 AND id=ANY($2::uuid[])",
        user_id,
        unique_ids,
    )
    owned = {row["id"] for row in rows}
    missing = [str(value) for value in unique_ids if value not in owned]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Turma(s) não encontrada(s) para este usuário: {', '.join(missing)}",
        )
    return unique_ids


async def _owned_turma_or_404(conn, user_id: str, turma_id: UUID):
    row = await get_turma(conn, user_id, turma_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turma não encontrada")
    return row


@router.get("/turmas", response_model=list[TurmaOut])
async def get_turmas(user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await list_turmas(conn, user.user_id)
    return [_turma_output(row) for row in rows]


@router.post("/turmas", response_model=TurmaOut, status_code=status.HTTP_201_CREATED)
async def post_turma(body: TurmaCreateIn, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await create_turma(
            conn,
            user.user_id,
            body.school.strip(),
            body.series.strip(),
            body.id_series.strip(),
            body.qtd,
            body.disciplina.strip(),
            body.color,
            body.image,
        )
    return _turma_output(row)


@router.get("/turmas/{turma_id}", response_model=TurmaOut)
async def get_turma_by_id(turma_id: UUID, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await _owned_turma_or_404(conn, user.user_id, turma_id)
    return _turma_output(row)


@router.put("/turmas/{turma_id}", response_model=TurmaOut)
@router.patch("/turmas/{turma_id}", response_model=TurmaOut)
async def put_turma(turma_id: UUID, body: TurmaUpdateIn, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        await _owned_turma_or_404(conn, user.user_id, turma_id)
        row = await update_turma(
            conn,
            user.user_id,
            turma_id,
            body.school.strip(),
            body.series.strip(),
            body.id_series.strip(),
            body.qtd,
            body.disciplina.strip(),
            body.color,
            body.image,
        )
    return _turma_output(row)


@router.delete("/turmas/{turma_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_turma(turma_id: UUID, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        await _owned_turma_or_404(conn, user.user_id, turma_id)
        await delete_turma(conn, user.user_id, turma_id)


@router.get("/templates", response_model=list[TemplateOut])
async def get_templates(user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await list_templates(conn, user.user_id)
    return [_template_output(row) for row in rows]


@router.post("/templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def post_template(body: TemplateCreateIn, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    file_bytes = _decode_asset(body.file_content)
    template_name = _template_name(body.title or body.file_name)
    async with pool.acquire() as conn:
        if await template_name_exists(conn, user.user_id, template_name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Já existe um template com o nome '{template_name}'. Escolha outro nome.",
            )
    stored_name, stored_content = _save_asset(
        user.user_id, "templates", body.file_name, file_bytes,
        requested_name=template_name, reject_duplicate=True,
    )
    title = template_name
    async with pool.acquire() as conn:
        turma_ids = await _owned_turma_ids(conn, user.user_id, body.turma_ids)
        async with conn.transaction():
            created = await create_template(
                conn, user.user_id, title,
                stored_content.decode("utf-8") if stored_content else body.html_content,
                stored_name, stored_content,
            )
            await replace_template_turmas(conn, created["id"], turma_ids)
        row = await get_template(conn, user.user_id, created["id"])
    return _template_output(row)


@router.get("/templates/{template_id}", response_model=TemplateOut)
async def get_template_by_id(template_id: UUID, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await get_template(conn, user.user_id, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template não encontrado")
    return _template_output(row)


@router.put("/templates/{template_id}", response_model=TemplateOut)
@router.patch("/templates/{template_id}", response_model=TemplateOut)
async def put_template(template_id: UUID, body: TemplateUpdateIn, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        if await get_template(conn, user.user_id, template_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template não encontrado")
        turma_ids = await _owned_turma_ids(conn, user.user_id, body.turma_ids)
        async with conn.transaction():
            await update_template(
                conn,
                user.user_id,
                template_id,
                body.title.strip(),
                body.html_content,
            )
            await replace_template_turmas(conn, template_id, turma_ids)
        row = await get_template(conn, user.user_id, template_id)
    return _template_output(row)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_template(template_id: UUID, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        if await get_template(conn, user.user_id, template_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template não encontrado")
        await delete_template(conn, user.user_id, template_id)


@router.get("/materiais", response_model=list[MaterialOut])
async def get_materiais(user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await list_materiais(conn, user.user_id)
    return [_material_output(row) for row in rows]


@router.post("/materiais", response_model=MaterialOut, status_code=status.HTTP_201_CREATED)
async def post_material(body: MaterialCreateIn, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    file_bytes = _decode_asset(body.file_content)
    uploaded_extension = Path(body.file_name or "").suffix.lower()
    uploaded_file_type = (
        "pdf" if uploaded_extension == ".pdf"
        else "html" if uploaded_extension == ".html"
        else "docx" if uploaded_extension == ".docx"
        else body.file_type
    )
    stored_name, stored_content = _save_asset(
        user.user_id, "materiais", body.file_name, file_bytes,
        body.category, body.type,
    )
    if stored_content and uploaded_file_type == "html":
        material_html = stored_content.decode("utf-8")
    elif stored_content:
        material_html = ""
    else:
        material_html = body.html_content
    async with pool.acquire() as conn:
        turma_ids = await _owned_turma_ids(conn, user.user_id, body.turma_ids)
        async with conn.transaction():
            created = await create_material(
                conn, user.user_id, body.title.strip(), body.autoral,
                body.orientation, body.type, body.category,
                uploaded_file_type,
                material_html,
                body.file_url, stored_name, stored_content,
            )
            await replace_material_turmas(conn, created["id"], turma_ids)
        row = await get_material(conn, user.user_id, created["id"])
    return _material_output(row)


@router.get("/materiais/{material_id}", response_model=MaterialOut)
async def get_material_by_id(material_id: UUID, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await get_material(conn, user.user_id, material_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material não encontrado")
    return _material_output(row)


@router.get("/materiais/{material_id}/download")
async def download_material(
    material_id: UUID,
    format: Literal["html", "pdf", "docx"] = Query(...),
    user: CurrentUser = Depends(get_current_user),
):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await get_material(conn, user.user_id, material_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material não encontrado")

    source_type = row["file_type"]
    stored_content = bytes(row["file_content"]) if row["file_content"] else None
    if format == source_type:
        content = stored_content
        if content is None and format == "html":
            content = (row["html_content"] or "").encode("utf-8")
        if content is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Arquivo do material não encontrado")
    elif source_type == "html" and format == "pdf":
        html_content = stored_content or (row["html_content"] or "").encode("utf-8")
        if not html_content.strip():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="O HTML do material está vazio")
        with tempfile.TemporaryDirectory(prefix="material-download-") as tmpdir:
            pdf_path = Path(tmpdir) / "material.pdf"
            try:
                await asyncio.to_thread(render_html_to_pdf, html_content, pdf_path, row["orientation"], tmpdir)
                content = pdf_path.read_bytes()
            except subprocess.TimeoutExpired as exc:
                raise HTTPException(status_code=504, detail="A conversão para PDF excedeu o tempo limite") from exc
            except FileNotFoundError as exc:
                raise HTTPException(status_code=503, detail="O conversor de PDF não está disponível") from exc
            except RuntimeError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
    elif source_type == "html" and format == "docx":
        html_content = stored_content or (row["html_content"] or "").encode("utf-8")
        if not html_content.strip():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="O HTML do material está vazio")
        try:
            content = await asyncio.to_thread(
                convert_html_bytes_to_docx,
                html_content,
                row["title"] or "material",
            )
        except HtmlToDocxError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Não é possível converter um arquivo {source_type.upper()} para {format.upper()}.",
        )

    base_name = _safe_name(Path(row["file_name"] or row["title"]).stem)
    extension = format
    media_types = {
        "html": "text/html; charset=utf-8",
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    return Response(
        content=content,
        media_type=media_types[format],
        headers={"Content-Disposition": f'attachment; filename="{base_name}.{extension}"'},
    )


@router.put("/materiais/{material_id}", response_model=MaterialOut)
@router.patch("/materiais/{material_id}", response_model=MaterialOut)
async def put_material(material_id: UUID, body: MaterialUpdateIn, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        if await get_material(conn, user.user_id, material_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material não encontrado")
        turma_ids = await _owned_turma_ids(conn, user.user_id, body.turma_ids)
        async with conn.transaction():
            await update_material(
                conn,
                user.user_id,
                material_id,
                body.title.strip(),
                body.autoral,
                body.orientation,
                body.type,
                body.category,
                body.file_type,
                body.html_content,
                body.file_url,
            )
            await replace_material_turmas(conn, material_id, turma_ids)
        row = await get_material(conn, user.user_id, material_id)
    return _material_output(row)


@router.delete("/materiais/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_material(material_id: UUID, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        if await get_material(conn, user.user_id, material_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material não encontrado")
        await delete_material(conn, user.user_id, material_id)
