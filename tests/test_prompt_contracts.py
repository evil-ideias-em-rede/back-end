"""Contratos dos prompts e do acervo, sem chamadas de LLM ou sessões reais."""
import importlib
import json
import re
import tempfile
import unittest
from pathlib import Path

from graph.agent.prompts.loader import render, render_for_agent
from graph.agent.prompts.material_rules import MATERIAL_RULES
from graph.tools.sandbox.workdir import SHARED_FILES_DIR, _copy_shared_files

PROMPT_ROOT = Path(__file__).resolve().parents[1] / "graph/agent/prompts"


class PromptContractsTest(unittest.TestCase):
    def test_all_chat_compositions_import_and_resolve(self):
        count = 0
        for mode in ("editor", "audiencias_sugeridas"):
            for path in (PROMPT_ROOT / mode).glob("*_prompt.py"):
                with self.subTest(mode=mode, file=path.name):
                    module = importlib.import_module(
                        f"graph.agent.prompts.{mode}.{path.stem}"
                    )
                    prompts = [v for k, v in vars(module).items()
                               if k.endswith("_PROMPT") and isinstance(v, str)]
                    self.assertEqual(len(prompts), 1)
                    prompt = prompts[0]
                    self.assertNotRegex(prompt, r"\{\{[A-Z_]+\}\}")
                    self.assertNotIn("<output_format>", prompt)
                    self.assertIn("HTML.html", prompt)
                    if mode == "editor":
                        self.assertIn("guia_edicao.md", prompt)
                        self.assertIn("templates/templates.json", prompt)
                        self.assertIn("teorias/_indice.md", prompt)
                        self.assertIn("dados/bncc.csv", prompt)
                    elif path.name == "brain_storm_prompt.py":
                        self.assertIn("somente planning.json", prompt)
                        self.assertIn("Não gere, escreva, altere ou apague HTML.html", prompt)
                        self.assertNotIn("GERAÇÃO NA TELA", prompt)
                    else:
                        self.assertIn("somente planning.json e HTML.html", prompt)
                    count += 1
        self.assertEqual(count, 14)

    def test_structured_library_keeps_its_output_contract(self):
        raw = render("20-plano-de-aula")
        chat = render_for_agent("20-plano-de-aula")
        self.assertIn("<output_format>", raw)
        self.assertNotIn("<output_format>", chat)
        self.assertIn("Case objetivos e habilidades", chat)
        self.assertIn("<pedagogical_principles>", chat)
        self.assertIn("<source_rules>", chat)

    def test_planning_example_is_valid_json(self):
        from graph.agent.prompts.audiencias_sugeridas.rules import PLANNING_RULES
        example = re.search(r"\[\n.*?\n\]", PLANNING_RULES, re.S).group()
        rows = json.loads(example)
        self.assertEqual(set(rows[0]), {"id", "titulo", "resumo", "assunto"})

    def test_every_concrete_profile_reference_exists(self):
        pattern = r"(?:templates|formatos-de-aula|teorias)/[\w-]+\.(?:md|html|json)"
        for material, text in MATERIAL_RULES.items():
            for relative in re.findall(pattern, text):
                with self.subTest(material=material, path=relative):
                    self.assertTrue((SHARED_FILES_DIR / "geral" / relative).is_file())

    def test_acervo_reaches_every_editor_without_overwriting_material(self):
        agents = ("brainstorm", "lesson_plan", "debate", "writing_workshop",
                  "political_leteracy", "slides", "generic", "editor_geral")
        for agent in agents:
            with self.subTest(agent=agent), tempfile.TemporaryDirectory() as temp:
                sandbox = Path(temp)
                current = '<html><body><section data-ied-page="1">Edição manual</section></body></html>'
                (sandbox / "HTML.html").write_text(current, encoding="utf-8")
                _copy_shared_files(sandbox, agent)
                for relative in ("guia_edicao.md", "templates/templates.json",
                                 "formatos-de-aula/_indice.md", "teorias/_indice.md",
                                 "dados/bncc.csv", "validar_html_pdf.md"):
                    self.assertTrue((sandbox / relative).is_file(), relative)
                catalog = json.loads((sandbox / "templates/templates.json").read_text())
                for item in catalog["templates"]:
                    self.assertTrue((sandbox / "templates" / item["arquivo"]).is_file())
                self.assertEqual((sandbox / "HTML.html").read_text(), current)
                if agent == "slides":
                    self.assertTrue((sandbox / "estrutura_slides.md").is_file())


if __name__ == "__main__":
    unittest.main()
