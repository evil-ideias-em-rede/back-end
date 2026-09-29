import csv
import importlib.util
import json
from io import BytesIO
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from zipfile import ZipFile

from graph.tools.sandbox.acervo import ROOT, read_reference, consultar_acervo
from graph.tools.sandbox.teacher_materials import consultar_materiais_professor
from services.teacher_materials import extract_material, read_teacher_materials, TEXT_LIMIT

OWNER = "11111111-1111-4111-8111-111111111111"
SESSION = "22222222-2222-4222-8222-222222222222"
MATERIAL = "33333333-3333-4333-8333-333333333333"


def config(teacher=OWNER):
    return {"configurable": {"thread_id": f"workflow-{SESSION}", "teacher_user_id": teacher, "user_id": "10"}}


def db(owner=OWNER):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={"owner_user_id": owner})
    conn.fetch = AsyncMock(return_value=[])
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


def material(kind="html", html="", blob=b""):
    return {"id": MATERIAL, "title": "Apoio", "file_type": kind, "html_content": html, "file_content": blob}


class PublicReferenceTest(unittest.TestCase):
    def test_allowlist_and_no_template_bypass(self):
        for filename in ("../.env", "/etc/passwd", "teorias/../contratos.md", "teorias\\ausubel.md",
                         "templates/templates.json", "templates/plano-de-aula-blocos.html", "prompts/00.md"):
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                read_reference(filename)
        self.assertIn("Consulta seletiva", read_reference("guia_consulta.md")["conteudo"])

    def test_symlink_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "teorias").mkdir()
            (root / "private").write_text("segredo")
            (root / "teorias/test.md").symlink_to(root / "private")
            with patch("graph.tools.sandbox.acervo.ROOT", root), self.assertRaises(ValueError):
                read_reference("teorias/test.md")

    def test_markdown_pagination_complete_and_all_formats_explained(self):
        filename = "formatos-de-aula/_indice.md"
        chunks, offset = [], 0
        while offset is not None:
            page = read_reference(filename, offset)
            self.assertLessEqual(len(page["conteudo"]), 18000)
            chunks.append(page["conteudo"])
            offset = page["proximo_inicio"]
        index = "".join(chunks)
        self.assertEqual(index, (ROOT / filename).read_text())
        filenames = {p.name for p in (ROOT / "formatos-de-aula").glob("*.md") if p.name != "_indice.md"}
        rows = [line for line in index.splitlines() if line.startswith("| `")]
        self.assertEqual({re.search(r"`([^`]+\.md)`", row)[1] for row in rows}, filenames)
        self.assertEqual(len(filenames), 61)
        self.assertTrue(all(len(row.split("|")[-2].strip()) > 100 for row in rows))

    def test_csv_filter_grade_membership_pagination_and_validation(self):
        filters = {"education_stage": "EF_AF", "grade": "6"}
        first = read_reference("dados/bncc.csv", filtros=filters)
        self.assertEqual(len(first["registros"]), 20)
        self.assertIsNotNone(first["proximo_inicio"])
        found, start = [], 0
        while start is not None:
            result = read_reference("dados/bncc.csv", start, filters)
            found.extend(result["registros"])
            start = result["proximo_inicio"]
        self.assertEqual(len(found), first["total"])
        self.assertEqual(len({r["id"] for r in found}), len(found))
        self.assertTrue(all("6" in r["grade"].split(";") for r in found))
        self.assertIn("6;7;8;9", {r["grade"] for r in found})
        for args in (("dados/bncc.csv", -1), ("dados/bncc.csv", 0, {"bad": "x"}), ("teorias/_indice.md", 0, {"id": "x"})):
            with self.assertRaises(ValueError):
                read_reference(*args)
        self.assertEqual(read_reference("dados/bncc.csv", filtros={"code": "inexistente"})["registros"], [])

    def test_theory_relations_and_bncc_copies_agree(self):
        principles = read_reference("dados/teorias-principios.csv", filtros={"theories": "Aprendizagem significativa — David Ausubel"})["registros"]
        with (ROOT / "dados/teorias-principios.csv").open() as stream:
            expected = [r for r in csv.DictReader(stream) if "Aprendizagem significativa — David Ausubel" in json.loads(r["theories"])]
        self.assertEqual(principles, expected)
        for principle in principles:
            rules = read_reference("dados/teorias-regras.csv", filtros={"principle_id": principle["id"], "active": "true"})["registros"]
            self.assertTrue(rules)
            self.assertTrue(all(int(r["priority"]) in {100, 80, 60} for r in rules))
        repo = Path(__file__).resolve().parents[1]
        self.assertEqual((ROOT / "dados/bncc.csv").read_bytes(), (repo / "graph/tools/retrieval/dados/bncc.csv").read_bytes())

    def test_tools_do_not_expose_identity_or_paths_to_private_data(self):
        self.assertNotIn("config", consultar_materiais_professor.args)
        self.assertNotIn("teacher_user_id", consultar_materiais_professor.args)
        self.assertNotIn("config", consultar_acervo.args)


