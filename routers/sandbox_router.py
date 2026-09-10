import re
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from db.memory_store import memory_store
from graph.tools.sandbox.workdir import BASE_WORKDIRS
from graph.tools.sandbox.workdir import workspace_for_chat


MAX_HTML_BYTES = 20 * 1024 * 1024
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
SANDBOX_ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")

router = APIRouter(prefix="/api", tags=["sandbox"])


def _session_or_404(session_id: str) -> None:
    try:
        memory_store.snapshot(session_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sessão não encontrada na memória do servidor",
        ) from exc


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


def _workflow_sandbox_dir(session_id: str) -> Path:
    _session_or_404(session_id)
    sandbox_dir = workspace_for_chat("workflow-demo-user", f"workflow-{session_id}") / "sandbox"
    if not sandbox_dir.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox não encontrado")
    return sandbox_dir


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
    sandbox_dir = _workflow_sandbox_dir(session_id)
    html_path = sandbox_dir / "HTML.html"
    _require_non_empty_file(html_path, "HTML.html")
    return FileResponse(html_path, media_type="text/html", headers={"Cache-Control": "no-store"})


@router.get("/workflow/sessions/{session_id}/{filename:path}")
async def get_workflow_asset(session_id: str, filename: str):
    """Serve imagens, documentos e outros arquivos do sandbox da sessão."""
    sandbox_dir = _workflow_sandbox_dir(session_id).resolve()
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
    sandbox_dir = _workflow_sandbox_dir(session_id)
    filename = Path(file.filename or "").name
    if not filename or filename in {".", ".."}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nome de arquivo inválido")

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="O arquivo deve ter no máximo 20 MB")
    target = sandbox_dir / filename
    target.write_bytes(content)
    return {"filename": filename, "sandbox_path": f"sandbox/{filename}", "size": len(content)}
