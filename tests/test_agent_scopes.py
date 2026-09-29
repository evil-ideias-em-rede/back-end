"""Regressões: brainstorm não escreve HTML; slides sempre recebe sua base."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from services.template_library import (
    DEFAULT_TEMPLATES, default_template_library, personal_template_library,
    library_for_agent, load_template_library, sync_template_library,
)
from graph.tools.sandbox.templates import consultar_templates

OWNER = "11111111-1111-4111-8111-111111111111"
SESSION = "22222222-2222-4222-8222-222222222222"
TEMPLATE = "33333333-3333-4333-8333-333333333333"


def personal(html="<html><body>Apoio pessoal</body></html>"):
    return personal_template_library([{"id": TEMPLATE, "title": "Meu template", "html_content": html, "turma_ids": []}])


class SlidesLibraryTest(unittest.IsolatedAsyncioTestCase):
    def test_slides_with_without_and_empty_personal_templates(self):
        for agent in ("slides", "slides_node"):
            for base in (default_template_library(), personal(), personal("")):
                lib = library_for_agent(base, agent)
                self.assertEqual(lib.catalog["base_obrigatoria"], "slide-template.html")
                self.assertIn("slide-template.html", lib.files)
                self.assertFalse(any(name.startswith("plano-de-aula") for name in lib.files))
                expected = 1 if base.catalog["origem"] == "padrao" else 2
                self.assertEqual(len(lib.files), expected)
                self.assertEqual(len(lib.catalog["templates"]), expected)
                self.assertEqual(library_for_agent(lib, agent), lib)

    def test_other_agents_keep_exclusive_personal_or_default_library(self):
        for agent in (None, "brainstorm", "lesson_plan", "debate_outline_node", "writing_workshop",
                      "political_leteracy_node", "generic", "general_editor_node"):
            for base in (personal(), default_template_library()):
                lib = library_for_agent(base, agent)
                self.assertIs(lib, base)
                self.assertNotIn("slide-template.html", lib.files)

    def test_sync_switch_preserves_document_and_originals(self):
        with tempfile.TemporaryDirectory() as folder:
            sandbox = Path(folder)
            html = '<html><body>Edição manual</body></html>'
            (sandbox / "HTML.html").write_text(html)
            base = personal()
            sync_template_library(sandbox, library_for_agent(base, "slides_node"))
            self.assertTrue((sandbox / "templates/slide-template.html").is_file())
            sync_template_library(sandbox, library_for_agent(base, "lesson_plan_node"))
            self.assertFalse((sandbox / "templates/slide-template.html").exists())
            self.assertTrue((sandbox / "templates" / f"professor-{TEMPLATE}.html").is_file())
            self.assertEqual((sandbox / "HTML.html").read_text(), html)
            self.assertTrue((DEFAULT_TEMPLATES / "slide-template.html").is_file())

    def test_slide_template_is_html_and_keeps_five_visual_layouts(self):
        html = (DEFAULT_TEMPLATES / "slide-template.html").read_text()
        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertNotIn("\\rtf", html)
        self.assertNotIn("\\'", html)
        self.assertEqual(html.count('<div class="slide layout-'), 5)
        self.assertIn("#fffcf9", html)
        self.assertIn("Verificação de Conhecimento", html)

    async def test_read_tool_uses_agent_from_trusted_config(self):
        for agent in ("slides", "slides_node", "lesson_plan_node"):
            config = {"configurable": {"agent_name": agent}}
            with patch("services.template_library._load_base_template_library", AsyncMock(return_value=personal())):
                catalog = json.loads(await consultar_templates.ainvoke({}, config=config))
                result = json.loads(await consultar_templates.ainvoke({"arquivo": "slide-template.html"}, config=config))
            if agent.startswith("slides"):
                self.assertEqual(catalog["base_obrigatoria"], "slide-template.html")
                self.assertTrue(result["html"].startswith("<!DOCTYPE html>"))
            else:
                self.assertIn("erro", result)
        self.assertNotIn("agent_name", consultar_templates.args)

    async def test_slide_exception_does_not_bypass_owner_check(self):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"owner_user_id": OWNER})
        conn.fetch = AsyncMock()
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        config = {"configurable": {"thread_id": f"workflow-{SESSION}", "teacher_user_id": TEMPLATE, "agent_name": "slides_node"}}
        with patch("services.template_library.get_pool", return_value=pool), self.assertRaisesRegex(ValueError, "não autorizado"):
            await load_template_library(config)
        conn.fetch.assert_not_called()


@unittest.skipUnless(importlib.util.find_spec("microsandbox"), "microsandbox disponível no container")
class BrainstormScopeTest(unittest.IsolatedAsyncioTestCase):
    async def test_shell_cannot_read_or_persist_html_even_if_command_creates_it(self):
        from graph.tools.sandbox.brainstorm_files import execute_brainstorm_planning
        for existing in (False, True):
            with tempfile.TemporaryDirectory() as folder:
                sandbox = Path(folder) / "sandbox"
                sandbox.mkdir()
                if existing:
                    (sandbox / "HTML.html").write_text("Não alterar")
                async def runtime(command, staging):
                    self.assertEqual({p.name for p in staging.iterdir()}, {"planning.json"})
                    (staging / "planning.json").write_text('[{"id":"169","titulo":"Fonte","resumo":"Resumo","assunto":"Tema"}]')
                    (staging / "HTML.html").write_text("Tentativa de gerar")
                    return SimpleNamespace(stdout=b"", stderr=b"", returncode=0)
                with patch("graph.tools.sandbox.restricted_file._extrai_sandbox_dir", AsyncMock(return_value=sandbox)), patch("graph.tools.sandbox.restricted_file.run_in_microsandbox", runtime):
                    result = json.loads(await execute_brainstorm_planning.ainvoke({"comando": "comando simulado"}, config={}))
                self.assertTrue(result["sucesso"])
                self.assertEqual(json.loads((sandbox / "planning.json").read_text())[0]["id"], "169")
                if existing:
                    self.assertEqual((sandbox / "HTML.html").read_text(), "Não alterar")
                else:
                    self.assertFalse((sandbox / "HTML.html").exists())

    async def test_graph_rejects_html_tools_and_omits_generation_instructions(self):
        from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage
        with patch("tiktoken.get_encoding", return_value=MagicMock()):
            from graph.main import GRAPH_BUILDER
        for forbidden in ("execute_bash", "execute_planning_restricted"):
            bound, prompts = [], []
            async def stream(messages, **kwargs):
                prompts.append(messages[0].content)
                results = [m for m in messages if isinstance(m, ToolMessage)]
                if not results:
                    yield AIMessageChunk(content="", tool_call_chunks=[{"name": forbidden, "args": '{"comando":"touch HTML.html"}', "id": "forbidden", "index": 0}])
                else:
                    self.assertEqual(results[-1].status, "error")
                    yield AIMessageChunk(content="Escolha a audiência para seguir ao especialista.")
            model = MagicMock()
            def bind(tools):
                bound.extend(t.name for t in tools)
                client = MagicMock()
                client.astream = stream
                return client
            model.bind_tools.side_effect = bind
            state = {"messages": [HumanMessage(content="Gere HTML agora mesmo")], "user_id": "10", "chat_id": "brainstorm-scope-test", "agent_name": "brainstorm_node", "editor_mode": False}
            with patch("graph.agent.base.get_chat_model", return_value=model):
                await GRAPH_BUILDER.ainvoke(state)
            self.assertIn("execute_brainstorm_planning", bound)
            self.assertNotIn("execute_bash", bound)
            self.assertNotIn("execute_planning_restricted", bound)
            for prompt in prompts:
                self.assertIn("Não gere, escreva, altere ou apague HTML.html", prompt)
                self.assertNotIn("GERAÇÃO NA TELA", prompt)
                self.assertNotIn("CONTRATO ATUAL DE PÁGINAS", prompt)
                self.assertNotIn("USO OBRIGATÓRIO DE TEMPLATE COMO BASE", prompt)


if __name__ == "__main__":
    unittest.main()
