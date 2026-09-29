import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from graph.tools.sandbox.templates import consultar_templates
from graph.tools.sandbox.workdir import _copy_shared_files
from services.template_library import (
    TemplateLibrary, default_template_library, load_template_library,
    personal_template_library, sync_template_library,
)

OWNER = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
SESSION = "33333333-3333-4333-8333-333333333333"
TEMPLATE = "44444444-4444-4444-8444-444444444444"
SECOND = "55555555-5555-4555-8555-555555555555"


def row(template_id=TEMPLATE, html="<html><body>Base pessoal</body></html>"):
    return {"id": template_id, "title": "Modelo da turma", "html_content": html, "turma_ids": [OTHER]}


def config(teacher=OWNER):
    return {"configurable": {"user_id": "10", "thread_id": f"workflow-{SESSION}", "teacher_user_id": teacher}}


def database(owner=OWNER, rows=None):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={"owner_user_id": owner})
    conn.fetch = AsyncMock(return_value=[] if rows is None else rows)
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


class TemplateAccessTest(unittest.IsolatedAsyncioTestCase):
    async def test_personal_library_excludes_defaults_and_preserves_class_links(self):
        pool, conn = database(rows=[row(), row(SECOND)])
        with patch("services.template_library.get_pool", return_value=pool):
            library = await load_template_library(config())
        self.assertEqual(library.catalog["origem"], "professor")
        self.assertEqual(len(library.files), 2)
        self.assertTrue(all(name.startswith("professor-") for name in library.files))
        self.assertEqual(library.catalog["templates"][0]["turmas"], [OTHER])
        query = conn.fetch.await_args
        self.assertEqual(query.args[1], OWNER)
        self.assertIn("WHERE t.user_id=$1", query.args[0])
        self.assertIn("c.user_id=t.user_id", query.args[0])
        self.assertEqual(conn.fetchrow.await_args.args[1], SESSION)

    async def test_no_uploads_has_defaults_but_empty_personal_does_not(self):
        for rows, origin in (([], "padrao"), ([row(html="")], "professor")):
            pool, _ = database(rows=rows)
            with patch("services.template_library.get_pool", return_value=pool):
                library = await load_template_library(config())
            self.assertEqual(library.catalog["origem"], origin)
            if rows:
                self.assertFalse(library.catalog["templates"][0]["conteudo_disponivel"])

    async def test_private_session_requires_its_real_owner_not_legacy_user(self):
        for teacher in (OTHER, None, "10"):
            pool, conn = database(rows=[row()])
            with patch("services.template_library.get_pool", return_value=pool):
                with self.assertRaisesRegex(ValueError, "não autorizado"):
                    await load_template_library(config(teacher))
            conn.fetch.assert_not_called()

    async def test_public_session_never_receives_personal_templates(self):
        for teacher in (None, OWNER):
            pool, conn = database(owner=None, rows=[row()])
            with patch("services.template_library.get_pool", return_value=pool):
                library = await load_template_library(config(teacher))
            self.assertEqual(library.catalog["origem"], "padrao")
            conn.fetch.assert_not_called()

    async def test_missing_session_fails_closed(self):
        pool, conn = database()
        conn.fetchrow.return_value = None
        with patch("services.template_library.get_pool", return_value=pool):
            with self.assertRaisesRegex(ValueError, "Sessão não encontrada"):
                await load_template_library(config())
        conn.fetch.assert_not_called()

    async def test_upload_edits_and_deletion_are_reloaded(self):
        pool, conn = database()
        conn.fetch.side_effect = [[row()], [row(html="Atualizado")], []]
        with patch("services.template_library.get_pool", return_value=pool):
            first = await load_template_library(config())
            edited = await load_template_library(config())
            deleted = await load_template_library(config())
        filename = f"professor-{TEMPLATE}.html"
        self.assertNotEqual(first.files[filename], edited.files[filename])
        self.assertEqual(edited.files[filename], "Atualizado")
        self.assertEqual(deleted.catalog["origem"], "padrao")

    async def test_read_tool_catalog_html_allowlist_and_empty_file(self):
        personal = personal_template_library([row(), row(SECOND, html="")])
        with patch("graph.tools.sandbox.templates.load_template_library", AsyncMock(return_value=personal)):
            catalog = json.loads(await consultar_templates.ainvoke({}, config=config()))
            self.assertNotIn("<html>", json.dumps(catalog))
            filename = catalog["templates"][0]["arquivo"]
            output = json.loads(await consultar_templates.ainvoke({"arquivo": filename}, config=config()))
            self.assertEqual(output["html"], row()["html_content"])
            for forbidden in ("../HTML.html", "/etc/passwd", "templates.json", "plano-de-aula-blocos.html"):
                result = json.loads(await consultar_templates.ainvoke({"arquivo": forbidden}, config=config()))
                self.assertIn("erro", result)
            empty = json.loads(await consultar_templates.ainvoke({"arquivo": f"professor-{SECOND}.html"}, config=config()))
            self.assertIn("Não use padrões", empty["erro"])
        self.assertNotIn("teacher_user_id", consultar_templates.args)
        self.assertNotIn("config", consultar_templates.args)


