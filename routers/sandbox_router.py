import json
import re
import sqlite3
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from db.pool import get_pool
from db.queries import get_workflow_session
from graph.tools.sandbox.workdir import BASE_WORKDIRS
from graph.tools.sandbox.workdir import workspace_for_chat
from graph.tools.retrieval.audiencias import consultar_audiencia
from services.workflow_files import persist_workflow_files
from services.workflow_files import restore_workflow_files
from uuid import UUID


MAX_HTML_BYTES = 20 * 1024 * 1024
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
SANDBOX_ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")

router = APIRouter(prefix="/api", tags=["sandbox"])


def _sandbox_dir_from_id(sandbox_id: str) -> Path:
    if not SANDBOX_ID_PATTERN.fullmatch(sandbox_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="sandbox_id inválido")

    sandbox_dir = (BASE_WORKDIRS / sandbox_id / "sandbox").resolve()
    expected_parent = (BASE_WORKDIRS / sandbox_id).resolve()
    if sandbox_dir.parent != expected_parent:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="sandbox_id inválido")
    if not sandbox_dir.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox não encontrado")
    return sandbox_dir


def _require_non_empty_file(path: Path, filename: str) -> None:
    try:
        is_non_empty = path.is_file() and path.stat().st_size > 0
    except OSError:
        is_non_empty = False
    if not is_non_empty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{filename} não existe ou está vazio",
        )


async def _workflow_sandbox_dir(session_id: str) -> Path:
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
    sandbox_dir = workspace_for_chat("10", f"workflow-{session_id}") / "sandbox"
    if not sandbox_dir.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox não encontrado")
    return sandbox_dir


def _audiencia_from_indice(audiencia_id: str) -> dict:
    try:
        audiencia = consultar_audiencia(audiencia_id)
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=503, detail="Índice de audiências indisponível") from exc
    if audiencia is None:
        raise HTTPException(status_code=404, detail=f"Audiência '{audiencia_id}' não encontrada")
    return audiencia


