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
3. Não tente instalar nada nem chamar ferramentas de conversão — o entregável é o
`.html` em si.
4. Você pode consultar as bibliotecas existentes para lhe auxiliar no visual.

## Imagens e arquivos anexados

Quando o usuário anexar uma imagem ou outro arquivo, ele ficará disponível na
raiz do sandbox. No `HTML.html`, referencie-o pelo nome relativo, por exemplo:

```html
<img src="UFCG-Central.png" alt="Logo UFCG">
```

Não converta a imagem para Base64 sem necessidade. O sistema serve os arquivos
do sandbox junto com o HTML, permitindo que referências relativas funcionem no
preview e na sessão atual. Antes de concluir, confirme com `ls -la` que o nome
do arquivo usado no HTML corresponde exatamente ao arquivo anexado.

# Página A4 Editável (HTML com seções clicáveis)

Gera uma página HTML de largura/altura reais de A4 (210mm × 297mm), com a
aparência de um documento institucional impresso (título centralizado,
seções com cabeçalho em negrito, parágrafos justificados, listas com
marcador, rodapé de fontes). Cada bloco de conteúdo fica dentro de uma
`<div class="secao">` com **id único**. Ao clicar numa seção, abre-se um
campo de anotação ali mesmo, onde o usuário escreve o que quer mudar
naquele trecho. Um painel lateral fixo reúne todas as anotações feitas e
oferece um botão para copiá-las em formato de lista (`id: alteração`),
pronto para o usuário colar de volta na conversa e pedir a edição.

Esse padrão é útil como **etapa intermediária de revisão**: em vez de o
usuário reescrever tudo em prosa, ele aponta exatamente qual seção quer
mexer e o que quer mudar nela.

## Quando usar

- Pedido explícito de página/folha em formato A4, ofício, memorando, edital,
  manual institucional, norma interna, comunicado.
- Usuário envia uma imagem/print de um documento formal e pede para "reproduzir",
  "recriar" ou "montar isso em HTML".
- Usuário quer um rascunho de documento onde ele possa clicar nas partes e indicar
  mudanças antes da versão final.

Não usar quando o pedido é apenas "escrever um texto/relatório" sem
menção a formato de página, impressão ou revisão por seções — nesse caso
um `.md` ou `.docx` simples resolve melhor (ver skill `docx`).

## 1. Estrutura da página (dimensões reais de A4)

Sempre usar `mm` para as dimensões da folha, não `px` nem `%`. Isso garante
que, ao imprimir (Ctrl+P → salvar como PDF), o resultado saia exatamente
no tamanho A4.

```css
body {
  margin: 0;
  background: #9a9a9a; /* fundo cinza fora da folha, só para visualização em tela */
  font-family: 'Times New Roman', Times, serif;
  display: flex;
  justify-content: center;
}

.folha-a4 {
  width: 210mm;
  min-height: 297mm;
  padding: 20mm 25mm;
  margin: 10mm auto;
  background: #fff;
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.35);
  box-sizing: border-box;
  position: relative;
  font-size: 12pt;
  line-height: 1.4;
  color: #111;
}

/* Ao imprimir, remove fundo cinza, sombra e margem extra */
@media print {
  body { background: none; display: block; }
  .folha-a4 { margin: 0; box-shadow: none; }
  .secao:hover { background: none !important; outline: none !important; }
  .anotacao, #painel-alteracoes, .rotulo-secao { display: none !important; }
}
```

Para documentos com mais de uma página, repita `.folha-a4` quantas vezes
for preciso e adicione `page-break-after: always;` em todas menos a
última (dentro do `@media print`).

Tipografia típica desse tipo de documento (ajuste ao que a imagem/pedido mostrar):
- Título do documento: negrito, centralizado, ~13–14pt.
- Cabeçalho de seção: negrito, versalete/maiúsculo, ~12pt, seguido de ponto final.
- Corpo: parágrafos justificados, 12pt, espaçamento 1.4–1.5.
- Listas: marcador `•`, recuo simples.
- Rodapé de fontes/referências: fonte menor (~9–10pt), no fim da página.

## 2. Seções em div com id único

Cada unidade lógica do documento (título, cada seção com seu cabeçalho,
rodapé) vira uma `<div class="secao">`. Regras:

