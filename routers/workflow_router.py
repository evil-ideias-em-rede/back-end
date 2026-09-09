from typing import Literal
import json
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
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
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _history(rows: list[dict]) -> list:
    message_types = {"user": HumanMessage, "assistant": AIMessage}
    return [message_types[row["role"]](content=row["content"]) for row in rows]


def _message_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") in {"text", "output_text"}:
                parts.append(str(item.get("text", "")))
        if parts:
            return "\n".join(part for part in parts if part)
    return str(content)


def _session_or_404(session_id: str) -> dict:
    try:
        return memory_store.snapshot(session_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sessão não encontrada na memória do servidor",
        ) from exc


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


@router.get("/sessions/{session_id}/html")
async def get_workflow_html(session_id: str):
    """Entrega o HTML produzido no sandbox da sessão atual."""
    _session_or_404(session_id)
    html_path = workspace_for_chat("workflow-demo-user", f"workflow-{session_id}") / "sandbox" / "HTML.html"
    if not html_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="HTML.html ainda não foi gerado")
    return FileResponse(html_path, media_type="text/html", headers={"Cache-Control": "no-store"})


@router.get("/sessions/{session_id}/{filename:path}")
async def get_workflow_asset(session_id: str, filename: str):
    """Serve imagens e outros arquivos anexados usados pelo HTML da sessão."""
    _session_or_404(session_id)
    relative_name = filename.removeprefix("sandbox/")
    asset_path = (workspace_for_chat("workflow-demo-user", f"workflow-{session_id}") / "sandbox" / relative_name).resolve()
    sandbox_dir = (workspace_for_chat("workflow-demo-user", f"workflow-{session_id}") / "sandbox").resolve()
    try:
        asset_path.relative_to(sandbox_dir)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado") from exc
    if not asset_path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    return FileResponse(asset_path, headers={"Cache-Control": "no-store"})


@router.post("/sessions/{session_id}/files")
async def upload_workflow_file(session_id: str, file: UploadFile = File(...)):
    """Salva um anexo no sandbox da sessão para o agente poder acessá-lo."""
    _session_or_404(session_id)
    filename = Path(file.filename or "").name
    if not filename or filename in {".", ".."}:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido")

    sandbox_dir = workspace_for_chat("workflow-demo-user", f"workflow-{session_id}") / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    target = sandbox_dir / filename
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="O arquivo deve ter no máximo 20 MB")
    target.write_bytes(content)
    return {"filename": filename, "sandbox_path": f"sandbox/{filename}", "size": len(content)}


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
        reply_text = _message_text(result["messages"][-1].content)
        
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
    required_file = "planning.json" if body.from_agent == "brainstorm" else "SPECIFICATION.md"
    instruction = (
        "O usuário solicitou avançar para o próximo agente. "
        f"Verifique se {required_file} está completo no sandbox. "
        f"Se não existir ou estiver incompleto, informe quais dados faltam. "
        f"Se houver informações suficientes, gere ou atualize {required_file}, leia o arquivo novamente, "
        "confirme que está correto e peça ao usuário para tentar avançar novamente."
    )
    reply_data = await send_workflow_message(
        session_id,
        WorkflowMessageIn(text=instruction, agent_name=body.from_agent),
    )
    required_path = workspace_for_chat("workflow-demo-user", f"workflow-{session_id}") / "sandbox" / required_file
    allowed = False
    if body.from_agent == "brainstorm":
        try:
            planning = json.loads(required_path.read_text(encoding="utf-8"))
            allowed = (
                isinstance(planning, list)
                and any(isinstance(item, dict) and item.get("user_has_accepted") is True for item in planning)
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            allowed = False
    else:
        try:
            allowed = required_path.is_file() and bool(required_path.read_text(encoding="utf-8").strip())
        except (OSError, UnicodeDecodeError):
            allowed = False
    if allowed:
        return {"allowed": True, **reply_data}
    # Mantém a resposta original da LLM no chat. O backend apenas informa o
    # resultado da validação para o front decidir se libera a transição.
    return {"allowed": False, **reply_data}
