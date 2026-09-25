import logging
import sqlite3
from typing import Awaitable, Callable, Literal
import json
from pathlib import Path
from uuid import uuid4

import jwt
from openai import AuthenticationError
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, ConfigDict, Field

from auth.dependencies import CurrentUser, get_optional_current_user
from auth.jwt_utils import decode_access_token
from db.pool import get_pool
from db.memory_store import memory_store
from db.queries import (
    add_workflow_message,
    create_workflow_session as insert_workflow_session,
    delete_workflow_session,
    get_workflow_messages,
    get_workflow_session as fetch_workflow_session,
    get_workflow_session_for_owner,
    get_workflow_sessions,
    get_workflow_sessions_for_owner,
    update_workflow_session_stage,
)
from graph.main import GRAPH_BUILDER
from graph.tools.sandbox.workdir import _extrai_sandbox_dir, remover_work_dir, workspace_for_chat, workspace_id_for_chat
from graph.tools.retrieval.audiencias import listar_audiencias
from services.workflow_files import persist_workflow_files, restore_workflow_files


AgentName = Literal[
    "brainstorm",
    "debate",
    "generic",
    "lesson_plan",
    "political_leteracy",
    "writing_workshop",
    "slides",
    "editor_geral",
    # Compatibilidade com sessões criadas pela primeira versão do editor.
    "template_editor",
]

GRAPH_AGENT_NAMES = {
    "brainstorm": "brainstorm_node",
    "lesson_plan": "lesson_plan_node",
    "debate": "debate_outline_node",
    "political_leteracy": "political_leteracy_node",
    "generic": "generic_activity_node",
    "writing_workshop": "writing_workshop_node",
    "slides": "slides_node",
    "editor_geral": "template_editor_node",
    "template_editor": "template_editor_node",
}


class WorkflowMessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=20000)
    agent_name: AgentName
    hidden: bool = False


class WorkflowAdvanceIn(BaseModel):
    from_agent: Literal["brainstorm"]


class WorkflowSessionOut(BaseModel):
    id: str
    created_at: str
    selected_agent: AgentName | None = None
    messages: list[dict]


class WorkflowSessionSummaryOut(BaseModel):
    id: str
    created_at: str
    selected_agent: AgentName | None = None
    current_stage: Literal["audiences", "editor"] = "audiences"
    message_count: int
    last_message_at: str | None = None
    last_message: str | None = None


class WorkflowReplyOut(BaseModel):
    session_id: str
    message: dict
    html_url: str | None = None


router = APIRouter(prefix="/api/workflow", tags=["workflow"])
logger = logging.getLogger(__name__)
WORKFLOW_USER_ID = 10
WORKFLOW_USER_ID_STR = str(WORKFLOW_USER_ID)


class WorkflowSessionCreateIn(BaseModel):
    user_id: int = Field(default=WORKFLOW_USER_ID, ge=1)
    agent_name: AgentName | None = None


class WorkflowStageIn(BaseModel):
    stage: Literal["audiences", "editor"]


def _workflow_chat_id(session_id: str) -> str:
    return f"workflow-{session_id}"


def _workflow_workspace(session_id: str) -> Path:
    return workspace_for_chat(WORKFLOW_USER_ID_STR, _workflow_chat_id(session_id))


def _history(rows: list[dict]) -> list:
    message_types = {"user": HumanMessage, "assistant": AIMessage}
    return [message_types[row["role"]](content=row["content"]) for row in rows]


def _message_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") in {"text", "output_text"}:
                parts.append(str(item.get("text", "")))
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict) and content.get("type") in {"text", "output_text"}:
        return str(content.get("text", ""))
    return str(content)


def _is_tool_result(value) -> bool:
    return (
        isinstance(value, dict)
        and {"stdout", "stderr", "returncode", "sucesso"}.issubset(value.keys())
    )