- `id` único, kebab-case, descritivo do conteúdo (`sec-titulo`,
  `sec-abertura-processos`, `sec-rodape`) — nunca `sec-1`, `sec-2`.
- `data-nome-secao="Rótulo curto e legível"` — aparece no hover e no
  painel de alterações.
- Não dividir demais: um parágrafo isolado não precisa virar seção própria;
  agrupe pelo cabeçalho/bloco temático, do jeito que uma pessoa apontaria
  "quero mudar essa parte aqui".

```html
<div class="secao" id="sec-titulo" data-nome-secao="Título do documento">
  <h1>Informações sobre o manuseio de processos</h1>
</div>

<div class="secao" id="sec-abertura-processos" data-nome-secao="Abertura de Processos e Expedientes">
  <h2>ABERTURA DE PROCESSOS E EXPEDIENTES.</h2>
  <ul>
    <li>Os Órgãos das Unidades devem solicitar a abertura de Processo ou de
    Expediente por meio de memorando, o qual deverá conter texto sugerindo
    o "Assunto" e "Interessado" da capa do P/E.</li>
    <li>A Seção Técnica de Comunicações deve registrar os Processos,
    inserindo os dados no Sistema de Protocolo e autuar processos, contendo
    etiqueta de identificação e os documentos iniciais recebidos para a
    abertura, em ordem cronológica, com todas as folhas numeradas e
    rubricadas.</li>
  </ul>
</div>
```

## 3. Interatividade: clicar para marcar uma mudança

Ao clicar em qualquer `.secao`, abre um campo de texto **dentro dela**
(não um `alert`/`prompt` do navegador — fica feio e trava a tela). A
seção marcada ganha uma borda lateral colorida. Um painel fixo no canto
mostra todas as marcações e permite copiar tudo formatado.

```css
.secao {
  position: relative;
  cursor: pointer;
  padding: 6px 10px;
  margin: 0 -10px 14px -10px;
  border-radius: 4px;
  border-left: 4px solid transparent;
  transition: background 0.15s, border-color 0.15s;
}
.secao:hover {
  background: rgba(255, 200, 0, 0.12);
}
.secao:hover .rotulo-secao {
  opacity: 1;
}
.secao.marcada {
  border-left-color: #e04b4b;
  background: rgba(224, 75, 75, 0.06);
}
.rotulo-secao {
  position: absolute;
  top: -9px;
  right: 2px;
  background: #333;
  color: #fff;
  font-family: Arial, sans-serif;
  font-size: 9px;
  padding: 1px 6px;
  border-radius: 3px;
  opacity: 0;
  transition: opacity 0.15s;
  pointer-events: none;
}
.anotacao {
  margin-top: 8px;
  font-family: Arial, sans-serif;
}
.anotacao textarea {
  width: 100%;
  box-sizing: border-box;
  font-family: Arial, sans-serif;
  font-size: 11px;
  padding: 6px;
  border: 1px solid #e04b4b;
  border-radius: 4px;
  resize: vertical;
}
#painel-alteracoes {
  position: fixed;
  top: 16px;
  right: 16px;
  width: 260px;
  max-height: 80vh;
  overflow-y: auto;
  background: #fff;
  border: 1px solid #ccc;
  border-radius: 8px;
  box-shadow: 0 4px 14px rgba(0,0,0,0.2);
  font-family: Arial, sans-serif;
  font-size: 12px;
  padding: 12px;
  display: none;
  z-index: 999;
}
#painel-alteracoes h3 { margin: 0 0 8px; font-size: 13px; }
#painel-alteracoes ul { list-style: none; margin: 0 0 10px; padding: 0; }
#painel-alteracoes li { margin-bottom: 8px; line-height: 1.35; }
#painel-alteracoes button {
  width: 100%;
  padding: 6px;
  border: none;
  border-radius: 5px;
  background: #2563eb;
  color: #fff;
  cursor: pointer;
  font-size: 12px;
}
```

```html
<div id="painel-alteracoes">
  <h3>Alterações marcadas</h3>
  <ul id="lista-alteracoes"></ul>
  <button onclick="copiarAlteracoes()">Copiar tudo</button>
</div>
```

