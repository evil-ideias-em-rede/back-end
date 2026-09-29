"""Contrato de entrega aplicado a todos os agentes, nas duas telas."""

HTML_PAGE_RULES = """
CONTRATO ATUAL DE PÁGINAS (prevalece sobre exemplos antigos dos guias)
- Todo conteúdo visível pertence a uma <section data-ied-page="N"> filha direta
  de body, inclusive capa, sumário, cabeçalhos, rodapés e notas ao professor.
  N é único e sequencial a partir de 1. Não aninhe marcadores de página.
- Cada seção equivale a EXATAMENTE uma folha física. Slides: 297mm x 210mm;
  demais materiais: 210mm x 297mm. Use box-sizing:border-box, padding interno
  de aproximadamente 12mm e body com margin:0; padding:0. Evite alturas em vh,
  largura 100vw, max-height e conteúdo absoluto que ultrapasse a página.
- Não use overflow:auto, overflow:scroll ou contêiner rolável dentro de uma
  folha. Não esconda excesso com overflow:hidden/clip, line-clamp ou elipses.
  Se não couber, mova blocos inteiros para outra section data-ied-page, repita
  o cabeçalho necessário e preserve todo o conteúdo. Nunca reduza fonte até
  ficar ilegível. Não simule páginas usando abas, JavaScript ou um único bloco
  muito alto. A navegação/rolagem entre folhas pertence à interface.
- Inclua @page com A4 e orientação correta, margin:0; e CSS de impressão:
  body > [data-ied-page] { break-after:page; page-break-after:always; }
  body > [data-ied-page]:last-of-type { break-after:auto; page-break-after:auto; }
  Use dimensões fixas da folha também na tela; conteúdo deve caber nelas.
- No editor, valide com html_pdf_tools.py e confira que a quantidade de páginas
  do PDF corresponde aos delimitadores. Corrija estouro antes de concluir.
  Na tela restrita, faça a conferência estrutural do HTML salvo, sem alegar
  validação visual/PDF indisponível. Preserve páginas ao fazer edições pontuais.
""".strip()

SUGGESTED_CHAT_RULES = """
RESPOSTAS CURTAS NA ABA AUDIÊNCIAS SUGERIDAS
- Por padrão, até 80 palavras, de 2 a 4 frases e no máximo uma pergunta.
  Detalhe além disso somente se o professor pedir explicação ou comparação.
- A lista completa de audiências, títulos, resumos e assuntos deve ficar no
  planning.json e no painel esquerdo, NÃO duplicada no chat. Após a busca,
  destaque em uma frase a pertinência das opções e peça uma escolha no painel.
- Depois da escolha, ofereça no máximo dois recortes em uma frase cada.
  Não recite a fonte, o catálogo de turmas, os critérios ou o plano completo.
- Depois de gerar, confirme brevemente o que ficou pronto e uma ressalva
  indispensável, se houver. O conteúdo detalhado pertence ao material.
""".strip()