class TemplateFilesTest(unittest.TestCase):
    def test_switch_default_personal_updated_personal_default_preserves_material(self):
        with tempfile.TemporaryDirectory() as folder:
            sandbox = Path(folder)
            current = '<section data-ied-page="1">Edição manual preservada</section>'
            (sandbox / "HTML.html").write_text(current)
            (sandbox / "planning.json").write_text("[]")
            standard = default_template_library()
            sync_template_library(sandbox, standard)
            self.assertTrue((sandbox / "templates/plano-de-aula-blocos.html").exists())
            personal = personal_template_library([row()])
            _copy_shared_files(sandbox, "lesson_plan", personal)
            expected = {"templates.json", f"professor-{TEMPLATE}.html"}
            self.assertEqual({p.name for p in (sandbox / "templates").iterdir()}, expected)
            _copy_shared_files(sandbox, "slides", personal)
            self.assertEqual({p.name for p in (sandbox / "templates").iterdir()}, expected | {"slide-template.html"})
            sync_template_library(sandbox, personal_template_library([row(SECOND, "Novo template")]))
            self.assertFalse((sandbox / "templates" / f"professor-{TEMPLATE}.html").exists())
            sync_template_library(sandbox, standard)
            self.assertEqual({p.name for p in (sandbox / "templates").iterdir()}, set(standard.files) | {"templates.json"})
            self.assertEqual((sandbox / "HTML.html").read_text(), current)
            self.assertEqual((sandbox / "planning.json").read_text(), "[]")

    def test_each_material_gets_only_personal_templates(self):
        for agent in ("brainstorm", "lesson_plan", "debate", "writing_workshop", "political_leteracy", "slides", "generic", "editor_geral"):
            with self.subTest(agent=agent), tempfile.TemporaryDirectory() as folder:
                sandbox = Path(folder)
                _copy_shared_files(sandbox, agent, personal_template_library([row()]))
                catalog = json.loads((sandbox / "templates/templates.json").read_text())
                self.assertEqual(catalog["origem"], "slides" if agent == "slides" else "professor")
                self.assertEqual(len(list((sandbox / "templates").glob("*.html"))), 2 if agent == "slides" else 1)

    def test_reject_directory_symlink_file_symlink_and_hardlink(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sandbox = root / "sandbox"
            sandbox.mkdir()
            outside = root / "outside"
            outside.mkdir()
            (outside / "templates.json").write_text("não tocar")
            (sandbox / "templates").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "link"):
                sync_template_library(sandbox, default_template_library())
            (sandbox / "templates").unlink()
            (sandbox / "templates").mkdir()
            path = sandbox / "templates/templates.json"
            path.symlink_to(outside / "templates.json")
            with self.assertRaises(ValueError):
                sync_template_library(sandbox, default_template_library())
            path.unlink()
            os.link(outside / "templates.json", path)
            with self.assertRaises(ValueError):
                sync_template_library(sandbox, default_template_library())
            self.assertEqual((outside / "templates.json").read_text(), "não tocar")

    def test_refuses_invalid_file_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "Nome inválido"):
                sync_template_library(Path(folder), TemplateLibrary({}, {"../escape.html": "bad"}))


if __name__ == "__main__":
    unittest.main()