class _ToolOutputPrefixFilter:
    """Remove blocos JSON técnicos do execute_bash antes de enviá-los ao chat."""

    def __init__(self) -> None:
        self._buffer = ""

    def push(self, text: str) -> str:
        self._buffer += text
        output: list[str] = []
        marker = '{"stdout"'
        while True:
            marker_start = self._buffer.find(marker)
            if marker_start < 0:
                keep = len(marker) - 1
                if len(self._buffer) <= keep:
                    break
                output.append(self._buffer[:-keep])
                self._buffer = self._buffer[-keep:]
                break

            if marker_start:
                output.append(self._buffer[:marker_start])
            candidate = self._buffer[marker_start:]
            try:
                value, end = json.JSONDecoder().raw_decode(candidate)
            except json.JSONDecodeError:
                self._buffer = candidate
                break

            if not _is_tool_result(value):
                output.append(candidate[:1])
                self._buffer = candidate[1:]
                continue

            self._buffer = candidate[end:]
            if self._buffer and self._buffer[0].isspace():
                self._buffer = self._buffer.lstrip()
        return "".join(output)

    def finish(self) -> str:
        # Se ficou um JSON técnico incompleto, não o expõe no chat.
        if self._buffer.lstrip().startswith('{"stdout"'):
            return ""
        output = self._buffer
        self._buffer = ""
        return output


def _clean_agent_text(content) -> str:
    text_filter = _ToolOutputPrefixFilter()
    return text_filter.push(_message_text(content)) + text_filter.finish()


def _session_or_404(session_id: str) -> dict:
    try:
        return memory_store.snapshot(session_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sessão não encontrada na memória do servidor",
        ) from exc


async def _ensure_session(session_id: str) -> dict:
    """Carrega uma sessão persistida para a memória usada pelo grafo."""
    try:
        session = memory_store.snapshot(session_id)
        await restore_workflow_files(session_id)
        return session
    except KeyError:
        pass

    try:
        pool = get_pool()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Banco de dados indisponível. Verifique DATABASE_URL no .env.",
        ) from exc
    async with pool.acquire() as conn:
        session_row = await fetch_workflow_session(conn, session_id)
        if session_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada")
        message_rows = await get_workflow_messages(conn, session_id)

    created_at = session_row["created_at"].isoformat()
    memory_store.create_session(
        session_id=str(session_row["id"]),
        created_at=created_at,
        selected_agent=session_row["selected_agent"],
    )
    for row in message_rows:
        memory_store.add_message(
            session_id,
            role=row["role"],
            content=row["content"] or "",
            agent_name=row["agent_name"],
            hidden=row["hidden"],
        )
    await restore_workflow_files(session_id)
    return memory_store.snapshot(session_id)


async def _ensure_session_access(session_id: str, user: CurrentUser | None) -> None:
    """Mantém o modo mock público e restringe sessões novas ao seu dono."""
    if user is None:
        return
    try:
        pool = get_pool()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Banco de dados indisponível. Verifique DATABASE_URL no .env.",
        ) from exc
    async with pool.acquire() as conn:
        row = await get_workflow_session_for_owner(conn, session_id, user.user_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada")


def _websocket_user(websocket: WebSocket) -> CurrentUser | None:
    """Lê o JWT de `?token=` ou do header Authorization, sem quebrar o mock."""
    authorization = websocket.headers.get("authorization", "")
    token = websocket.query_params.get("token")
    if not token and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido") from exc
    return CurrentUser(user_id=payload["sub"], google_id=payload.get("google_id"))


def _validate_agent_for_session(session: dict, agent_name: AgentName) -> None:
    selected_agent = session.get("selected_agent")
    if selected_agent and agent_name not in {"brainstorm", selected_agent}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Esta sessão foi criada para o agente final '{selected_agent}'.",
        )


async def _persist_workflow_message(session_id: str, agent_name: str, role: str, content: str, hidden: bool = False) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await add_workflow_message(conn, session_id, agent_name, role, content, hidden)


