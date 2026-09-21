from typing import List
from auth.dependencies import CurrentUser, get_current_user
from fastapi import APIRouter, Depends, HTTPException, status
from db.pool import get_pool
from db.queries import (
    create_chat_tab,
    delete_chat_tab,
    get_chat_messages_by_chat_id,
    get_chat_tab_for_user_id,
    get_chat_tabs_by_user_id,
    update_chat_title,
)
from schemas import (
    ChatMessageOut,
    ChatTabCreateIn,
    ChatTabOut,
    SendMessageIn,
    SendMessageOut,
)
from graph.main import resolve_agent_name
from services.chat_service import run_chat_turn
from graph.tools.sandbox.workdir import remover_workspace_do_chat


router = APIRouter(prefix="/chats", tags=["chats"])


def _chat_tab_output(row) -> ChatTabOut:
    return ChatTabOut(
        id=row["id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _chat_message_output(row) -> ChatMessageOut:
    return ChatMessageOut(
        id=row["id"],
        role=row["role"],
        content=row["content"],
        filename=row["filename"],
        created_at=row["created_at"],
    )


async def _get_owned_chat_or_404(pool, chat_id: str, user: CurrentUser):
    async with pool.acquire() as conn:
        tab = await get_chat_tab_for_user_id(conn, chat_id, user.user_id)
    if tab is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat não encontrado")
    return tab


@router.get("", response_model=List[ChatTabOut])
async def list_chats(user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await get_chat_tabs_by_user_id(conn, user.user_id)
    return [_chat_tab_output(row) for row in rows]


@router.post("", response_model=ChatTabOut)
async def create_chat(body: ChatTabCreateIn, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await create_chat_tab(conn, user.user_id, body.title)
    return _chat_tab_output(row)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_chat(chat_id: str, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    await _get_owned_chat_or_404(pool, chat_id, user)
    async with pool.acquire() as conn:
        await delete_chat_tab(conn, chat_id)
    await remover_workspace_do_chat(user.user_id, chat_id)


@router.patch("/{chat_id}/title", status_code=status.HTTP_204_NO_CONTENT)
async def rename_chat(chat_id: str, body: ChatTabCreateIn, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    await _get_owned_chat_or_404(pool, chat_id, user)
    async with pool.acquire() as conn:
        await update_chat_title(conn, chat_id, body.title)


@router.get("/{chat_id}/messages", response_model=List[ChatMessageOut])
async def list_messages(chat_id: str, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    await _get_owned_chat_or_404(pool, chat_id, user)
    async with pool.acquire() as conn:
        rows = await get_chat_messages_by_chat_id(conn, chat_id)
    return [_chat_message_output(row) for row in rows]


@router.post("/{chat_id}/messages", response_model=SendMessageOut)
async def send_message(chat_id: str, body: SendMessageIn, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    tab = await _get_owned_chat_or_404(pool, chat_id, user)

    try:
        resolve_agent_name(body.agent_name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc),) from exc

    async with pool.acquire() as conn:
        rows = await get_chat_messages_by_chat_id(conn, chat_id)

    reply = await run_chat_turn(
        pool,
        user_id=user.user_id,
        chat_id=chat_id,
        chat_messages=rows,
        context=tab["context"],
        user_input=body.text,
        agent_name=body.agent_name,
    )
    
    return SendMessageOut(reply=reply)
