import json
import shutil
import tempfile
import unittest
from pathlib import Path

from graph.tools.sandbox.shared.html_page_contract import PaginationError, read_validation_result
from graph.tools.sandbox.shared.html_pdf_tools import html_for_pdf, render_html_to_pdf


def document(content, orientation="V"):
    width, height = (297, 210) if orientation == "H" else (210, 297)
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
    body {{margin:0;padding:0}}
    section[data-ied-page] {{box-sizing:border-box;width:{width}mm;height:{height}mm;padding:12mm;}}
    </style></head><body>{content}</body></html>'''.encode()


class PaginationTest(unittest.TestCase):
    def test_result_and_failure_are_explicit(self):
        for errors in ([], ["Página 1: conteúdo rolável"]):
            dom = '<script id="workflow-page-validation-result" type="application/json">' + json.dumps({"pages": 2, "errors": errors}) + '</script>'
            if errors:
                with self.assertRaisesRegex(PaginationError, "conteúdo rolável"):
                    read_validation_result(dom)
            else:
                self.assertEqual(read_validation_result(dom), 2)
        with self.assertRaises(PaginationError):
            read_validation_result("<html></html>")

    def test_print_contract(self):
        output = html_for_pdf(document(""), "H").decode()
        self.assertIn("A4 landscape", output)
        self.assertIn("break-after: page", output)
        self.assertIn(":not(:has(~ [data-ied-page]))", output)
        self.assertNotIn("overflow: hidden", output)


@unittest.skipUnless(any(shutil.which(name) for name in ("chromium", "chromium-browser", "google-chrome")), "Chromium indisponível neste ambiente")
class BrowserPaginationTest(unittest.TestCase):
    def test_one_marker_per_pdf_page_portrait_and_landscape(self):
        import pymupdf
        for orientation in ("V", "H"):
            with self.subTest(orientation=orientation), tempfile.TemporaryDirectory() as directory:
                html = document('<section data-ied-page="1"><h1>Primeira</h1></section><section data-ied-page="2"><p>Segunda</p></section>', orientation)
                output = render_html_to_pdf(html, Path(directory) / "test.pdf", orientation)
                with pymupdf.open(output) as pdf:
                    self.assertEqual(pdf.page_count, 2)
                    self.assertIn("Primeira", pdf[0].get_text())
                    self.assertIn("Segunda", pdf[1].get_text())
                    self.assertEqual(pdf[0].rect.width > pdf[0].rect.height, orientation == "H")

    def test_rejects_scroll_clipping_overflow_and_invalid_markers(self):
        cases = [
            '<section data-ied-page="1"><div style="height:20mm;overflow:auto"><p style="height:60mm">Muito conteúdo</p></div></section>',
            '<section data-ied-page="1"><div style="height:20mm;overflow:hidden"><p style="height:60mm">Texto cortado</p></div></section>',
            '<section data-ied-page="1"><div style="height:400mm">Longo</div></section>',
            '<section data-ied-page="1">A</section><section data-ied-page="1">B</section>',
            '<main><section data-ied-page="1">Aninhada</section></main>',
            '<nav>Sumário fora da página</nav><section data-ied-page="1">A</section>',
        ]
        for fit in (False, True):
            for content in cases:
                with self.subTest(content=content, fit=fit), tempfile.TemporaryDirectory() as directory:
                    with self.assertRaises(PaginationError):
                        render_html_to_pdf(document(content), Path(directory) / "test.pdf", fit_overflow=fit)

    def test_export_can_fit_moderate_page_overflow(self):
        import pymupdf
        content = '''<style>
        section > .grid {display:grid;gap:8px}
        .block {height:27mm;border:1px solid black}
        </style><section data-ied-page="1"><p>Primeira intacta</p></section>
        <section data-ied-page="2"><div class="grid">''' + ''.join(
            f'<div class="block">Bloco {index} completo</div>' for index in range(10)
        ) + '''</div><p>Último trecho da segunda</p></section>
        <section data-ied-page="3"><p>Terceira intacta</p></section>'''
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(PaginationError):
                render_html_to_pdf(document(content), Path(directory) / "strict.pdf")
            output = render_html_to_pdf(
                document(content),
                Path(directory) / "test.pdf",
                fit_overflow=True,
            )
            with pymupdf.open(output) as pdf:
                self.assertEqual(pdf.page_count, 3)
                self.assertIn("Primeira intacta", pdf[0].get_text())
                for index in range(10):
                    self.assertIn(f"Bloco {index} completo", pdf[1].get_text())
                self.assertIn("Último trecho da segunda", pdf[1].get_text())
                self.assertIn("Terceira intacta", pdf[2].get_text())

    def test_fitting_does_not_change_valid_layout(self):
        import pymupdf
        html = document('''<style>section > p {margin:0;font-size:18px}</style>
            <section data-ied-page="1"><p>Texto preservado</p></section>''')
        with tempfile.TemporaryDirectory() as directory:
            outputs = [render_html_to_pdf(html, Path(directory) / f"{fit}.pdf", fit_overflow=fit) for fit in (False, True)]
            with pymupdf.open(outputs[0]) as original, pymupdf.open(outputs[1]) as fitted:
                self.assertEqual(original[0].get_text("words"), fitted[0].get_text("words"))

    def test_legacy_without_markers_still_exports(self):
        with tempfile.TemporaryDirectory() as directory:
            output = render_html_to_pdf(document("<p>Legado</p>"), Path(directory) / "test.pdf")
            self.assertTrue(output.is_file())
