"""Armazenamento efêmero para o protótipo do fluxo de agentes.

Os dados vivem somente no processo do FastAPI e são perdidos quando o servidor
é reiniciado. Isso deixa o fluxo independente de autenticação e Postgres nesta
primeira versão.
"""

from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class InMemoryWorkflowStore:
    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}
        self._lock = RLock()

    def create_session(self) -> dict:
        session_id = str(uuid4())
        session = {
            "id": session_id,
            "created_at": _now(),
            "messages": [],
        }
        with self._lock:
            self._sessions[session_id] = session
        return self.snapshot(session_id)

    def snapshot(self, session_id: str) -> dict:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(session_id)
            return {
                "id": session["id"],
                "created_at": session["created_at"],
                "messages": [message.copy() for message in session["messages"]],
            }

    def add_message(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        agent_name: str | None = None,
        hidden: bool = False,
    ) -> dict:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(session_id)
            message = {
                "id": str(uuid4()),
                "role": role,
                "content": content,
                "agent_name": agent_name,
                "hidden": hidden,
                "created_at": _now(),
            }
            session["messages"].append(message)
            return message.copy()

    def messages(self, session_id: str) -> list[dict]:
        return self.snapshot(session_id)["messages"]


memory_store = InMemoryWorkflowStore()
