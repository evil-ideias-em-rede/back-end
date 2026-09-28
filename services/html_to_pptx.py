"""Converte os slides HTML em um PPTX com textos editáveis.

O HTML do editor primeiro passa pelo mesmo Chromium da exportação para PDF.
Depois, o Poppler separa cada página em fundo gráfico e textos posicionados.
O fundo vira o plano de fundo do slide e cada trecho de texto vira uma caixa
editável, seguindo a estratégia do conversor fornecido pelo usuário.
"""

import base64
from io import BytesIO
import re
from pathlib import Path
import tempfile

from bs4 import BeautifulSoup, NavigableString, Tag
from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Mm, Pt

from graph.tools.sandbox.shared.html_pdf_tools import render_html_to_pdf
from services.pdf_to_html import PdfConversionError, convert_pdf_bytes_to_html


A4_SHORT_MM = 210.0
A4_LONG_MM = 297.0
PX_PER_MM = 96 / 25.4
EMU_PER_PX = 914400 / 96
PT_PER_PX = 72 / 96
LINE_HEIGHT_NORMAL = 1.15
RE_NUM = r"(-?\d+(?:\.\d+)?)"

FONT_MAP = {
    "helveticaneue": "Arial",
    "helvetica": "Arial",
    "arial": "Arial",
    "arialmt": "Arial",
    "timesnewroman": "Times New Roman",
    "timesnewromanps": "Times New Roman",
    "timesnewromanpsmt": "Times New Roman",
    "times": "Times New Roman",
    "timesroman": "Times New Roman",
    "courier": "Courier New",
    "couriernew": "Courier New",
    "calibri": "Calibri",
    "cambria": "Cambria",
    "georgia": "Georgia",
    "verdana": "Verdana",
    "tahoma": "Tahoma",
    "garamond": "Garamond",
    "symbol": "Symbol",
}


class HtmlToPptxError(RuntimeError):
    """Erro ao montar a apresentação a partir do HTML renderizado."""


def _clean_font_name(raw: str) -> tuple[str, bool, bool]:
    name = raw.strip().strip("'\"")
    name = re.sub(r"^[A-Z]{6}\+", "", name)
    base, _, style = name.partition("-")
    style = style.lower()
    bold = any(value in style for value in ("bold", "black", "heavy", "semibold"))
    italic = any(value in style for value in ("italic", "oblique"))

    key = base.lower().replace(" ", "")
    if key in FONT_MAP:
        return FONT_MAP[key], bold, italic
    for suffix in ("psmt", "mt", "ps"):
        if key.endswith(suffix) and key[: -len(suffix)] in FONT_MAP:
            return FONT_MAP[key[: -len(suffix)]], bold, italic
    readable = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", re.sub(r"(PSMT|MT|PS)$", "", base))
    return readable or "Arial", bold, italic


def _read_css(html: str) -> tuple[dict, dict]:
    fonts = {}
    for name, body in re.findall(r"\.(ft\d+)\s*\{([^}]*)\}", html):
        properties = dict(
            (key.strip().lower(), value.strip())
            for key, _, value in (part.partition(":") for part in body.split(";"))
            if key.strip()
        )
        size = re.match(RE_NUM, properties.get("font-size", "16px"))
        line_height = re.match(RE_NUM, properties.get("line-height", ""))
        family, bold, italic = _clean_font_name(properties.get("font-family", "Arial"))
        color = properties.get("color", "#000000").lstrip("#")
        if len(color) == 3:
            color = "".join(component * 2 for component in color)
        fonts[name] = {
            "size_px": float(size.group(1)) if size else 16.0,
            "line_height_px": float(line_height.group(1)) if line_height else None,
            "family": family,
            "bold": bold or "bold" in properties.get("font-weight", ""),
            "italic": italic or "italic" in properties.get("font-style", ""),
            "color": color if re.fullmatch(r"[0-9a-fA-F]{6}", color) else "000000",
        }

    pages = {}
    content_pattern = (
        rf"\.pg(\d+)-conteudo\{{width:{RE_NUM}px;height:{RE_NUM}px;"
        rf"transform:scale\({RE_NUM}\);\}}"
    )
    for number, width, slice_height, scale in re.findall(content_pattern, html):
        pages[number] = {
            "width": float(width),
            "slice_height": float(slice_height),
            "html_scale": float(scale),
        }

    background_pattern = (
        rf"\.pg(\d+)-fundo\{{background-image:url\(\"(data:[^\"]+)\"\);"
        rf"background-size:{RE_NUM}px {RE_NUM}px;\}}"
    )
    for number, data_url, width, height in re.findall(background_pattern, html):
        pages.setdefault(number, {}).update({
            "background": data_url,
            "background_width": float(width),
            "background_height": float(height),
        })
    return fonts, pages


