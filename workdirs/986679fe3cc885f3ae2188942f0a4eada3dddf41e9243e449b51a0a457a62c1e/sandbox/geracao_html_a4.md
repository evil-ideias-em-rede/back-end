---
nome: geracao_html_a4
quando_usar: >
  O usuário pede um documento, relatório, ficha, proposta, cardápio,
  currículo ou material visual em HTML cujo resultado final precisa manter
  as proporções de uma folha impressa (A4), porque será convertido para PDF
  mais adiante — mesmo que a conversão em si não aconteça agora. Não use
  este guia para HTML solto/interativo pensado só pra tela (dashboard,
  landing page, formulário dinâmico): para isso, siga apenas o README
  genérico do sandbox sobre como montar um HTML bem-feito. Este guia é uma
  camada ADICIONAL de regras, específica para quando o HTML precisa se
  comportar como página(s) de documento.
---

# Como gerar HTML no formato de folha A4 (pronto para virar PDF depois)

Você tem acesso à ferramenta `execute_bash`, que executa comandos num
sandbox. Não existe geração de PDF nesta etapa — o entregável aqui é
sempre um arquivo `HTML.html` autocontido que já existe dentro do sandbox.
A conversão para PDF é um passo futuro e separado, feito fora deste fluxo;
seu trabalho é garantir que o HTML já nasça com as proporções e a estrutura
corretas para que essa conversão, quando acontecer, não distorça nada.

## Fluxo recomendado

1. Manipule o HTML completo no arquivo HTML.html.
2. Rode `ls -la HTML.html` para confirmar que o arquivo existe e tem tamanho > 0.
3. Não tente instalar nada nem chamar ferramentas de conversão — o entregável é o `.html` em si.
4. Você pode consultar as bibliotecas existentes para lhe auxiliar no visual.

## Estrutura de página obrigatória

- Cada página do documento é uma `<div class="pagina">` com dimensões
  fixas de **210mm × 297mm** (A4 retrato). Documentos de uma página só
  precisam de uma `div`; documentos maiores usam uma `div.pagina` por
  página.
- Use `box-sizing: border-box` e padding interno de **20mm** em todos os
  lados como margem de conteúdo (equivalente aos ~2,2cm usados nos PDFs
  gerados via reportlab — mantém a mesma identidade visual entre os dois
  formatos, caso o usuário compare os dois).
- Dimensões, margens e padding da página sempre em unidades absolutas
  (`mm`, `cm`, `pt`) — **nunca** `%`, `vw`, `vh`. Essas unidades dependem
  do viewport do navegador, não da folha física, e a proporção A4 quebra
  assim que o HTML for aberto numa tela de tamanho diferente ou
  processado por um conversor.
- Tamanho de fonte em `pt`, não em `px` ou `rem` — é a unidade que
  corresponde ao que se espera de um documento impresso.
- Dentro de `@media print`, aplique `break-after: page;` (ou
  `page-break-after: always;` para compatibilidade com motores mais
  antigos) em toda `.pagina` exceto a última. Isso garante paginação
  correta tanto se alguém usar "Imprimir → Salvar como PDF" do navegador
  quanto se um conversor baseado em Chromium for usado depois.
- Declare `@page { size: A4; margin: 0; }` no topo do `<style>` — a margem
  real já está sendo controlada pelo padding da `.pagina`, não pelo
  `@page`, para o resultado ficar idêntico entre a visualização em tela e
  a impressão.

## Esqueleto pronto para copiar

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Título do Documento</title>
<style>
  :root {
    --cor-primaria: #1F3A5F;   /* títulos, cabeçalho de tabela */
    --cor-secundaria: #4A7C9E; /* acentos, subtítulos */
    --cor-texto: #222222;
    --cor-texto-claro: #666666;
    --cor-linha: #D8DEE4;
    --cor-fundo-alt: #F4F6F8; /* zebra striping em tabelas */
  }

  @page { size: A4; margin: 0; }

  * { box-sizing: border-box; }

  body {
    margin: 0;
    font-family: Helvetica, Arial, sans-serif; /* web-safe, ver seção Fontes */
    color: var(--cor-texto);
    background: #E9E9E9; /* só visível na tela, some na impressão */
  }

  .pagina {
    width: 210mm;
    min-height: 297mm;
    padding: 20mm;
    margin: 0 auto 8mm auto; /* espaçamento entre páginas só na tela */
    background: white;
    position: relative;
  }

  @media print {
    body { background: none; }
    .pagina { margin: 0; break-after: page; page-break-after: always; }
    .pagina:last-child { break-after: auto; page-break-after: auto; }
  }

  h1 { font-size: 18pt; color: var(--cor-primaria); margin: 0 0 10pt 0; }
  h2 { font-size: 13pt; color: var(--cor-secundaria); margin: 14pt 0 6pt 0; }
  p, li { font-size: 10.5pt; line-height: 1.5; }

  table { width: 100%; border-collapse: collapse; margin: 8pt 0; }
  thead th {
    background: var(--cor-primaria); color: white;
    font-size: 9.5pt; text-align: left; padding: 6pt 8pt;
  }
  tbody td {
    font-size: 9.5pt; padding: 6pt 8pt;
    border-bottom: 0.5pt solid var(--cor-linha);
  }
  tbody tr:nth-child(even) { background: var(--cor-fundo-alt); }

  .rodape {
    position: absolute; bottom: 10mm; left: 20mm; right: 20mm;
    display: flex; justify-content: space-between;
    font-size: 8pt; color: var(--cor-texto-claro);
    border-top: 0.5pt solid var(--cor-linha); padding-top: 4pt;
  }