@router.post("/workflow/sessions/{session_id}/planning/select/{planning_id}")
async def select_workflow_planning_item(session_id: str, planning_id: str):
    """Seleciona a audiência, salva seu conteúdo no sandbox e devolve o registro completo."""
    sandbox_dir = await _workflow_sandbox_dir(session_id)
    audiencia = _audiencia_from_indice(planning_id)
    audiencia_path = sandbox_dir / "audiencia.json"
    audiencia_changed = True
    try:
        if audiencia_path.is_file():
            current_audiencia = json.loads(audiencia_path.read_text(encoding="utf-8"))
            audiencia_changed = str(current_audiencia.get("id")) != str(audiencia.get("id"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        audiencia_changed = True
    try:
        audiencia_path.write_text(
            json.dumps(audiencia, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Não foi possível salvar a audiência no sandbox") from exc
    planning_path = sandbox_dir / "planning.json"

    if planning_path.is_symlink() or not planning_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="planning.json não existe ou está inválido",
        )

    try:
        planning = json.loads(planning_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="planning.json não contém um JSON válido",
        ) from exc

    if not isinstance(planning, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="planning.json deve conter uma lista de ideias",
        )
    selected_index = next(
        (
            index
            for index, item in enumerate(planning)
            if isinstance(item, dict)
            and str(
                item.get(
                    "id",
                    item.get("ref_id", item.get("audiencia_id", item.get("session_id", ""))),
                )
            ) == planning_id
        ),
        None,
    )
    already_selected = False
    if selected_index is not None:
        already_selected = planning[selected_index].get("user_has_accepted") is True and sum(
            isinstance(item, dict) and item.get("user_has_accepted") is True
            for item in planning
        ) == 1
        if not already_selected:
            for item in planning:
                if isinstance(item, dict):
                    item["user_has_accepted"] = False
            planning[selected_index]["user_has_accepted"] = True

            try:
                planning_path.write_text(
                    json.dumps(planning, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            except OSError as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Não foi possível salvar a ideia escolhida",
                ) from exc

    await persist_workflow_files(session_id)
    return {
        "session_id": session_id,
        "selected_id": planning_id,
        "selected_index": selected_index,
        "changed": audiencia_changed,
        "audiencia": audiencia,
        "audiencia_file": "audiencia.json",
        "planning": planning,
    }


@router.post("/sandboxes/{sandbox_id}/html")
async def upload_html_to_sandbox(sandbox_id: str, file: UploadFile = File(...)):
    """Salva um HTML no sandbox informado, sobrescrevendo o mesmo nome."""
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".html") or filename in {".", ".."}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Somente arquivos com extensão .html são aceitos",
        )

    sandbox_dir = _sandbox_dir_from_id(sandbox_id)

    content = await file.read(MAX_HTML_BYTES + 1)
    if len(content) > MAX_HTML_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="O HTML deve ter no máximo 20 MB")

    target = sandbox_dir / filename
    overwritten = target.is_file()
    target.write_bytes(content)
    return {
        "sandbox_id": sandbox_id,
        "filename": filename,
        "path": f"sandbox/{filename}",
        "overwritten": overwritten,
        "size": len(content),
    }


@router.get("/sandboxes/{sandbox_id}/html")
async def get_html_from_sandbox(sandbox_id: str):
    """Entrega o HTML principal do sandbox."""
    sandbox_dir = _sandbox_dir_from_id(sandbox_id)
    html_path = sandbox_dir / "HTML.html"
    _require_non_empty_file(html_path, "HTML.html")
    return FileResponse(html_path, media_type="text/html", headers={"Cache-Control": "no-store"})


@router.get("/sandboxes/{sandbox_id}/{filename:path}")
async def get_sandbox_file(sandbox_id: str, filename: str):
    """Entrega um arquivo não vazio do sandbox sem expor seu caminho absoluto."""
    sandbox_dir = _sandbox_dir_from_id(sandbox_id).resolve()
    relative_name = filename.removeprefix("sandbox/")
    file_path = (sandbox_dir / relative_name).resolve()
    try:
        file_path.relative_to(sandbox_dir)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Arquivo não encontrado") from exc
    _require_non_empty_file(file_path, relative_name)
    return FileResponse(file_path, headers={"Cache-Control": "no-store"})


@router.get("/workflow/sessions/{session_id}/html")
async def get_workflow_html(session_id: str):
    """Entrega o HTML produzido pelo agente no sandbox da sessão."""
    sandbox_dir = await _workflow_sandbox_dir(session_id)
    html_path = sandbox_dir / "HTML.html"
    _require_non_empty_file(html_path, "HTML.html")
    return FileResponse(html_path, media_type="text/html", headers={"Cache-Control": "no-store"})


@router.get("/workflow/sessions/{session_id}/{filename:path}")
async def get_workflow_asset(session_id: str, filename: str):
    """Serve imagens, documentos e outros arquivos do sandbox da sessão."""
    sandbox_dir = (await _workflow_sandbox_dir(session_id)).resolve()
    relative_name = filename.removeprefix("sandbox/")
    asset_path = (sandbox_dir / relative_name).resolve()
    try:
        asset_path.relative_to(sandbox_dir)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Arquivo não encontrado") from exc
    _require_non_empty_file(asset_path, relative_name)
    return FileResponse(asset_path, headers={"Cache-Control": "no-store"})


@router.post("/workflow/sessions/{session_id}/files")
async def upload_workflow_file(session_id: str, file: UploadFile = File(...)):
    """Salva um anexo enviado pelo frontend no sandbox da sessão."""
    sandbox_dir = await _workflow_sandbox_dir(session_id)
    filename = Path(file.filename or "").name
    if not filename or filename in {".", ".."}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nome de arquivo inválido")

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="O arquivo deve ter no máximo 20 MB")
    target = sandbox_dir / filename
    target.write_bytes(content)
    await persist_workflow_files(session_id)
    return {"filename": filename, "sandbox_path": f"sandbox/{filename}", "size": len(content)}