def _is_non_empty_file(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _graph_config(session_id: str, agent_name: str | None = None) -> dict:
    configurable = {
        "thread_id": _workflow_chat_id(session_id),
        "user_id": WORKFLOW_USER_ID_STR,
        "work_dir": str(_workflow_workspace(session_id)),
    }
    if agent_name:
        configurable["agent_name"] = agent_name
    return {
        "configurable": {
            **configurable,
        }
    }


def _workflow_state(
    session: dict,
    session_id: str,
    text: str,
    agent_name: AgentName,
    editor_mode: bool = False,
    user_edited: bool = False,
) -> dict:
    return {
        "messages": _history(session["messages"]) + [HumanMessage(content=text)],
        "chat_id": _workflow_chat_id(session_id),
        "user_id": WORKFLOW_USER_ID_STR,
        "context": None,
        "agent_name": GRAPH_AGENT_NAMES[agent_name],
        "selected_agent": None,
        "next_node": None,
        "editor_mode": editor_mode,
        "user_edited": user_edited,
    }


def _workflow_artifacts(session_id: str, agent_name: AgentName) -> dict:
    sandbox_dir = _workflow_workspace(session_id) / "sandbox"
    if agent_name == "brainstorm":
        filename = "planning.json"
    elif agent_name in {
        "debate", "generic", "lesson_plan", "political_leteracy",
        "writing_workshop", "slides",
        "editor_geral",
        "template_editor",
    }:
        filename = "HTML.html"
    else:
        return {}

    path = sandbox_dir / filename
    if not _is_non_empty_file(path):
        return {}
    if filename == "HTML.html":
        url = f"/api/workflow/sessions/{session_id}/html"
        return {"html_url": url, "artifact_name": filename, "artifact_url": url}
    url = f"/api/workflow/sessions/{session_id}/{filename}"
    return {"artifact_name": filename, "artifact_url": url}


def _planning_path(session_id: str) -> Path:
    return _workflow_workspace(session_id) / "sandbox" / "planning.json"


def _read_planning(session_id: str) -> list[dict]:
    path = _planning_path(session_id)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="planning.json não contém JSON válido") from exc
    if not isinstance(value, list):
        raise HTTPException(status_code=422, detail="planning.json deve conter uma lista")
    return [item for item in value if isinstance(item, dict)]


def _audiencias_do_indice() -> list[dict]:
    try:
        return listar_audiencias()
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=503, detail="Índice de audiências indisponível") from exc


def _audiencia_for_planning_item(item: dict) -> dict | None:
    audiences = _audiencias_do_indice()
    candidate_ids = [
        item.get("audiencia_id"),
        item.get("audienciaId"),
        item.get("ref_id"),
        item.get("id"),
    ]
    for candidate_id in candidate_ids:
        if candidate_id is None:
            continue
        match = next((audiencia for audiencia in audiences if str(audiencia.get("id")) == str(candidate_id)), None)
        if match:
            return match
    title = str(item.get("titulo", "")).strip().casefold()
    if title:
        return next(
            (audiencia for audiencia in audiences if str(audiencia.get("titulo", "")).strip().casefold() == title),
            None,
        )
    return None


def _has_brainstorm_conversation_after(path: Path, session_id: str) -> bool:
    """Confirma uma conversa real do brainstorm sem depender de timestamps."""
    del path  # O arquivo é validado separadamente em _advance_validation_errors.
    try:
        messages = memory_store.messages(session_id)
    except KeyError:
        return False

    has_visible_user_message = any(
        message.get("agent_name") == "brainstorm"
        and message.get("role") == "user"
        and message.get("hidden") is not True
        and bool(str(message.get("content") or "").strip())
        for message in messages
    )
    has_brainstorm_response = any(
        message.get("agent_name") == "brainstorm"
        and message.get("role") == "assistant"
        and bool(str(message.get("content") or "").strip())
        for message in messages
    )
    return has_visible_user_message and has_brainstorm_response