</style>
</head>
<body>

  <div class="pagina">
    <h1>Título do Documento</h1>
    <p>Texto corrido normal.</p>

    <h2>Nome da Seção</h2>
    <table>
      <thead><tr><th>Coluna 1</th><th>Coluna 2</th><th>Coluna 3</th></tr></thead>
      <tbody>
        <tr><td>a</td><td>b</td><td>c</td></tr>
        <tr><td>d</td><td>e</td><td>f</td></tr>
      </tbody>
    </table>

    <div class="rodape">
      <span>Título do Documento</span>
      <span>Página 1</span>
    </div>
  </div>

  <!-- Página 2: repita a estrutura acima, trocando o conteúdo e o número
       da página no rodapé. Não existe numeração automática garantida
       entre motores de conversão diferentes — escreva o número manualmente. -->

</body>
</html>
```

## Imagens

Este HTML precisa ser autocontido — sem links para arquivos externos que
podem não existir mais na hora da conversão futura:

- **Gráfico simples (barras, linhas, pizza)**: prefira **SVG inline**
  direto no HTML em vez de gerar um PNG. Escala sem perda e não depende
  de base64.
- **Gráfico mais complexo ou foto real**: converta o arquivo para base64
  e embuta com `<img src="data:image/png;base64,....">`.
- **Nunca** use `<img src="http://...">` apontando para uma URL externa —
  o sandbox pode não ter rede, e o passo futuro de conversão para PDF
  também pode rodar sem rede.

## Fontes

Use só fontes web-safe: `Arial`, `Helvetica`, `Georgia`,
`"Times New Roman"`, `"Courier New"`. Não use `<link>` para Google Fonts
ou qualquer CDN de fontes — mesmo motivo do item anterior (sem rede
garantida, nem agora nem na conversão futura). Se uma fonte customizada
for realmente necessária, ela precisa ser embutida via `@font-face` com
o arquivo da fonte em base64 — nunca referenciada por URL.

## Armadilhas comuns (evite estes erros)

- **Conteúdo que estoura os 297mm da `.pagina`**: isso não gera erro
  nenhum agora (o navegador só mostra uma div mais alta), mas quando
  convertido vira texto cortado ou uma quebra de página no lugar errado.
  Se o conteúdo não couber, quebre em mais `div.pagina` — não tente
  encolher fonte pra forçar caber.
- **`%`, `vw`, `vh` na página ou nas margens**: funciona bem visualmente
  na tela, mas destrói a proporção A4 assim que o HTML for aberto num
  viewport diferente ou processado por um conversor.
- **`position: fixed` para cabeçalho/rodapé repetido**: não se comporta
  como "repetir em toda página" fora de um motor de paginação real.
  Repita o cabeçalho/rodapé manualmente dentro de cada `div.pagina`.
- **Numeração de página automática via `counter(page)` do CSS Paged
  Media**: só funciona em motores que implementam essa spec (ex.:
  WeasyPrint, Prince) — não em impressão comum do Chrome nem na maioria
  dos conversores baseados em Puppeteer. Escreva o número da página como
  texto fixo em cada `.pagina`, como no esqueleto acima, pra funcionar
  independente de qual conversor for usado depois.
- **Sombras, gradientes, `filter`/`backdrop-filter`**: suporte parcial
  em conversores mais antigos (ex.: wkhtmltopdf). Se não se sabe qual
  motor será usado depois, prefira bordas finas e cores sólidas.
- **Fonte em `px`**: mistura mal com o resto do documento pensado em
  `mm`/`pt`. Mantenha tudo consistente em unidades físicas.