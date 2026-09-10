from typing import Awaitable, Callable, Literal
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from db.memory_store import memory_store
from graph.main import GRAPH_BUILDER
from graph.tools.sandbox.workdir import _extrai_sandbox_dir, workspace_for_chat


AgentName = Literal[
    "brainstorm",
    "specification",
    "debate",
    "generic",
    "lesson_plan",
    "political_leteracy",
]


class WorkflowMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    agent_name: AgentName


class WorkflowAdvanceIn(BaseModel):
    from_agent: Literal["brainstorm", "specification"]


class WorkflowSessionOut(BaseModel):
    id: str
    created_at: str
    messages: list[dict]


class WorkflowReplyOut(BaseModel):
    session_id: str
    message: dict
    html_url: str | None = None


router = APIRouter(prefix="/api/workflow", tags=["workflow"])


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


def _is_non_empty_file(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _graph_config(session_id: str) -> dict:
    return {
        "configurable": {
            "thread_id": f"workflow-{session_id}",
            "user_id": "workflow-demo-user",
            "work_dir": str(workspace_for_chat("workflow-demo-user", f"workflow-{session_id}")),
        }
    }


def _workflow_state(session: dict, session_id: str, text: str, agent_name: AgentName) -> dict:
    return {
        "messages": _history(session["messages"]) + [HumanMessage(content=text)],
        "chat_id": f"workflow-{session_id}",
        "user_id": "workflow-demo-user",
        "context": None,
        "agent_name": agent_name,
        "selected_agent": None,
        "next_node": None,
    }


def _workflow_artifacts(session_id: str, agent_name: AgentName) -> dict:
    sandbox_dir = workspace_for_chat("workflow-demo-user", f"workflow-{session_id}") / "sandbox"
    if agent_name == "brainstorm":
        filename = "planning.json"
    elif agent_name == "specification":
        filename = "specification.json"
    elif agent_name in {"debate", "generic", "lesson_plan", "political_leteracy"}:
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
    session = _session_or_404(session_id)
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A mensagem não pode ficar vazia")

    memory_store.add_message(session_id, role="user", content=text, agent_name=body.agent_name)
    state = _workflow_state(session, session_id, text, body.agent_name)
    reply_text = await _stream_graph_response(state, _graph_config(session_id), emit)
    reply = memory_store.add_message(
        session_id,
        role="assistant",
        content=reply_text,
        agent_name=body.agent_name,
    )
    payload = {
        "type": "done",
        "session_id": session_id,
        "message": reply,
    }
    payload.update(_workflow_artifacts(session_id, body.agent_name))
    return payload


def _advance_instruction(from_agent: str) -> str:
    required_file = "planning.json" if from_agent == "brainstorm" else "specification.json"
    return (
        "O usuário clicou no botão para avançar para o próximo agente. "
        "Esta é uma solicitação real do usuário e sua resposta será exibida diretamente no chat do frontend. "
        "Responda em português, de forma clara e objetiva, sem mencionar instruções internas do sistema. "
        f"Verifique se {required_file} está completo no sandbox. "
        "Para planning.json, só considere pronto quando houver exatamente uma ideia com user_has_accepted igual a true. "
        "Para specification.json, só considere pronto quando houver um objeto JSON válido e não vazio. "
        f"Se não existir ou estiver incompleto, informe quais dados faltam, mas não cite nomes de arquivos. "
        f"Se houver informações suficientes, gere ou atualize {required_file}, leia o arquivo novamente, "
        "se o usuário já tiver escolhido uma ideia, marque exatamente essa ideia como aceita, "
        "confirme que está correto e informe ao usuário que ele pode prosseguir."
    )


def _advance_allowed(session_id: str, from_agent: str) -> bool:
    filename = "planning.json" if from_agent == "brainstorm" else "specification.json"
    path = workspace_for_chat("workflow-demo-user", f"workflow-{session_id}") / "sandbox" / filename
    if from_agent == "brainstorm":
        try:
            planning = json.loads(path.read_text(encoding="utf-8"))
            return (
                isinstance(planning, list)
                and sum(
                    isinstance(item, dict) and item.get("user_has_accepted") is True
                    for item in planning
                ) == 1
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return False
    try:
        specification = json.loads(path.read_text(encoding="utf-8"))
        return isinstance(specification, dict) and bool(specification)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False


@router.post("/sessions", response_model=WorkflowSessionOut)
async def create_workflow_session():
    session = memory_store.create_session()
    # Prepara o sandbox no momento em que a sessão nasce. Antes disso ele só
    # era criado quando o agente chamava uma ferramenta pela primeira vez.
    await _extrai_sandbox_dir(
        {
            "configurable": {
                "user_id": "workflow-demo-user",
                "thread_id": f"workflow-{session['id']}",
            }
        }
    )
    return session


@router.get("/sessions/{session_id}", response_model=WorkflowSessionOut)
async def get_workflow_session(session_id: str):
    return _session_or_404(session_id)


@router.websocket("/sessions/{session_id}/ws")
async def workflow_socket(websocket: WebSocket, session_id: str):
    """Transmite a resposta da LLM e sinaliza a conclusão com um evento done."""
    await websocket.accept()
    try:
        _session_or_404(session_id)
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
                if _advance_allowed(session_id, advance.from_agent):
                    payload = {
                        "type": "done",
                        "session_id": session_id,
                        "allowed": True,
                    }
                    payload.update(_workflow_artifacts(session_id, advance.from_agent))
                    await websocket.send_json(payload)
                    continue
                body = WorkflowMessageIn(
                    text=_advance_instruction(advance.from_agent),
                    agent_name=advance.from_agent,
                )
                payload = await _run_streamed_message(session_id, body, emit)
                payload["allowed"] = _advance_allowed(session_id, advance.from_agent)
                await websocket.send_json(payload)
                continue

            await websocket.send_json({"type": "error", "message": "Tipo de evento inválido."})
    except WebSocketDisconnect:
        return
    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except WebSocketDisconnect:
            return


@router.post("/sessions/{session_id}/messages", response_model=WorkflowReplyOut)
async def send_workflow_message(session_id: str, body: WorkflowMessageIn):
    session = _session_or_404(session_id)
    text = body.text.strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A mensagem não pode ficar vazia",
        )
    
    memory_store.add_message(
        session_id,
        role="user",
        content=text,
        agent_name=body.agent_name,
    )

    state = {
        "messages": _history(session["messages"]) + [HumanMessage(content=text)],
        "chat_id": f"workflow-{session_id}",
        "user_id": "workflow-demo-user",
        "context": None,
        "agent_name": body.agent_name,
        "selected_agent": None,
        "next_node": None,
    }

    try:
        # O ToolNode precisa receber a mesma identidade do chat para preparar
        # o sandbox correto. Sem esta configuração, execute_bash não consegue
        # resolver o diretório e falha antes de acessar planning.json.
        graph_config = {
            "configurable": {
                "thread_id": f"workflow-{session_id}",
                "user_id": "workflow-demo-user",
                "work_dir": str(workspace_for_chat("workflow-demo-user", f"workflow-{session_id}")),
            }
        }
        result = await GRAPH_BUILDER.ainvoke(state, config=graph_config)
        reply_text = _clean_agent_text(result["messages"][-1].content)
        
    except Exception:
        # A entrada do usuário já foi salva. Deixamos o erro chegar ao front
        # para que uma falha do provedor não seja confundida com resposta do agente.
        raise

    reply = memory_store.add_message(
        session_id,
        role="assistant",
        content=reply_text,
        agent_name=body.agent_name,
    )
    html_url = None
    if body.agent_name in {"debate", "generic", "lesson_plan", "political_leteracy"}:
        html_path = workspace_for_chat("workflow-demo-user", f"workflow-{session_id}") / "sandbox" / "HTML.html"
        if html_path.is_file():
            html_url = f"/api/workflow/sessions/{session_id}/html"
    return {"session_id": session_id, "message": reply, "html_url": html_url}


@router.post("/sessions/{session_id}/advance")
async def advance_workflow(session_id: str, body: WorkflowAdvanceIn):
    """Valida o arquivo obrigatório antes de trocar de agente."""
    if _advance_allowed(session_id, body.from_agent):
        payload = {
            "allowed": True,
            "session_id": session_id,
            "message": None,
        }
        payload.update(_workflow_artifacts(session_id, body.from_agent))
        return payload

    reply_data = await send_workflow_message(
        session_id,
        WorkflowMessageIn(text=_advance_instruction(body.from_agent), agent_name=body.from_agent),
    )
    allowed = _advance_allowed(session_id, body.from_agent)
    if allowed:
        return {"allowed": True, **reply_data}
    # Mantém a resposta original da LLM no chat. O backend apenas informa o
    # resultado da validação para o front decidir se libera a transição.
    return {"allowed": False, **reply_data}