def _decode_data_url(url: str) -> Image.Image:
    _, _, encoded = url.partition(",")
    try:
        return Image.open(BytesIO(base64.b64decode(encoded))).convert("RGB")
    except (ValueError, OSError) as exc:
        raise HtmlToPptxError("Não foi possível ler o fundo de um slide") from exc


def _blank_layout(presentation: Presentation):
    for layout in presentation.slide_layouts:
        if len(layout.placeholders) == 0:
            return layout
    return presentation.slide_layouts[6]


def _set_run_language(run, language: str = "pt-BR") -> None:
    run._r.get_or_add_rPr().set("lang", language)


def _add_runs(
    paragraph,
    node: Tag,
    font: dict,
    scale: float,
    bold: bool = False,
    italic: bool = False,
    underline: bool = False,
) -> None:
    for child in node.children:
        if isinstance(child, NavigableString):
            text = str(child).replace("\u00a0", " ")
            if not text:
                continue
            run = paragraph.add_run()
            run.text = text
            run.font.name = font["family"]
            run.font.size = Pt(round(font["size_px"] * scale * PT_PER_PX * 2) / 2)
            run.font.bold = bold or font["bold"]
            run.font.italic = italic or font["italic"]
            run.font.underline = underline or None
            run.font.color.rgb = RGBColor.from_string(font["color"].upper())
            properties = run._r.get_or_add_rPr()
            for tag in ("a:ea", "a:cs"):
                element = properties.find(qn(tag))
                if element is None:
                    element = etree.SubElement(properties, qn(tag))
                element.set("typeface", font["family"])
            _set_run_language(run)
        elif isinstance(child, Tag):
            child_name = child.name.lower()
            if child_name == "br":
                paragraph.add_line_break()
                continue
            _add_runs(
                paragraph,
                child,
                font,
                scale,
                bold or child_name in ("b", "strong"),
                italic or child_name in ("i", "em"),
                underline or child_name == "u",
            )


def _set_slide_background(slide, image: Image.Image) -> None:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    _, relation_id = slide.part.get_or_add_image_part(buffer)

    common_slide_data = slide._element.find(qn("p:cSld"))
    old_background = common_slide_data.find(qn("p:bg"))
    if old_background is not None:
        common_slide_data.remove(old_background)
    background = etree.fromstring(
        '<p:bg xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<p:bgPr><a:blipFill dpi="0" rotWithShape="1">'
        f'<a:blip r:embed="{relation_id}"/><a:srcRect/>'
        '<a:stretch><a:fillRect/></a:stretch>'
        '</a:blipFill><a:effectLst/></p:bgPr></p:bg>'
    )
    common_slide_data.insert(0, background)


