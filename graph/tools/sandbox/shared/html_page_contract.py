"""Mede folhas no Chromium sem esconder, cortar ou alterar o conteúdo original."""

import json
from html.parser import HTMLParser


class PaginationError(RuntimeError):
    pass


def validation_script(orientation: str) -> str:
    width, height = (297, 210) if orientation == "H" else (210, 297)
    script = r"""
<script>
window.addEventListener('load', async function () {
  await document.fonts.ready;
  const errors = [];
  const pages = Array.from(document.querySelectorAll('[data-ied-page]'));
  if (pages.length) {
    const probe = document.createElement('div');
    probe.style.cssText = 'position:absolute;visibility:hidden;width:WIDTHmm;height:HEIGHTmm;box-sizing:border-box;padding:0;border:0';
    document.body.appendChild(probe);
    const sheet = probe.getBoundingClientRect();
    probe.remove();
    const ids = new Set();
    const tolerance = 2;
    pages.forEach(function (page, index) {
      const label = 'Página ' + (index + 1);
      const id = page.getAttribute('data-ied-page');
      if (!id || ids.has(id) || page.parentElement !== document.body) {
        errors.push(label + ': delimitador vazio, repetido ou fora do body.');
      }
      ids.add(id);
      const rect = page.getBoundingClientRect();
      if (rect.width > sheet.width + tolerance || rect.height > sheet.height + tolerance) {
        errors.push(label + ': tamanho excede uma folha A4; divida o conteúdo.');
      }
      const elements = [page, ...page.querySelectorAll('*')];
      const overflow = elements.some(function (el) {
        if (!(el instanceof HTMLElement) || !el.getClientRects().length) return false;
        const style = getComputedStyle(el);
        const box = el.getBoundingClientRect();
        if (box.right > rect.left + sheet.width + tolerance ||
            box.bottom > rect.top + sheet.height + tolerance ||
            box.left < rect.left - tolerance || box.top < rect.top - tolerance) return true;
        const scrollX = el.scrollWidth > el.clientWidth + tolerance;
        const scrollY = el.scrollHeight > el.clientHeight + tolerance;
        return (scrollX && ['auto', 'scroll', 'hidden', 'clip'].includes(style.overflowX)) ||
               (scrollY && ['auto', 'scroll', 'hidden', 'clip'].includes(style.overflowY));
      });
      if (overflow) errors.push(label + ': conteúdo rolável, cortado ou fora da folha; distribua em mais páginas.');
    });
    Array.from(document.body.children).forEach(function (el) {
      if (el.hasAttribute('data-ied-page') || ['STYLE', 'SCRIPT', 'LINK'].includes(el.tagName)) return;
      const box = el.getBoundingClientRect();
      if (box.width && box.height && getComputedStyle(el).visibility !== 'hidden') {
        errors.push('Há conteúdo fora dos delimitadores de página.');
      }
    });
  }
  const result = document.createElement('script');
  result.type = 'application/json';
  result.id = 'workflow-page-validation-result';
  result.textContent = JSON.stringify({pages: pages.length, errors: errors});
  document.body.appendChild(result);
});
</script>
"""
    return script.replace("WIDTH", str(width)).replace("HEIGHT", str(height))


def read_validation_result(dom: str) -> int:
    class ResultParser(HTMLParser):
        active = False
        result = ""

        def handle_starttag(self, tag, attrs):
            if tag == "script" and dict(attrs).get("id") == "workflow-page-validation-result":
                self.active = True

        def handle_endtag(self, tag):
            if tag == "script":
                self.active = False

        def handle_data(self, data):
            if self.active:
                self.result += data

    parser = ResultParser()
    parser.feed(dom)
    try:
        result = json.loads(parser.result)
    except (ValueError, TypeError) as exc:
        raise PaginationError("Não foi possível verificar a paginação do HTML.") from exc
    if result["errors"]:
        raise PaginationError("Revise a paginação antes de exportar: " + " ".join(result["errors"][:8]))
    return result["pages"]