async def _stream_graph_response(
    state: dict,
    config: dict,
    emit: Callable[[dict], Awaitable[None]],
) -> str:
    """Executa o grafo e envia somente os deltas textuais da LLM."""
    parts: list[str] = []
    text_filter = _ToolOutputPrefixFilter()
    async for item in GRAPH_BUILDER.astream(
        state,
        config=config,
        stream_mode="messages",
        version="v2",
    ):
        if not isinstance(item, dict) or item.get("type") != "messages":
            continue
        data = item.get("data")
        if not isinstance(data, tuple) or len(data) != 2:
            continue
        chunk = data[0]
        delta = _message_text(getattr(chunk, "content", ""))
        if not delta:
            continue
        visible_delta = text_filter.push(delta)
        if not visible_delta:
            continue
        parts.append(visible_delta)
        await emit({"type": "token", "content": visible_delta})
    trailing_text = text_filter.finish()
    if trailing_text:
        parts.append(trailing_text)
        await emit({"type": "token", "content": trailing_text})
    return "".join(parts)


async def _run_streamed_message(
    session_id: str,
    body: WorkflowMessageIn,
    emit: Callable[[dict], Awaitable[None]],
) -> dict:
    session = await _ensure_session(session_id)
    _validate_agent_for_session(session, body.agent_name)
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A mensagem não pode ficar vazia")

    await _persist_workflow_message(session_id, body.agent_name, "user", text, body.hidden)
    memory_store.add_message(
        session_id,
        role="user",
        content=text,
        agent_name=body.agent_name,
        hidden=body.hidden,
    )
    state = _workflow_state(session, session_id, text, body.agent_name)
    try:
        reply_text = await _stream_graph_response(state, _graph_config(session_id, body.agent_name), emit)
    finally:
        try:
            await persist_workflow_files(session_id)
        except Exception:
            logger.exception("Não foi possível persistir o sandbox da sessão %s", session_id)
    reply = memory_store.add_message(
        session_id,
        role="assistant",
        content=reply_text,
        agent_name=body.agent_name,
    )
    await _persist_workflow_message(session_id, body.agent_name, "assistant", reply_text)
    payload = {
        "type": "done",
        "session_id": session_id,
        "message": reply,
    }
    payload.update(_workflow_artifacts(session_id, body.agent_name))
    return payload


def _advance_instruction(from_agent: str) -> str:
    required_file = "planning.json"
    return (
        "O usuário clicou no botão para avançar para o próximo agente. "
        "Esta é uma solicitação real do usuário e sua resposta será exibida diretamente no chat do frontend. "
        "Responda em português, de forma clara e objetiva, sem mencionar instruções internas do sistema. "
        f"Verifique se {required_file} está completo no sandbox. "
        "Para planning.json, só considere pronto quando houver uma lista válida de ideias. "
        "Também confirme que a audiência escolhida está disponível antes de avançar. "
        f"Se não existir ou estiver incompleto, informe quais dados faltam, mas não cite nomes de arquivos. "
        f"Se houver informações suficientes, gere ou atualize {required_file}, leia o arquivo novamente, "
        "se o usuário já tiver escolhido uma ideia, marque exatamente essa ideia como aceita, "
        "confirme que está correto e informe ao usuário que ele pode prosseguir."
    )


def _advance_allowed(session_id: str, from_agent: str) -> bool:
    return not _advance_validation_errors(session_id, from_agent)


