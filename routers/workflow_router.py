from typing import Literal

from fastapi import APIRouter, HTTPException, status
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from db.memory_store import memory_store
from graph.main import GRAPH_BUILDER
from graph.tools.sandbox.workdir import workspace_for_chat


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


class WorkflowSessionOut(BaseModel):
    id: str
    created_at: str
    messages: list[dict]


class WorkflowReplyOut(BaseModel):
    session_id: str
    message: dict


router = APIRouter(prefix="/api/workflow", tags=["workflow"])


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
    return memory_store.create_session()


@router.get("/sessions/{session_id}", response_model=WorkflowSessionOut)
async def get_workflow_session(session_id: str):
    return _session_or_404(session_id)


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
    return {"session_id": session_id, "message": reply}
