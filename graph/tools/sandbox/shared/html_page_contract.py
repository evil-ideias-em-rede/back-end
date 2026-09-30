"""Mede folhas no Chromium sem esconder, cortar ou alterar o conteúdo original."""

import json
from html.parser import HTMLParser


class PaginationError(RuntimeError):
    pass


def validation_script(orientation: str, fit_overflow: bool = False) -> str:
    width, height = (297, 210) if orientation == "H" else (210, 297)
    script = r"""
<script>
window.addEventListener('load', async function () {
  await document.fonts.ready;
  const errors = [];
  const pages = Array.from(document.querySelectorAll('[data-ied-page]'));
  if (FIT_OVERFLOW && pages.length) {
    pages.forEach(function (page) {
      const style = getComputedStyle(page);
      const origin = page.getBoundingClientRect();
      const content = [...page.querySelectorAll('*')].filter(function (el) {
        return el instanceof HTMLElement && el.getClientRects().length;
      });
      const contentWidth = Math.max(origin.width, ...content.map(function (el) {
        return el.getBoundingClientRect().right - origin.left;
      }).map(function (right) { return right + parseFloat(style.paddingRight); }));
      const contentHeight = Math.max(origin.height, ...content.map(function (el) {
        return el.getBoundingClientRect().bottom - origin.top;
      }).map(function (bottom) { return bottom + parseFloat(style.paddingBottom); }));
      const scale = Math.min(1, origin.width / contentWidth, origin.height / contentHeight);
      // Ajustes muito grandes tornam a folha ilegível e continuam sendo
      // rejeitados. O autoajuste existe para pequenas variações de fonte e
      // conteúdo editado, não para esconder erros graves de paginação.
      if (scale < 0.998 && scale >= 0.8 && style.zoom === '1' && style.transform === 'none') {
        // Zoom participa do layout de impressão; transform deixava espaço
        // não escalado e criava folhas extras. Preserve os seletores CSS
        // existentes: não adicione wrappers aos filhos da página.
        page.style.setProperty('zoom', String(scale), 'important');
        page.style.setProperty('height', origin.height / scale + 'px', 'important');
        page.style.setProperty('max-height', 'none', 'important');
        page.setAttribute('data-workflow-page-scale', String(scale));
      }
    });
  }
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
    return (
        script.replace("WIDTH", str(width))
        .replace("HEIGHT", str(height))
        .replace("FIT_OVERFLOW", "true" if fit_overflow else "false")
    )


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