def _advance_validation_errors(session_id: str, from_agent: str) -> list[str]:
    sandbox_dir = _workflow_workspace(session_id) / "sandbox"
    path = sandbox_dir / "planning.json"
    errors: list[str] = []
    if from_agent == "brainstorm":
        if not _has_brainstorm_conversation_after(path, session_id):
            errors.append("O brainstorm ainda não respondeu ao usuário.")
        if not path.is_file():
            errors.append("Não existe um plano de audiência: planning.json não foi criado.")
        else:
            try:
                planning = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(planning, list) or not planning:
                    errors.append("O plano de audiência está vazio ou não contém uma lista válida.")
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                errors.append("planning.json existe, mas não contém JSON válido.")
        try:
            audiencia_path = sandbox_dir / "audiencia.json"
            if not audiencia_path.is_file():
                errors.append("Nenhuma audiência foi escolhida. Clique na audiência desejada.")
            else:
                audiencia = json.loads(audiencia_path.read_text(encoding="utf-8"))
                if not isinstance(audiencia, dict):
                    errors.append("audiencia.json não contém um objeto JSON válido.")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            errors.append("audiencia.json existe, mas não contém JSON válido.")
        return errors
    try:
        return [] if path.is_file() and bool(path.read_text(encoding="utf-8").strip()) else ["planning.json não existe ou está vazio."]
    except (OSError, UnicodeDecodeError):
        return ["Não foi possível validar o planejamento."]


@router.post("/sessions", response_model=WorkflowSessionOut)
async def create_workflow_session(
    body: WorkflowSessionCreateIn,
    user: CurrentUser | None = Depends(get_optional_current_user),
):
    if user is None and body.user_id != WORKFLOW_USER_ID:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"O usuário mock disponível é o id {WORKFLOW_USER_ID}",
        )

    # O id do workdir é persistido junto da sessão para permitir rastrear a
    # relação entre o banco e workdirs/<id>/sandbox.
    session_uuid = uuid4()
    session_id_hint = str(session_uuid)
    workdir_id = workspace_id_for_chat(WORKFLOW_USER_ID_STR, _workflow_chat_id(session_id_hint))
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await insert_workflow_session(
            conn,
            session_uuid,
            WORKFLOW_USER_ID,
            body.agent_name,
            workdir_id,
            owner_user_id=user.user_id if user else None,
        )

    session_id = str(row["id"])
    session = memory_store.create_session(
        session_id=session_id,
        created_at=row["created_at"].isoformat(),
        selected_agent=row["selected_agent"],
    )
    # Prepara o sandbox no momento em que a sessão nasce. Antes disso ele só
    # era criado quando o agente chamava uma ferramenta pela primeira vez.
    await _extrai_sandbox_dir(
        {
            "configurable": {
                "user_id": WORKFLOW_USER_ID_STR,
                "thread_id": _workflow_chat_id(session["id"]),
                "agent_name": body.agent_name or "brainstorm",
            }
        }
    )
    await persist_workflow_files(session["id"])
    return session


@router.get("/sessions", response_model=list[WorkflowSessionSummaryOut])
async def list_workflow_sessions(
    user_id: int = Query(default=WORKFLOW_USER_ID, ge=1),
    user: CurrentUser | None = Depends(get_optional_current_user),
):
    if user is None and user_id != WORKFLOW_USER_ID:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"O usuário mock disponível é o id {WORKFLOW_USER_ID}",
        )

    try:
        pool = get_pool()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Banco de dados indisponível. Verifique DATABASE_URL no .env.",
        ) from exc
    async with pool.acquire() as conn:
        rows = (
            await get_workflow_sessions_for_owner(conn, user.user_id)
            if user
            else await get_workflow_sessions(conn, user_id)
        )
    return [
        {
            "id": str(row["id"]),
            "created_at": row["created_at"].isoformat(),
            "selected_agent": row["selected_agent"],
            "current_stage": row["current_stage"] or "audiences",
            "message_count": row["message_count"],
            "last_message_at": row["last_message_at"].isoformat() if row["last_message_at"] else None,
            "last_message": row["last_message"],
        }
        for row in rows
    ]


