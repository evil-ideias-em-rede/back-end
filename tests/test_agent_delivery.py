import unittest
import importlib.util
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessageChunk


@unittest.skipUnless(importlib.util.find_spec("microsandbox"), "microsandbox disponível no container")
class AgentDeliveryTest(unittest.IsolatedAsyncioTestCase):
    async def test_context_and_page_rules_in_both_modes(self):
        # As ferramentas de busca não são usadas neste teste. Evite download
        # do tokenizer durante o import em ambientes sem rede.
        with patch("tiktoken.get_encoding", return_value=MagicMock()):
            from graph.agent.base import run_agent
        for editor in (False, True):
            captured = []

            async def stream(messages, **kwargs):
                captured.extend(messages)
                yield AIMessageChunk(content="Pronto.")

            model = MagicMock()
            model.bind_tools.return_value.astream = stream
            state = {"user_id": "10", "chat_id": "teste-sem-escrita",
                     "editor_mode": editor, "context": "Turma B: 32 alunos", "messages": []}
            with patch("graph.agent.base.get_chat_model", return_value=model):
                await run_agent(state, "Prompt específico", tools=[])
            prompt = captured[0].content
            self.assertIn("Turma B: 32 alunos", prompt)
            self.assertIn("CONTRATO ATUAL DE PÁGINAS", prompt)
            self.assertIn("USO OBRIGATÓRIO DE TEMPLATE COMO BASE", prompt)
            self.assertIn("consultar_templates", [tool.name for tool in model.bind_tools.call_args.args[0]])
            self.assertEqual("até 80 palavras" in prompt, not editor)
