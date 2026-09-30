import io
import shutil
import unittest
from unittest.mock import AsyncMock, patch

from bs4 import BeautifulSoup
from docx import Document
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth.workflow_access import require_workflow_access
from routers import html_pdf_router
from tests.test_html_pagination import document


SESSION = "ff997961-810c-4966-9bc9-4abded776b03"


class WorkflowExportTest(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(html_pdf_router.router)
        app.dependency_overrides[require_workflow_access] = lambda: None
        self.client = TestClient(app)
        self.session_patch = patch.object(html_pdf_router, "_session_or_404", new_callable=AsyncMock)
        self.session_check = self.session_patch.start()
        self.addCleanup(self.session_patch.stop)

    def download(self, content, format="html", orientation="V", filename="Plano de Aula.html"):
        return self.client.post(
            f"/api/workflow/sessions/{SESSION}/download",
            params={"format": format, "filename": filename, "orientation": orientation},
            files={"file": ("HTML.html", content, "text/html")},
        )

    def test_html_download_preserves_current_edits_and_accents(self):
        fragment = '<style>p{color:red}</style><p>Revisão: ação e água</p>'
        response = self.download(fragment.encode(), filename='../../plano.html')
        self.assertEqual(response.status_code, 200)
        self.assertIn('filename="plano.html"', response.headers["content-disposition"])
        soup = BeautifulSoup(response.content, "html.parser")
        self.assertEqual(soup.meta["charset"], "utf-8")
        self.assertEqual(soup.p.text, "Revisão: ação e água")
        self.assertEqual(soup.style.text, "p{color:red}")
        self.session_check.assert_awaited_once_with(SESSION, restore_files=False)

    def test_empty_upload_and_invalid_format_are_rejected(self):
        self.assertEqual(self.download(b' ').status_code, 422)
        self.assertEqual(self.download(b'<p>Texto</p>', format="exe").status_code, 422)

    @unittest.skipUnless(shutil.which("chromium") and shutil.which("pdftohtml"), "Conversores indisponíveis")
    def test_docx_has_editable_text_page_breaks_and_orientation(self):
        for orientation in ("V", "H"):
            with self.subTest(orientation=orientation):
                content = document('''<section data-ied-page="1"><p>Texto editável na primeira</p></section>
                    <section data-ied-page="2"><p>Última página completa</p></section>''', orientation)
                response = self.download(content, format="docx", orientation=orientation)
                self.assertEqual(response.status_code, 200, response.text[:500] if response.status_code != 200 else '')
                doc = Document(io.BytesIO(response.content))
                text = ' '.join(p.text for p in doc.paragraphs)
                self.assertIn("Texto editável na primeira", text)
                self.assertIn("Última página completa", text)
                self.assertEqual(len(doc.element.xpath('//w:pageBreakBefore')), 1)
                self.assertEqual(doc.sections[0].page_width > doc.sections[0].page_height, orientation == "H")

    @unittest.skipUnless(shutil.which("chromium"), "Chromium indisponível")
    def test_pdf_download_and_legacy_route(self):
        import pymupdf
        content = document('<section data-ied-page="1"><p>PDF completo</p></section>')
        responses = [self.download(content, format="pdf"), self.client.post(
            f"/api/workflow/sessions/{SESSION}/pdf?orientation=V",
            files={"file": ("HTML.html", content, "text/html")},
        )]
        for response in responses:
            self.assertEqual(response.status_code, 200, response.text[:500] if response.status_code != 200 else '')
            self.assertEqual(response.headers["content-type"], "application/pdf")
            with pymupdf.open(stream=response.content, filetype="pdf") as pdf:
                self.assertEqual(len(pdf), 1)
                self.assertIn("PDF completo", pdf[0].get_text())