@router.patch("/sessions/{session_id}/stage")
async def update_workflow_stage(
    session_id: str,
    body: WorkflowStageIn,
    user: CurrentUser | None = Depends(get_optional_current_user),
):
    """Persiste a tela atual para a retomada não depender dos arquivos do sandbox."""
    await _ensure_session_access(session_id, user)
    try:
        pool = get_pool()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Banco de dados indisponível. Verifique DATABASE_URL no .env.",
        ) from exc
    async with pool.acquire() as conn:
        row = await update_workflow_session_stage(conn, session_id, body.stage)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada")
    return {
        "session_id": str(row["id"]),
        "current_stage": row["current_stage"],
    }


@router.get("/sessions/{session_id}", response_model=WorkflowSessionOut)
async def get_workflow_session(
    session_id: str,
    user: CurrentUser | None = Depends(get_optional_current_user),
):
    await _ensure_session_access(session_id, user)
    return await _ensure_session(session_id)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_workflow_session(
    session_id: str,
    user: CurrentUser | None = Depends(get_optional_current_user),
):
    await _ensure_session_access(session_id, user)
    pool = get_pool()
    owner_user_id = user.user_id if user else None
    async with pool.acquire() as conn:
        deleted = await delete_workflow_session(conn, session_id, owner_user_id)
    if deleted is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada")
    memory_store._sessions.pop(session_id, None)
    await remover_work_dir(deleted["workdir_id"])


@router.get("/sessions/{session_id}/planning", response_model=list[dict])
async def get_workflow_planning(
    session_id: str,
    user: CurrentUser | None = Depends(get_optional_current_user),
):
    await _ensure_session_access(session_id, user)
    await _ensure_session(session_id)
    return _read_planning(session_id)


@router.post("/sessions/{session_id}/planning/select/{planning_id}", response_model=dict)
async def select_workflow_planning(
    session_id: str,
    planning_id: str,
    user: CurrentUser | None = Depends(get_optional_current_user),
):
    await _ensure_session_access(session_id, user)
    await _ensure_session(session_id)
    planning = _read_planning(session_id)
    selected = next(
        (
            item
            for item in planning
            if str(item.get("id", item.get("ref_id", ""))) == planning_id
        ),
        None,
    )
    if selected is None:
        raise HTTPException(status_code=404, detail="Item de planejamento não encontrado")

    audiencia = _audiencia_for_planning_item(selected)
    if audiencia is None:
        raise HTTPException(
            status_code=404,
            detail="O item selecionado não possui uma audiência correspondente",
        )

    audiencia_path = _workflow_workspace(session_id) / "sandbox" / "audiencia.json"
    audiencia_path.parent.mkdir(parents=True, exist_ok=True)
    audiencia_path.write_text(json.dumps(audiencia, ensure_ascii=False, indent=2), encoding="utf-8")
    await persist_workflow_files(session_id)
    return audiencia


@router.websocket("/sessions/{session_id}/ws")
async def workflow_socket(websocket: WebSocket, session_id: str):
    """Transmite a resposta da LLM e sinaliza a conclusão com um evento done."""
    await websocket.accept()
    try:
        websocket_user = _websocket_user(websocket)
        await _ensure_session_access(session_id, websocket_user)
        await _ensure_session(session_id)
    except HTTPException as exc:
        await websocket.close(code=1008, reason=str(exc.detail))
        return

    async def emit(event: dict) -> None:
        await websocket.send_json(event)

    try:
        while True:
            request = await websocket.receive_json()
            request_type = request.get("type") if isinstance(request, dict) else None

            if request_type == "message":
                body = WorkflowMessageIn.model_validate(request)
                payload = await _run_streamed_message(session_id, body, emit)
                await websocket.send_json(payload)
                continue

            if request_type == "advance":
                advance = WorkflowAdvanceIn.model_validate(request)
                validation_errors = _advance_validation_errors(session_id, advance.from_agent)
                if not validation_errors:
                    payload = {
                        "type": "done",
                        "session_id": session_id,
                        "allowed": True,
                    }
                    payload.update(_workflow_artifacts(session_id, advance.from_agent))
                    await websocket.send_json(payload)
                    continue
                await websocket.send_json({
                    "type": "error",
                    "status_code": 400,
                    "detail": validation_errors,
                    "message": "Não é possível escolher o agente final: " + " ".join(validation_errors),
                })
                continue

            await websocket.send_json({"type": "error", "message": "Tipo de evento inválido."})
    except WebSocketDisconnect:
        return
    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except WebSocketDisconnect:
            return


