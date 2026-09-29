import importlib.util
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage
from services.template_library import personal_template_library


@unittest.skipUnless(importlib.util.find_spec("microsandbox"), "grafo completo disponível no container")
class TemplateGraphTest(unittest.IsolatedAsyncioTestCase):
    async def test_template_read_tool_is_bound_and_executed_in_both_modes(self):
        with patch("tiktoken.get_encoding", return_value=MagicMock()):
            from graph.main import GRAPH_BUILDER
        library = personal_template_library([{
            "id": "44444444-4444-4444-8444-444444444444", "title": "Base da professora",
            "html_content": "<html><body>Meu template</body></html>", "turma_ids": [],
        }])
        for editor in (False, True):
            prompts, results, bound = [], [], []
            async def stream(messages, **kwargs):
                prompts.append(messages[0].content)
                tool_messages = [message for message in messages if isinstance(message, ToolMessage)]
                if not tool_messages:
                    yield AIMessageChunk(content="", tool_call_chunks=[{
                        "name": "consultar_templates", "args": "{}", "id": "catalog-call", "index": 0,
                    }])
                elif len(tool_messages) == 1:
                    catalog = json.loads(tool_messages[-1].content)
                    results.append(catalog)
                    yield AIMessageChunk(content="", tool_call_chunks=[{
                        "name": "consultar_templates", "args": json.dumps({"arquivo": catalog["templates"][0]["arquivo"]}),
                        "id": "html-call", "index": 0,
                    }])
                else:
                    results.append(json.loads(tool_messages[-1].content))
                    yield AIMessageChunk(content="Base lida.")

            model = MagicMock()
            def bind_tools(tools):
                bound.append([tool.name for tool in tools])
                result = MagicMock()
                result.astream = stream
                return result
            model.bind_tools.side_effect = bind_tools
            settings = {"user_id": "10", "thread_id": "template-test", "teacher_user_id": "owner", "agent_name": "lesson_plan_node"}
            state = {"messages": [HumanMessage(content="Crie um plano com meu template.")],
                     "user_id": "10", "chat_id": "template-test", "agent_name": "lesson_plan_node",
                     "editor_mode": editor, "user_edited": False}
            loader = AsyncMock(return_value=library)
            with patch("graph.agent.base.get_chat_model", return_value=model), patch("graph.tools.sandbox.templates.load_template_library", loader):
                result = await GRAPH_BUILDER.ainvoke(state, {"configurable": settings})
            self.assertEqual(result["messages"][-1].content, "Base lida.")
            self.assertEqual(results[0]["origem"], "professor")
            self.assertEqual(results[1]["html"], "<html><body>Meu template</body></html>")
            self.assertTrue(all("consultar_templates" in names for names in bound))
            self.assertTrue(all("USO OBRIGATÓRIO DE TEMPLATE COMO BASE" in prompt for prompt in prompts))
            for call in loader.await_args_list:
                self.assertEqual(call.args[0]["configurable"]["teacher_user_id"], "owner")


if __name__ == "__main__":
    unittest.main()
