from pathlib import Path, PurePosixPath

from db.pool import get_pool
from db.queries import get_workflow_files, replace_workflow_files
from graph.tools.sandbox.workdir import workspace_for_chat


WORKFLOW_USER_ID = "10"


def _sandbox_dir(session_id: str) -> Path:
    return workspace_for_chat(WORKFLOW_USER_ID, f"workflow-{session_id}") / "sandbox"


def _safe_relative_path(path: str) -> Path:
    relative = PurePosixPath(path)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError("caminho de arquivo do workflow inválido")
    return Path(*relative.parts)


def _read_sandbox_files(session_id: str) -> list[tuple[str, bytes]]:
    sandbox_dir = _sandbox_dir(session_id)
    if not sandbox_dir.is_dir():
        return []

    files: list[tuple[str, bytes]] = []
    for path in sandbox_dir.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(sandbox_dir).as_posix()
        _safe_relative_path(relative)
        files.append((relative, path.read_bytes()))
    return files


async def persist_workflow_files(session_id: str) -> None:
    files = _read_sandbox_files(session_id)
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await replace_workflow_files(conn, session_id, files)


async def restore_workflow_files(session_id: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await get_workflow_files(conn, session_id)

    sandbox_dir = _sandbox_dir(session_id)
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    stored_paths = {_safe_relative_path(row["path"]) for row in rows}
    # Sincroniza exclusões: um arquivo apagado durante a sessão não pode
    # continuar no workdir local e reaparecer na próxima retomada.
    for current_path in sorted(sandbox_dir.rglob("*"), reverse=True):
        if current_path.is_symlink() or current_path.is_file():
            relative = current_path.relative_to(sandbox_dir)
            if relative not in stored_paths:
                current_path.unlink(missing_ok=True)

    for row in rows:
        relative = _safe_relative_path(row["path"])
        target = sandbox_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(bytes(row["content"]))