async def _process_workflow_message(
    session_id: str,
    body: WorkflowMessageIn,
    user: CurrentUser | None = Depends(get_optional_current_user),
    editor_mode: bool = False,
):
    await _ensure_session_access(session_id, user)
    session = await _ensure_session(session_id)
    _validate_agent_for_session(session, body.agent_name)
    text = body.text.strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A mensagem não pode ficar vazia",
        )
    
    await _persist_workflow_message(session_id, body.agent_name, "user", text, body.hidden)
    memory_store.add_message(
        session_id,
        role="user",
        content=text,
        agent_name=body.agent_name,
        hidden=body.hidden,
    )

    state = _workflow_state(
        session,
        session_id,
        text,
        body.agent_name,
        editor_mode=editor_mode,
        user_edited=getattr(body, "user_edited", False),
    )

    try:
        # O ToolNode precisa receber a mesma identidade do chat para preparar
        # o sandbox correto. Sem esta configuração, execute_bash não consegue
        # resolver o diretório e falha antes de acessar planning.json.
        graph_config = _graph_config(session_id, body.agent_name)
        result = await GRAPH_BUILDER.ainvoke(state, config=graph_config)
        reply_text = _clean_agent_text(result["messages"][-1].content)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="A chave OPENAI_API_KEY está ausente ou inválida no back-end. Preencha back-end/.env e reinicie o serviço.",
        ) from exc
    except Exception:
        # A entrada do usuário já foi salva. Deixamos o erro chegar ao front
        # para que uma falha do provedor não seja confundida com resposta do agente.
        raise
    finally:
        try:
            await persist_workflow_files(session_id)
        except Exception:
            logger.exception("Não foi possível persistir o sandbox da sessão %s", session_id)

    reply = memory_store.add_message(
        session_id,
        role="assistant",
        content=reply_text,
        agent_name=body.agent_name,
    )
    await _persist_workflow_message(session_id, body.agent_name, "assistant", reply_text)
    html_url = None
    if body.agent_name in {
        "debate", "generic", "lesson_plan", "political_leteracy",
        "writing_workshop", "slides",
        "editor_geral",
        "template_editor",
    }:
        html_path = _workflow_workspace(session_id) / "sandbox" / "HTML.html"
        if html_path.is_file():
            html_url = f"/api/workflow/sessions/{session_id}/html"
    return {"session_id": session_id, "message": reply, "html_url": html_url}


@router.post("/sessions/{session_id}/advance")
async def advance_workflow(
    session_id: str,
    body: WorkflowAdvanceIn,
    user: CurrentUser | None = Depends(get_optional_current_user),
):
    """Valida o arquivo obrigatório antes de trocar de agente."""
    await _ensure_session_access(session_id, user)
    await _ensure_session(session_id)
    if _advance_allowed(session_id, body.from_agent):
        payload = {
            "allowed": True,
            "session_id": session_id,
            "message": None,
        }
        payload.update(_workflow_artifacts(session_id, body.from_agent))
        return payload

    reply_data = await _process_workflow_message(
        session_id,
        WorkflowMessageIn(
            text=_advance_instruction(body.from_agent),
            agent_name=body.from_agent,
            hidden=True,
        ),
        user,
    )
    allowed = _advance_allowed(session_id, body.from_agent)
    if allowed:
        return {"allowed": True, **reply_data}
    # Mantém a resposta original da LLM no chat. O backend apenas informa o
    # resultado da validação para o front decidir se libera a transição.
    return {"allowed": False, **reply_data}
