import re
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from graph.tools.sandbox.workdir import BASE_WORKDIRS


MAX_HTML_BYTES = 20 * 1024 * 1024
SANDBOX_ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")

router = APIRouter(prefix="/api/sandboxes", tags=["sandbox"])


@router.post("/{sandbox_id}/html")
async def upload_html_to_sandbox(sandbox_id: str, file: UploadFile = File(...)):
    """Salva um HTML no sandbox informado, sobrescrevendo o mesmo nome."""
    if not SANDBOX_ID_PATTERN.fullmatch(sandbox_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="sandbox_id inválido")

    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".html") or filename in {".", ".."}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Somente arquivos com extensão .html são aceitos",
        )

    sandbox_dir = (BASE_WORKDIRS / sandbox_id / "sandbox").resolve()
    expected_parent = (BASE_WORKDIRS / sandbox_id).resolve()
    if sandbox_dir.parent != expected_parent:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="sandbox_id inválido")
    if not sandbox_dir.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox não encontrado")

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
