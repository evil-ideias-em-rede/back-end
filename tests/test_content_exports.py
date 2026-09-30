"""Exercise saved-content downloads, independently of workflow/editor exports."""

import io
import shutil
import subprocess
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import fitz
from docx import Document
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from auth.dependencies import CurrentUser, get_current_user
from graph.tools.sandbox.shared.html_page_contract import PaginationError
from routers import content_router
from tests.test_html_pagination import document


CONTENT_ID = UUID("9f939781-2e19-4907-8c4a-eaa2768bbaf0")
HAS_CONVERTERS = shutil.which("chromium") and shutil.which("pdftohtml")


def overflowing_document(orientation="V"):
    block_height = 19 if orientation == "H" else 27
    blocks = "".join(f'<div class="block">Bloco {index} completo</div>' for index in range(10))
    return document(f'''<style>
        section > .grid {{display:grid;gap:8px}}
        .block {{height:{block_height}mm;border:1px solid black}}
        </style><section data-ied-page="1"><p>Primeira intacta</p></section>
        <section data-ied-page="2"><div class="grid">{blocks}</div>
        <p>Último trecho da segunda</p></section>
        <section data-ied-page="3"><p>Terceira intacta</p></section>''', orientation)


class ContentExportTest(unittest.TestCase):
    def setUp(self):
        self.row = {
            "title": "Plano de Aula", "file_name": "Plano de Aula.html",
            "file_content": None, "html_content": "<p>Revisão: ação e água</p>",
            "file_type": "html", "orientation": "V", "updated_at": "2026-09-30",
        }
        self.conn = object()
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=self.conn)
        pool_patch = patch.object(content_router, "get_pool", return_value=pool)
        pool_patch.start()
        self.addCleanup(pool_patch.stop)
        self.queries = {}
        for kind, name in (("templates", "get_template"), ("materiais", "get_material")):
            query_patch = patch.object(content_router, name, new_callable=AsyncMock)
            self.queries[kind] = query_patch.start()
            self.queries[kind].return_value = self.row
            self.addCleanup(query_patch.stop)
        content_router._thumbnail_cache.clear()
        self.addCleanup(content_router._thumbnail_cache.clear)
        self.app = FastAPI()
        self.app.include_router(content_router.router)
        self.app.dependency_overrides[get_current_user] = lambda: CurrentUser("teacher")
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def download(self, kind, format):
        response = self.client.get(f"/api/{kind}/{CONTENT_ID}/download", params={"format": format})
        self.queries[kind].assert_awaited_with(self.conn, "teacher", CONTENT_ID)
        return response

    def assert_success(self, response):
        self.assertEqual(response.status_code, 200, response.text[:500] if response.status_code != 200 else "")

    def test_html_preserves_stored_source_and_fallback(self):
        for kind in self.queries:
            for stored in (None, b"<p>Stored source</p>"):
                with self.subTest(kind=kind, stored=bool(stored)):
                    self.row["file_content"] = stored
                    response = self.download(kind, "html")
                    self.assert_success(response)
                    self.assertEqual(response.content, stored or self.row["html_content"].encode())
                    self.assertIn('filename="Plano_de_Aula.html"', response.headers["content-disposition"])

    def test_original_material_files_are_not_reconverted(self):
        for format in ("pdf", "docx"):
            with self.subTest(format=format):
                self.row.update(file_type=format, file_content=b"original bytes")
                response = self.download("materiais", format)
                self.assert_success(response)
                self.assertEqual(response.content, b"original bytes")

    def test_authentication_is_required(self):
        self.app.dependency_overrides.clear()
        for kind in self.queries:
            response = self.client.get(f"/api/{kind}/{CONTENT_ID}/download?format=html")
            self.assertIn(response.status_code, (401, 403))
            self.queries[kind].assert_not_awaited()

    def test_missing_and_empty_documents(self):
        self.row["html_content"] = " "
        for kind, query in self.queries.items():
            for format in ("pdf", "docx"):
                with self.subTest(kind=kind, format=format):
                    self.assertEqual(self.download(kind, format).status_code, 422)
            query.return_value = None
            self.assertEqual(self.download(kind, "html").status_code, 404)

    def test_conversion_failures_have_actionable_status_codes(self):
        failures = (
            (subprocess.TimeoutExpired("converter", 1), 504),
            (FileNotFoundError("converter"), 503),
            (PaginationError("Página 2: conteúdo cortado"), 422),
            (RuntimeError("Falha ao converter"), 502),
        )
        for kind in self.queries:
            for format, converter in (("pdf", "render_html_to_pdf"), ("docx", "convert_paginated_html_bytes_to_docx")):
                for error, status in failures:
                    with self.subTest(kind=kind, format=format, status=status):
                        with patch.object(content_router, converter, side_effect=error):
                            self.assertEqual(self.download(kind, format).status_code, status)

    @unittest.skipUnless(HAS_CONVERTERS, "Conversores indisponíveis")
    def test_saved_pdf_fits_overflow_without_losing_pages_or_text(self):
        for kind, orientation in (("templates", "V"), ("materiais", "V"), ("materiais", "H")):
            with self.subTest(kind=kind, orientation=orientation):
                self.row.update(html_content=overflowing_document(orientation).decode(), orientation=orientation)
                response = self.download(kind, "pdf")
                self.assert_success(response)
                self.assertEqual(response.headers["content-type"], "application/pdf")
                with fitz.open(stream=response.content, filetype="pdf") as pdf:
                    self.assertEqual(len(pdf), 3)
                    self.assertEqual(pdf[0].rect.width > pdf[0].rect.height, orientation == "H")
                    self.assertIn("Primeira intacta", pdf[0].get_text())
                    for index in range(10):
                        self.assertIn(f"Bloco {index} completo", pdf[1].get_text())
                    self.assertIn("Último trecho da segunda", pdf[1].get_text())
                    self.assertIn("Terceira intacta", pdf[2].get_text())

    @unittest.skipUnless(HAS_CONVERTERS, "Conversores indisponíveis")
    def test_saved_docx_accepts_generated_html_and_preserves_editable_text(self):
        for kind, orientation in (("templates", "V"), ("materiais", "V"), ("materiais", "H")):
            with self.subTest(kind=kind, orientation=orientation):
                self.row.update(file_content=overflowing_document(orientation), orientation=orientation)
                response = self.download(kind, "docx")
                self.assert_success(response)
                doc = Document(io.BytesIO(response.content))
                text = " ".join(p.text for p in doc.paragraphs)
                for expected in ("Primeira intacta", "Último trecho da segunda", "Terceira intacta"):
                    self.assertIn(expected, text)
                for index in range(10):
                    self.assertIn(f"Bloco {index} completo", text)
                self.assertEqual(len(doc.element.xpath("//w:pageBreakBefore")), 2)
                self.assertEqual(doc.sections[0].page_width > doc.sections[0].page_height, orientation == "H")

    @unittest.skipUnless(HAS_CONVERTERS, "Conversores indisponíveis")
    def test_thumbnail_fits_overflow_and_respects_orientation_and_cache(self):
        for orientation in ("V", "H"):
            with self.subTest(orientation=orientation):
                self.row.update(file_content=overflowing_document(orientation), orientation=orientation)
                url = f"/api/materiais/{CONTENT_ID}/thumbnail"
                response = self.client.get(url)
                self.assert_success(response)
                self.assertEqual(response.headers["content-type"], "image/png")
                with Image.open(io.BytesIO(response.content)) as preview:
                    self.assertEqual(preview.width > preview.height, orientation == "H")
                with patch.object(content_router, "_first_page_png") as renderer:
                    self.assertEqual(self.client.get(url).content, response.content)
                    renderer.assert_not_called()

    @unittest.skipUnless(HAS_CONVERTERS, "Conversores indisponíveis")
    def test_actual_clipped_content_is_still_rejected(self):
        self.row["file_content"] = document('''<section data-ied-page="1">
            <div style="height:20mm;overflow:hidden"><p style="height:60mm">Texto cortado</p></div>
            </section>''')
        for kind, format in (("templates", "pdf"), ("materiais", "docx")):
            with self.subTest(kind=kind, format=format):
                response = self.download(kind, format)
                self.assertEqual(response.status_code, 422)
                self.assertIn("paginação", response.json()["detail"])
