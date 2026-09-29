"""Proteção dos artefatos que podem conter dados privados do professor."""
from uuid import UUID

from fastapi import Depends, HTTPException, Request

from auth.dependencies import CurrentUser, get_optional_current_user
from db.pool import get_pool


async def require_workflow_access(
    request: Request,
    user: CurrentUser | None = Depends(get_optional_current_user),
) -> None:
    session_id = request.path_params.get("session_id")
    sandbox_id = request.path_params.get("sandbox_id")
    if not session_id and not sandbox_id:
        return
    async with get_pool().acquire() as conn:
        if session_id:
            try:
                identifier = UUID(session_id)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail="Sessão não encontrada") from exc
            row = await conn.fetchrow(
                "SELECT owner_user_id FROM workflow_sessions WHERE id=$1", identifier,
            )
            if row is None:
                raise HTTPException(status_code=404, detail="Sessão não encontrada")
        else:
            row = await conn.fetchrow(
                "SELECT owner_user_id FROM workflow_sessions WHERE workdir_id=$1", sandbox_id,
            )
        # Workflows públicos e sandboxes legados não recebem o catálogo privado.
        if row is None or row["owner_user_id"] is None:
            return
        if user is None:
            raise HTTPException(status_code=401, detail="Faça login para acessar esta sessão")
        if str(row["owner_user_id"]) != str(user.user_id):
            raise HTTPException(status_code=404, detail="Sessão não encontrada")
