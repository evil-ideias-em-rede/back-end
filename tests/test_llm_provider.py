import json
import os
import unittest
from unittest.mock import patch

import httpx
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from services.install_config import validate_install_config
from services.llm import create_chat_model, create_structured_model, generate_text, get_llm_config


ENV = {
    "LLM_PROVIDER": "deepinfra",
    "DEEPINFRA_MODEL": "XiaomiMiMo/MiMo-V2.6-Pro",
    "DEEPINFRA_API_KEY": "fake-deepinfra-key",
    "OPENAI_MODEL_NAME": "test-openai-model",
    "OPENAI_API_KEY": "fake-openai-key",
}


class Result(BaseModel):
    """Resultado de teste."""
    text: str


class ProviderTest(unittest.TestCase):
    def test_selection_defaults_alias_and_no_secret_in_repr(self):
        config = get_llm_config(ENV)
        self.assertEqual(config.provider, "deepinfra")
        self.assertEqual(config.model, ENV["DEEPINFRA_MODEL"])
        self.assertEqual(config.base_url, "https://api.deepinfra.com/v1/openai")
        self.assertNotIn(ENV["DEEPINFRA_API_KEY"], repr(config))
        legacy = {"OPENAI_MODEL": "legacy-model", "OPENAI_API_KEY": "test"}
        self.assertEqual(get_llm_config(legacy).model, "legacy-model")
        self.assertEqual(get_llm_config(legacy).provider, "openai")
        self.assertEqual(get_llm_config(ENV, model="override").model, "override")

    def test_invalid_or_missing_config_never_falls_back(self):
        for provider, prefix, model_key in (("deepinfra", "DEEPINFRA", "DEEPINFRA_MODEL"), ("openai", "OPENAI", "OPENAI_MODEL_NAME")):
            for key in (f"{prefix}_API_KEY", model_key):
                with self.subTest(provider=provider, key=key):
                    env = dict(ENV, LLM_PROVIDER=provider)
                    env.pop(key)
                    with self.assertRaisesRegex(ValueError, key):
                        get_llm_config(env)
        for provider in ("", "unknown"):
            with self.assertRaisesRegex(ValueError, "LLM_PROVIDER"):
                get_llm_config(dict(ENV, LLM_PROVIDER=provider))

    def test_installation_requires_selected_provider_and_embedding_key(self):
        env = dict(ENV, APP_ENV="installation", DATABASE_URL="postgresql://app:pass@db/app", JWT_SECRET="a" * 64)
        env.pop("OPENAI_MODEL_NAME")
        validate_install_config(env)
        env.pop("OPENAI_API_KEY")
        with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY"):
            validate_install_config(env)

    def test_deepinfra_text_wire_format_and_credential_isolation(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={"id": "chat-test", "object": "chat.completion", "created": 1,
                "model": ENV["DEEPINFRA_MODEL"], "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": "SELECT 1"}}]})
        # OPENAI_BASE_URL must not redirect DeepInfra credentials.
        with patch.dict(os.environ, dict(ENV, OPENAI_BASE_URL="https://wrong.example/v1"), clear=True), httpx.Client(transport=httpx.MockTransport(handler)) as client:
            model = create_chat_model(http_client=client, max_retries=0)
            with patch("services.llm.create_chat_model", return_value=model):
                self.assertEqual(generate_text("SQL"), "SELECT 1")
        request = requests[0]
        self.assertEqual(str(request.url), "https://api.deepinfra.com/v1/openai/chat/completions")
        self.assertEqual(request.headers["authorization"], "Bearer fake-deepinfra-key")
        body = json.loads(request.content)
        self.assertEqual(body["model"], ENV["DEEPINFRA_MODEL"])
        self.assertIn("messages", body)
        self.assertNotIn("input", body)

    def test_openai_keeps_responses_wire_format(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={"id": "resp_test", "object": "response", "created_at": 1,
                "status": "completed", "model": "test-openai-model", "error": None, "usage": None,
                "output": [{"id": "msg_test", "type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": "SELECT 2", "annotations": []}]}]})
        with patch.dict(os.environ, dict(ENV, LLM_PROVIDER="openai"), clear=True), httpx.Client(transport=httpx.MockTransport(handler)) as client:
            model = create_chat_model(http_client=client, max_retries=0)
            with patch("services.llm.create_chat_model", return_value=model):
                self.assertEqual(generate_text("SQL"), "SELECT 2")
        request = requests[0]
        self.assertEqual(str(request.url), "https://api.openai.com/v1/responses")
        self.assertEqual(request.headers["authorization"], "Bearer fake-openai-key")
        self.assertEqual(json.loads(request.content)["model"], "test-openai-model")
        self.assertIn("input", json.loads(request.content))

    def test_structured_deepinfra_uses_tools_and_parses_schema(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={"id": "chat-test", "object": "chat.completion", "created": 1,
                "model": ENV["DEEPINFRA_MODEL"], "choices": [{"index": 0, "finish_reason": "tool_calls",
                "message": {"role": "assistant", "content": None, "tool_calls": [{"id": "call_test", "type": "function",
                "function": {"name": "Result", "arguments": '{"text":"ok"}'}}]}}]})
        with patch.dict(os.environ, ENV, clear=True), httpx.Client(transport=httpx.MockTransport(handler)) as client:
            model = create_chat_model(http_client=client, max_retries=0)
            with patch("services.llm.create_chat_model", return_value=model):
                result = create_structured_model(Result).invoke("Teste")
        self.assertEqual(result.text, "ok")
        body = json.loads(requests[0].content)
        self.assertEqual(body["tools"][0]["function"]["name"], "Result")
        self.assertNotIn("response_format", body)

    def test_text_rejects_empty_response_and_ignores_reasoning(self):
        with patch("services.llm.create_chat_model") as factory:
            factory.return_value.invoke.return_value = AIMessage(content=[
                {"type": "reasoning", "text": "não exibir"}, {"type": "text", "text": "visível"}])
            self.assertEqual(generate_text("prompt"), "visível")
            factory.return_value.invoke.return_value = AIMessage(content="")
            with self.assertRaisesRegex(ValueError, "sem texto"):
                generate_text("prompt")