class PrivateReferenceTest(unittest.IsolatedAsyncioTestCase):
    async def test_wrong_missing_legacy_identity_rejected(self):
        for teacher in (None, "10", MATERIAL):
            pool, conn = db()
            with patch("services.teacher_materials.get_pool", return_value=pool), self.assertRaisesRegex(ValueError, "não autorizado"):
                await read_teacher_materials(config(teacher))
            conn.fetch.assert_not_called()
            self.assertEqual(conn.fetchrow.await_count, 1)

    async def test_public_and_missing_sessions_never_read_private_rows(self):
        for teacher in (OWNER, None):
            pool, conn = db(owner=None)
            with patch("services.teacher_materials.get_pool", return_value=pool):
                result = await read_teacher_materials(config(teacher), MATERIAL)
            self.assertEqual(result["materiais"], [])
            self.assertEqual(conn.fetchrow.await_count, 1)
        pool, conn = db()
        conn.fetchrow.return_value = None
        with patch("services.teacher_materials.get_pool", return_value=pool), self.assertRaisesRegex(ValueError, "Sessão não encontrada"):
            await read_teacher_materials(config())

    async def test_catalog_metadata_only_owned_classes_and_pagination(self):
        pool, conn = db()
        conn.fetch.return_value = [{"id": MATERIAL, "title": "Apoio", "file_type": "pdf", "turma_ids": [SESSION]}] * 21
        with patch("services.teacher_materials.get_pool", return_value=pool):
            result = await read_teacher_materials(config(), inicio=20)
        self.assertEqual(len(result["materiais"]), 20)
        self.assertEqual(result["proximo_inicio"], 40)
        sql, *args = conn.fetch.await_args.args
        self.assertNotIn("file_content", sql)
        self.assertNotIn("html_content", sql)
        self.assertIn("c.user_id=m.user_id", sql)
        self.assertIn("WHERE m.user_id=$1", sql)
        self.assertEqual(args, [OWNER, 21, 20])

    async def test_selected_material_scoped_to_owner_and_not_found_closed(self):
        pool, conn = db()
        conn.fetchrow.side_effect = [{"owner_user_id": OWNER}, None]
        with patch("services.teacher_materials.get_pool", return_value=pool), self.assertRaisesRegex(ValueError, "não disponível"):
            await read_teacher_materials(config(), MATERIAL)
        sql, *args = conn.fetchrow.await_args.args
        self.assertIn("WHERE id=$1 AND user_id=$2", sql)
        self.assertEqual(args, [MATERIAL, OWNER])

    async def test_successful_read_preserves_config_and_passes_only_selected_row(self):
        pool, conn = db()
        row = material()
        conn.fetchrow.side_effect = [{"owner_user_id": OWNER}, row]
        with patch("services.teacher_materials.get_pool", return_value=pool), patch("services.teacher_materials.extract_material", return_value={"conteudo": "Trecho"}) as extract:
            result = json.loads(await consultar_materiais_professor.ainvoke({"material_id": MATERIAL, "pagina": 2, "inicio": 12}, config=config()))
        self.assertEqual(result["conteudo"], "Trecho")
        extract.assert_called_once_with(row, 2, 12)

    async def test_invalid_inputs_fail_before_database_access(self):
        with patch("services.teacher_materials.get_pool") as pool:
            for args in ((config(), "../../.env"), (config(), None, 0), (config(), None, 1, -1)):
                with self.assertRaises(ValueError):
                    await read_teacher_materials(*args)
            pool.assert_not_called()


class AttachmentTextTest(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("bs4"), "bs4 disponível no container")
    def test_html_strips_executable_content_and_paginates(self):
        row = material(html="<html><head><title>not body</title></head><body><script>secret()</script><style>hidden</style><p>" + "x" * (TEXT_LIMIT + 10) + "</p><img src='http://example.test/private'></body></html>")
        first = extract_material(row, 1, 0)
        self.assertEqual(first["conteudo"], "x" * TEXT_LIMIT)
        self.assertEqual(first["proximo_inicio"], TEXT_LIMIT)
        self.assertEqual(extract_material(row, 1, TEXT_LIMIT)["conteudo"], "x" * 10)
        self.assertIsNone(first["total_paginas"])
        with self.assertRaises(ValueError):
            extract_material(row, 2, 0)

    def test_docx_extracts_text_in_document_order_without_executing_xml(self):
        stream = BytesIO()
        with ZipFile(stream, "w") as archive:
            archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Primeiro</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Tabela</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
        result = extract_material(material("docx", blob=stream.getvalue()), 1, 0)
        self.assertEqual(result["conteudo"], "Primeiro\nTabela")
        with self.assertRaises(ValueError):
            extract_material(material("docx", blob=b"bad"), 1, 0)
        stream = BytesIO()
        with ZipFile(stream, "w") as archive:
            archive.writestr("word/document.xml", '<!DOCTYPE foo [<!ENTITY test SYSTEM "file:///etc/passwd">]><foo>&test;</foo>')
        with self.assertRaisesRegex(ValueError, "Entidades"):
            extract_material(material("docx", blob=stream.getvalue()), 1, 0)

    @unittest.skipUnless(importlib.util.find_spec("fitz"), "PyMuPDF disponível no container")
    def test_pdf_page_scanned_page_and_invalid_pdf(self):
        import fitz
        with fitz.open() as pdf:
            pdf.new_page().insert_text((40, 40), "Texto da primeira pagina")
            pdf.new_page()
            blob = pdf.tobytes()
        row = material("pdf", blob=blob)
        first = extract_material(row, 1, 0)
        self.assertIn("primeira", first["conteudo"])
        self.assertEqual(first["total_paginas"], 2)
        self.assertEqual(first["proxima_pagina"], 2)
        self.assertIn("OCR", extract_material(row, 2, 0)["aviso"])
        with self.assertRaises(ValueError):
            extract_material(row, 3, 0)
        with self.assertRaises(ValueError):
            extract_material(material("pdf", blob=b"invalid pdf"), 1, 0)

    def test_resource_limits_and_unsupported_content(self):
        with patch("services.teacher_materials.MAX_BYTES", 10), self.assertRaisesRegex(ValueError, "limite"):
            extract_material(material("docx", blob=b"x" * 11), 1, 0)
        with self.assertRaisesRegex(ValueError, "nenhuma URL"):
            extract_material(material("png", blob=b"image"), 1, 0)


if __name__ == "__main__":
    unittest.main()