```js
const alteracoes = {}; // id da seção -> texto pedido pelo usuário

document.querySelectorAll('.secao').forEach(div => {
  // rótulo que aparece no hover
  const rotulo = document.createElement('span');
  rotulo.className = 'rotulo-secao';
  rotulo.textContent = div.dataset.nomeSecao || div.id;
  div.appendChild(rotulo);

  div.addEventListener('click', (e) => {
    // clique dentro da própria caixa de anotação não deve reabrir/fechar
    if (e.target.closest('.anotacao')) return;
    alternarAnotacao(div);
  });
});

function alternarAnotacao(div) {
  let caixa = div.querySelector('.anotacao');
  if (caixa) { caixa.remove(); return; }

  caixa = document.createElement('div');
  caixa.className = 'anotacao';
  caixa.innerHTML = `<textarea rows="2" placeholder="O que você quer mudar aqui?"></textarea>`;
  div.appendChild(caixa);

  const textarea = caixa.querySelector('textarea');
  textarea.value = alteracoes[div.id] || '';
  textarea.focus();
  textarea.addEventListener('input', () => {
    const texto = textarea.value.trim();
    if (texto) {
      alteracoes[div.id] = texto;
      div.classList.add('marcada');
    } else {
      delete alteracoes[div.id];
      div.classList.remove('marcada');
    }
    atualizarPainel();
  });
}

function atualizarPainel() {
  const painel = document.getElementById('painel-alteracoes');
  const lista = document.getElementById('lista-alteracoes');
  const ids = Object.keys(alteracoes);
  lista.innerHTML = ids.map(id => {
    const nome = document.getElementById(id)?.dataset.nomeSecao || id;
    return `<li><strong>${nome}</strong><br>${alteracoes[id]}</li>`;
  }).join('');
  painel.style.display = ids.length ? 'block' : 'none';
}

function copiarAlteracoes() {
  const linhas = Object.entries(alteracoes)
    .map(([id, texto]) => `- ${id}: ${texto}`);
  const texto = linhas.join('\n');
  navigator.clipboard?.writeText(texto);
  alert('Alterações copiadas. Cole na conversa para pedir a revisão dessas partes.');
}
```

## 4. Montagem do arquivo final

Um único arquivo `.html` autocontido: `<style>` no `<head>`, o `<div
class="folha-a4">` com as seções no `<body>`, e o `<script>` no fim do
`<body>`. Não usar frameworks — é HTML/CSS/JS puro, sem build.

Esqueleto:

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Nome do documento</title>
<style>
  /* CSS das seções 1 e 3 aqui */
</style>
</head>
<body>

<div class="folha-a4">
  <div class="secao" id="sec-titulo" data-nome-secao="Título">...</div>
  <div class="secao" id="sec-..." data-nome-secao="...">...</div>
  <!-- demais seções -->
</div>

<div id="painel-alteracoes">
  <h3>Alterações marcadas</h3>
  <ul id="lista-alteracoes"></ul>
  <button onclick="copiarAlteracoes()">Copiar tudo</button>
</div>

<script>
  /* JS da seção 3 aqui */
</script>
</body>
</html>
```

## 5. Checklist antes de entregar

- [ ] Folha mede exatamente `210mm` × `297mm` (min-height), com padding em `mm`.
- [ ] Todo bloco de conteúdo está dentro de uma `.secao` com `id` único e `data-nome-secao`.
- [ ] Nenhum `id` duplicado (checar visualmente ou com um `grep 'id="sec-'` no arquivo).
- [ ] Clicar em qualquer seção abre/fecha a caixa de anotação sem recarregar a página nem afetar outras seções.
- [ ] O painel lateral só aparece quando existe pelo menos uma alteração marcada.
- [ ] `@media print` esconde painel, caixas de anotação e realces — a versão impressa fica limpa, só o conteúdo do documento.
- [ ] Fontes/estilo (serifada para o corpo, negrito nos cabeçalhos, texto justificado) batem com o que o usuário pediu ou com a imagem de referência enviada.
- [ ] Se o documento tiver mais de uma página, cada página é uma `.folha-a4` separada, com quebra de página no `@media print`.
- [ ] CSS no mermo arquivo HTML.

## 6. Exemplo completo de referência

Veja `assets/exemplo-manuseio-processos.html` — reprodução completa de um
documento institucional real (manual de manuseio de processos, com
título, três seções e rodapé de fontes) já com todas as seções clicáveis
e o painel de alterações funcionando. Use como ponto de partida: copie a
estrutura e troque o conteúdo das `.secao` pelo texto do novo documento.
