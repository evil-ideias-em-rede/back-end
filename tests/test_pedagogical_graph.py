"""Exercita os ToolNodes reais com LLM simulada, sem rede nem uso de créditos."""
import importlib.util
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage


@unittest.skipUnless(importlib.util.find_spec("microsandbox"), "grafo completo disponível no container")
class PedagogicalGraphTest(unittest.IsolatedAsyncioTestCase):
    async def test_every_agent_reads_references_materials_and_bncc_in_both_modes(self):
        with patch("tiktoken.get_encoding", return_value=MagicMock()):
            from graph.main import GRAPH_BUILDER, AGENT_NAMES
        calls = [
            ("consultar_acervo", {"arquivo": "guia_consulta.md"}),
            ("consultar_acervo", {"arquivo": "teorias/_indice.md"}),
            ("consultar_materiais_professor", {}),
            ("consultar_bncc", {"etapa": "fundamental", "ano": "6", "componente": "Ciências"}),
        ]
        for agent in AGENT_NAMES:
            # O editor geral não possui tela de audiências sugeridas por contrato.
            for editor in ((True,) if agent == "general_editor_node" else (False, True)):
                with self.subTest(agent=agent, editor=editor):
                    bound, prompts = [], []

                    async def stream(messages, **kwargs):
                        prompts.append(messages[0].content)
                        results = [m for m in messages if isinstance(m, ToolMessage)]
                        if len(results) < len(calls):
                            name, args = calls[len(results)]
                            yield AIMessageChunk(content="", tool_call_chunks=[{
                                "name": name, "args": json.dumps(args), "id": f"read-{len(results)}", "index": 0,
                            }])
                        else:
                            self.assertIn("Consulta seletiva", results[0].content)
                            self.assertIn("ausubel.md", results[1].content)
                            self.assertIn("Apoio autorizado", results[2].content)
                            self.assertIn("EF06CI", results[3].content)
                            yield AIMessageChunk(content="Referências consultadas.")

                    def bind_tools(tools):
                        bound.append({tool.name for tool in tools})
                        client = MagicMock()
                        client.astream = stream
                        return client

                    model = MagicMock()
                    model.bind_tools.side_effect = bind_tools
                    state = {"messages": [HumanMessage(content="Prepare a atividade com minhas fontes.")],
                             "user_id": "10", "chat_id": "reference-test", "agent_name": agent,
                             "editor_mode": editor, "user_edited": False}
                    settings = {"configurable": {"teacher_user_id": "trusted-owner"}}
                    loader = AsyncMock(return_value={"materiais": [{"titulo": "Apoio autorizado"}]})
                    with patch("graph.agent.base.get_chat_model", return_value=model), patch("graph.tools.sandbox.teacher_materials.read_teacher_materials", loader):
                        result = await GRAPH_BUILDER.ainvoke(state, settings)
                    self.assertEqual(result["messages"][-1].content, "Referências consultadas.")
                    self.assertTrue(all({"consultar_acervo", "consultar_templates", "consultar_materiais_professor", "consultar_bncc"} <= names for names in bound))
                    expected_scope = "BRAINSTORM: SOMENTE EXPLORAÇÃO" if agent == "brainstorm_node" else "CONSULTA PEDAGÓGICA ANTES DE GERAR"
                    self.assertTrue(all(expected_scope in prompt for prompt in prompts))
                    self.assertEqual(loader.await_args.args[0]["configurable"]["teacher_user_id"], "trusted-owner")


if __name__ == "__main__":
    unittest.main()