def _presentation_from_pdf_html(html: str, title: str) -> bytes:
    fonts, pages = _read_css(html)
    soup = BeautifulSoup(html, "html.parser")
    sheets = soup.select("section.folha")
    if not sheets:
        raise HtmlToPptxError("A conversão intermediária não encontrou nenhum slide")

    first_page = next((pages.get(sheet.get("data-pagina-pdf", "")) for sheet in sheets), None)
    if not first_page:
        raise HtmlToPptxError("Os dados de tamanho dos slides não foram encontrados")
    source_width = first_page.get("background_width", first_page.get("width", 1))
    source_height = first_page.get("background_height", first_page.get("slice_height", 1))
    landscape = source_width > source_height
    width_mm = A4_LONG_MM if landscape else A4_SHORT_MM
    height_mm = A4_SHORT_MM if landscape else A4_LONG_MM

    presentation = Presentation()
    presentation.slide_width = Mm(width_mm)
    presentation.slide_height = Mm(height_mm)
    presentation.core_properties.title = title
    layout = _blank_layout(presentation)
    background_cache: dict[str, Image.Image] = {}
    text_count = 0

    for sheet in sheets:
        page_number = sheet.get("data-pagina-pdf", "")
        page = pages.get(page_number)
        if not page or "width" not in page:
            raise HtmlToPptxError(f"Os dados da página {page_number} não foram encontrados")

        content = sheet.select_one(".folha-conteudo")
        slide = presentation.slides.add_slide(layout)
        coordinate_scale = (width_mm * PX_PER_MM) / page["width"]

        if page.get("background") and content is not None:
            position = re.search(
                rf"background-position:\s*0\s+{RE_NUM}px",
                content.get("style", ""),
            )
            offset = -float(position.group(1)) if position else 0.0
            if page_number not in background_cache:
                background_cache[page_number] = _decode_data_url(page["background"])
            source = background_cache[page_number]
            source_css_height = page.get("background_height", page["slice_height"])
            pixel_scale = source.height / source_css_height
            top = int(round(offset * pixel_scale))
            bottom = int(round(min(offset + page["slice_height"], source_css_height) * pixel_scale))
            if bottom > top:
                _set_slide_background(slide, source.crop((0, top, source.width, bottom)))

        if content is None:
            continue
        for paragraph_node in content.find_all("p", recursive=False):
            if not paragraph_node.get_text().replace("\u00a0", "").strip():
                continue
            style = paragraph_node.get("style", "")
            top_match = re.search(rf"top:{RE_NUM}px", style)
            left_match = re.search(rf"left:{RE_NUM}px", style)
            top = float(top_match.group(1)) if top_match else 0.0
            left = float(left_match.group(1)) if left_match else 0.0
            font_class = next(
                (class_name for class_name in paragraph_node.get("class", []) if class_name in fonts),
                None,
            )
            font = fonts.get(font_class, {
                "size_px": 16.0,
                "line_height_px": None,
                "family": "Arial",
                "bold": False,
                "italic": False,
                "color": "000000",
            })

            line_height_px = font["line_height_px"] or font["size_px"] * LINE_HEIGHT_NORMAL
            lines = 1 + len(paragraph_node.find_all("br"))
            x = int(round(left * coordinate_scale * EMU_PER_PX))
            y = int(round(top * coordinate_scale * EMU_PER_PX))
            width = max(int(presentation.slide_width) - x, int(Mm(5)))
            height = int(round(line_height_px * lines * coordinate_scale * EMU_PER_PX))

            shape = slide.shapes.add_textbox(Emu(x), Emu(y), Emu(width), Emu(height))
            text_count += 1
            shape.name = f"Texto {text_count}"
            frame = shape.text_frame
            frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
            frame.word_wrap = False
            frame.auto_size = MSO_AUTO_SIZE.NONE
            frame.vertical_anchor = MSO_ANCHOR.TOP
            paragraph = frame.paragraphs[0]
            paragraph.alignment = PP_ALIGN.LEFT
            paragraph.space_before = paragraph.space_after = Pt(0)
            paragraph.line_spacing = Pt(line_height_px * coordinate_scale * PT_PER_PX)
            _add_runs(paragraph, paragraph_node, font, coordinate_scale)

    output = BytesIO()
    presentation.save(output)
    return output.getvalue()


def convert_html_bytes_to_pptx(
    content: bytes,
    title: str = "apresentacao",
    work_dir: str | Path | None = None,
) -> bytes:
    """Retorna um PPTX visualmente fiel com textos editáveis."""
    if not content.strip():
        raise HtmlToPptxError("O HTML não pode estar vazio")

    temporary_parent = Path(work_dir).resolve() if work_dir else None
    if temporary_parent:
        temporary_parent.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.TemporaryDirectory(prefix="html-to-pptx-", dir=temporary_parent) as directory:
            temp_dir = Path(directory)
            pdf_path = temp_dir / "slides.pdf"
            render_html_to_pdf(content, pdf_path, "H", temp_dir)
            structured_html = convert_pdf_bytes_to_html(
                pdf_path.read_bytes(),
                title=title,
                zoom=2.0,
            ).decode("utf-8", errors="replace")
            return _presentation_from_pdf_html(structured_html, title)
    except PdfConversionError as exc:
        raise HtmlToPptxError(str(exc)) from exc
    except HtmlToPptxError:
        raise
    except (ValueError, OSError) as exc:
        raise HtmlToPptxError("Não foi possível gerar a apresentação PPTX") from exc