class StreamingTest(unittest.IsolatedAsyncioTestCase):
    async def test_deepinfra_streams_tool_call_and_followup(self):
        requests = []
        def handler(request):
            body = json.loads(request.content)
            requests.append(body)
            if len(requests) == 1:
                deltas = [
                    {"role": "assistant", "tool_calls": [{"index": 0, "id": "call_test", "type": "function", "function": {"name": "Result", "arguments": ""}}]},
                    {"tool_calls": [{"index": 0, "function": {"arguments": '{"text":"ok"}'}}]},
                ]
                finish = "tool_calls"
            else:
                deltas = [{"role": "assistant", "content": "Pron"}, {"content": "to."}]
                finish = "stop"
            events = []
            for delta in deltas + [{}]:
                payload = {"id": "chat-test", "object": "chat.completion.chunk", "created": 1,
                    "model": ENV["DEEPINFRA_MODEL"], "choices": [{"index": 0, "delta": delta,
                    "finish_reason": finish if not delta else None}]}
                events.append("data: " + json.dumps(payload) + "\n\n")
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, text="".join(events) + "data: [DONE]\n\n")
        with patch.dict(os.environ, ENV, clear=True):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                model = create_chat_model(http_async_client=client, max_retries=0).bind_tools([Result])
                chunks = [chunk async for chunk in model.astream([HumanMessage(content="Teste")])]
                message = chunks[0]
                for chunk in chunks[1:]:
                    message += chunk
                self.assertEqual(message.tool_calls[0]["args"], {"text": "ok"})
                followup = [HumanMessage(content="Teste"), message, ToolMessage(content="ok", tool_call_id="call_test")]
                text = "".join([chunk.content async for chunk in model.astream(followup)])
        self.assertEqual(text, "Pronto.")
        self.assertTrue(requests[0]["stream"])
        self.assertEqual(requests[1]["messages"][-1]["role"], "tool")
        self.assertEqual(requests[1]["messages"][-1]["tool_call_id"], "call_test")


if __name__ == "__main__":
    unittest.main()
