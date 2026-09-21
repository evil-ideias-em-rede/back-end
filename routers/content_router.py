"""API persistente para os recursos do painel do professor.

Os nomes e o formato das respostas acompanham os tipos usados pelo frontend
React. A autenticação é feita pelo mesmo Bearer JWT dos chats tradicionais.
"""

import sqlite3
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

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


router = APIRouter(prefix="/api", tags=["professor"])


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
        "description": row["description"],
        "htmlContent": row["html_content"],
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
        "htmlContent": row["html_content"],
        "fileUrl": row["file_url"],
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
    async with pool.acquire() as conn:
        turma_ids = await _owned_turma_ids(conn, user.user_id, body.turma_ids)
        async with conn.transaction():
            created = await create_template(
                conn,
                user.user_id,
                body.title.strip(),
                body.description.strip() if body.description else None,
                body.html_content,
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
                body.description.strip() if body.description else None,
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
    async with pool.acquire() as conn:
        turma_ids = await _owned_turma_ids(conn, user.user_id, body.turma_ids)
        async with conn.transaction():
            created = await create_material(
                conn,
                user.user_id,
                body.title.strip(),
                body.autoral,
                body.orientation,
                body.type,
                body.category,
                body.file_type,
                body.html_content,
                body.file_url,
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
