import unittest
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.exceptions import ContextOverflowError


class WorkflowErrorsTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        with patch("tiktoken.get_encoding", return_value=MagicMock()):
            from routers import workflow_router, workflow_messages_router
        cls.workflow = workflow_router
        cls.messages = workflow_messages_router

    async def test_failed_generation_returns_json_with_cors_and_keeps_user_message(self):
        for error, status_code, detail in (
            (ContextOverflowError("context too long"), 422, "grande demais"),
            (RuntimeError("private provider diagnostics"), 502, "Sua mensagem foi salva"),
        ):
            with self.subTest(error=type(error).__name__), ExitStack() as stack:
                router = self.workflow
                for name in ("_ensure_session_access", "_extrai_sandbox_dir", "persist_workflow_files"):
                    stack.enter_context(patch.object(router, name, AsyncMock()))
                stack.enter_context(patch.object(router, "_ensure_session", AsyncMock(
                    return_value={"messages": [], "selected_agent": "lesson_plan"})))
                stack.enter_context(patch.object(router, "load_teacher_context", AsyncMock(return_value=None)))
                persisted = stack.enter_context(patch.object(router, "_persist_workflow_message", AsyncMock()))
                stack.enter_context(patch.object(router.memory_store, "add_message", MagicMock()))
                graph = stack.enter_context(patch.object(router.GRAPH_BUILDER, "ainvoke", AsyncMock(side_effect=error)))
                stack.enter_context(patch.object(router.logger, "exception"))
                app = FastAPI()
                app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
                app.include_router(self.messages.router)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                    response = await client.post(
                        "/api/workflow/sessions/test/messages",
                        json={"text": "Gere o material", "agent_name": "lesson_plan"},
                        headers={"Origin": "http://127.0.0.1:5173"},
                    )
                self.assertEqual(response.status_code, status_code)
                self.assertEqual(response.headers["access-control-allow-origin"], "*")
                self.assertIn(detail, response.json()["detail"])
                self.assertNotIn("private provider", response.text)
                graph.assert_awaited_once()
                persisted.assert_awaited_once_with("test", "lesson_plan", "user", "Gere o material", False)
