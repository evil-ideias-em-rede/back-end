---
name: validar_html_pdf
description: Valida se o HTML.html do material pode ser exportado para PDF pelo mesmo fluxo do botão Exportar e rasteriza cada página para inspeção estrutural.
---

# Validar HTML antes de concluir

Use esta skill quando criar ou alterar `HTML.html`, principalmente na tela de
edição. O PDF gerado aqui precisa ser equivalente ao PDF exportado pelo
frontend: use o conversor `html_pdf_tools.py`, não `reportlab`, não uma
biblioteca alternativa e não um HTML simplificado.

## Fluxo obrigatório

1. Leia o documento atual antes de editar:

```bash
cat HTML.html
```

2. Confirme que as páginas continuam delimitadas por seções no `body`:

```bash
grep -n 'data-ied-page' HTML.html
```

Cada página física deve ter uma seção como:

```html
<section data-ied-page="1">...</section>
```

3. Gere o PDF com o mesmo conversor do endpoint. Use `H` para slides e `V`
para materiais em retrato:

```bash
python3 html_pdf_tools.py HTML.html HTML.validacao.pdf --orientation V
```

4. Converta o PDF em imagens, uma imagem por página:

```bash
python3 conversor_pdf_para_imagem.py HTML.validacao.pdf --dpi 150 --formato png
```

5. Faça a verificação estrutural antes de responder:

```bash
python3 - <<'PY'
import glob
import os
from pathlib import Path
import pymupdf

if not Path("HTML.html").read_text(encoding="utf-8").strip():
    raise SystemExit("HTML.html está vazio")

pdf = pymupdf.open("HTML.validacao.pdf")
imagens = sorted(glob.glob("HTML.validacao_imagens_*/*.png"))
print({
    "paginas_pdf": len(pdf),
    "imagens_geradas": len(imagens),
    "tamanhos": [tuple(page.rect) for page in pdf],
    "texto_por_pagina": [len(page.get_text().strip()) for page in pdf],
    "imagens": imagens,
})
if not pdf.page_count:
    raise SystemExit("O PDF não possui páginas")
if len(imagens) != pdf.page_count:
    raise SystemExit("A quantidade de imagens não corresponde às páginas do PDF")
if any(not os.path.isfile(path) or os.path.getsize(path) == 0 for path in imagens):
    raise SystemExit("Existe uma imagem de página vazia ou inválida")
if any(
    not page.get_text().strip()
    and not page.get_images(full=True)
    and not page.get_drawings()
    for page in pdf
):
    raise SystemExit("Existe uma página PDF completamente vazia")
PY
```

## Critérios de correção

- O comando de geração deve terminar com sucesso e criar um PDF não vazio.
- O número de imagens deve ser igual ao número de páginas do PDF.
- A orientação deve corresponder ao material: retrato para documentos comuns
  e paisagem para slides.
- Não deve haver página totalmente vazia causada por `data-ied-page` extra.
- Preserve `HTML.html`, suas seções, estilos, conteúdo não solicitado e os
  atributos `data-ied-page` durante a correção.
- Se houver falha, corrija o HTML e execute novamente o fluxo completo.

Os arquivos `HTML.validacao.pdf` e a pasta de imagens são artefatos de
validação. Não os use como substitutos de `HTML.html` e não responda como se o
material estivesse pronto enquanto a geração falhar.
