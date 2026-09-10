---
name: geracao_html_a4
description: Ensina a criar páginas HTML no formato de uma folha de ofício/relatório A4 em pé (retrato), organizadas em seções `<div>` com ID único e estável, onde cada seção é clicável — ao clicar, o usuário pode dizer o que quer mudar naquele trecho específico. Use este skill sempre que o usuário pedir ofícios, memorandos, atas, editais, contratos, planos de aula, formulários ou qualquer documento no estilo "folha impressa" A4 que ele queira revisar seção por seção depois. Gatilhos: "folha de ofício", "página A4", "documento clicável", "documento editável por seção", "modelo de documento oficial", ou quando o usuário envia a imagem de um documento formatado pedindo uma versão HTML equivalente.
---

# Folha de Ofício A4 Editável (HTML)

## Quando usar

Use este skill quando o pedido for por um documento HTML que deve **parecer uma folha de papel A4 em pé** (ofício, memorando, ata, edital, plano de aula, contrato, formulário etc.) e onde o usuário vai querer **apontar partes específicas para alterar depois**, em vez de reescrever o documento inteiro a cada rodada de feedback.

A ideia central é simples: cada bloco de conteúdo da folha vira um `<div>` com um **ID único e estável**. Ao clicar nesse bloco, o usuário registra o que quer mudar ali — e nas próximas rodadas, você (Claude) edita só aquele `<div>`, sem tocar no resto do documento.

## Antes de gerar o arquivo: conversar primeiro

Não pule direto para o HTML. Enquanto ainda estiver esclarecendo tema, conteúdo, série/público ou qualquer outro dado necessário, responda em texto normal — só crie o arquivo quando o usuário pedir isso explicitamente ("gera o documento", "monta o HTML", "fecha isso"). Depois que o arquivo existir, qualquer pedido de ajuste é uma edição pontual na seção certa (ver "Depois que o usuário responder", no fim deste guia), nunca uma regeração do zero.

## Passo 1 — Montar a "folha" A4

Uma folha A4 tem 210mm × 297mm. Não precisa converter para pixels: navegadores modernos entendem `mm` direto, e isso deixa a proporção correta tanto na tela quanto na impressão.

```css
:root {
  --largura-folha: 210mm;
  --altura-folha: 297mm;
}

body {
  background: #e8e8e8; /* área cinza ao redor, para a folha branca se destacar */
  margin: 0;
  padding: 32px 16px;
}

.pagina {
  width: var(--largura-folha);
  min-height: var(--altura-folha);
  margin: 0 auto 24px;
  padding: 20mm 22mm; /* margens de um ofício típico */
  background: #fff;
  box-shadow: 0 4px 18px rgba(0, 0, 0, 0.18); /* sombra sutil = "papel sobre a mesa" */
  box-sizing: border-box;
}
```

**Padrão: uma única `.pagina`, contínua, sem abas.** Na grande maioria dos casos (ofício, memorando, plano de aula, formulário) o documento é uma folha só — deixe o conteúdo crescer verticalmente dentro de uma `.pagina` (por isso `min-height`, não `height` fixo) em vez de inventar uma navegação por abas ou "página 1 / página 2" clicável dentro do HTML. Isso quebra a metáfora de folha impressa e adiciona uma camada de JS/estado que ninguém pediu.

Só use mais de uma `.pagina` quando o conteúdo realmente for longo o bastante para exigir múltiplas folhas impressas de verdade (um contrato de 4 páginas, por exemplo). Mesmo nesse caso, é para a **impressão** (`page-break-after`, ver Passo 6) — continue sem tabs ou botões de "próxima página"; o usuário rola a página normalmente na tela.

## Passo 2 — Dividir o conteúdo em seções com ID único

Cada bloco de sentido (título, um item de lista de itens relacionados, um parágrafo, a seção de fontes/rodapé) vira uma `<div class="secao">` com um `id` descritivo. Prefira nomes que descrevam o **conteúdo**, não a posição ("secao-abertura-processos", não "secao-2") — assim o ID continua fazendo sentido mesmo depois de reordenar ou editar o documento.

```html
<div class="secao" id="secao-titulo" data-titulo="Título" onclick="selecionar(this)">
  <h1>INFORMAÇÕES SOBRE O ASSUNTO X</h1>
</div>

<div class="secao" id="secao-abertura" data-titulo="Abertura de processos" onclick="selecionar(this)">
  <h2>ABERTURA DE PROCESSOS.</h2>
  <ul>
    <li>Primeiro ponto sobre o procedimento.</li>
    <li>Segundo ponto, com detalhes adicionais.</li>
  </ul>
</div>
```

Duas regras evitam dor de cabeça depois:
- **Não aninhe `<div class="secao">` uma dentro da outra.** Se um clique precisa "borbulhar" por duas seções sobrepostas, o usuário nunca vai saber qual delas está editando. Mantenha uma estrutura plana: uma seção, um bloco de conteúdo.
- **IDs são para sempre.** Quando o usuário disser "na secao-abertura, troque X por Y", você deve localizar exatamente essa `div` no arquivo e editar só ela com `str_replace` — é para isso que o ID serve. Não regenere o arquivo inteiro a cada pedido de ajuste; isso desperdiça contexto e arrisca mudar coisas que o usuário não pediu.

### Convenções de ID por tipo de documento

Ter um padrão de nomes por tipo de documento facilita tanto a sua vida (editar depois) quanto a de outros agentes/pipelines que gerem o mesmo tipo de peça repetidamente:

| Tipo de documento | IDs sugeridos |
|---|---|
| Ofício / memorando | `secao-titulo`, `secao-abertura`, `secao-tramite`, `secao-conservacao`, `secao-fontes` |
| Plano de aula | `secao-titulo`, `secao-objetivos`, `secao-materiais`, `secao-etapas`, `secao-avaliacao`, `secao-adaptacao`, `secao-referencias` |
| Ata de reunião | `secao-titulo`, `secao-participantes`, `secao-pauta`, `secao-deliberacoes`, `secao-encaminhamentos` |
| Contrato / termo | `secao-titulo`, `secao-partes`, `secao-objeto`, `secao-clausulas`, `secao-assinaturas` |

Se o pedido não se encaixar em nenhuma dessas categorias, invente IDs seguindo o mesmo espírito (descritivos, em kebab-case, prefixados com `secao-`) em vez de forçar um encaixe.

## Passo 3 — Tornar as seções clicáveis

Existem dois contextos possíveis, e o comportamento certo depende de qual deles você está usando. Em nenhum dos dois a seção deve abrir um modal ou caixa de texto pedindo "o que você quer mudar" — isso é papel de outro componente fora do HTML (um campo de mensagem, o próprio chat, uma extensão). O trabalho da `.secao` é só parecer clicável e mostrar visualmente qual está selecionada; o `id` e o conteúdo já estão no DOM para quem for capturar a informação.

**A) Página HTML autônoma (artifact/arquivo para o usuário salvar ou imprimir)** — o clique apenas destaca a seção selecionada, nada mais:

```css
.secao {
  position: relative;
  padding: 10px 14px;
  margin: 0 -14px 14px;
  border-radius: 6px;
  cursor: pointer;
}
.secao:hover {
  background: rgba(124, 58, 237, 0.08);
  outline: 1px dashed #7C3AED;
}
.secao.selecionada {
  background: rgba(124, 58, 237, 0.08);
  outline: 2px solid #7C3AED;
}
```

```javascript
function selecionar(el) {
  document.querySelectorAll('.secao').forEach(s => s.classList.remove('selecionada'));
  el.classList.add('selecionada');
}
```

Se a integração precisar ser avisada explicitamente de qual seção foi clicada (por exemplo, um app por fora escutando via `postMessage`), adicione isso dentro da mesma função — mas não construa um campo de texto ou painel de anotações dentro do HTML para capturar a mensagem; isso não é responsabilidade desta página.

**B) Dentro do widget do Visualizer (`visualize:show_widget`)** — esse ambiente expõe uma função global `sendPrompt(texto)` que manda a mensagem direto para o chat, como se o usuário tivesse digitado:

```html
<div class="secao" id="secao-abertura" data-titulo="Abertura de processos"
     onclick="sendPrompt('Quero alterar a seção &quot;' + this.dataset.titulo + '&quot; (id: secao-abertura).')">
  ...
</div>
```

Use (A) por padrão — é o caminho mais comum, funciona em qualquer artifact HTML salvo ou baixado. Só use (B) quando o pedido for explicitamente para gerar o documento como visual inline via o Visualizer.

## Passo 4 — Sumário com âncoras (opcional, para documentos longos)

Como a folha é uma página só (Passo 1) e não tem abas, a forma de navegar num documento longo é um pequeno sumário no topo com links âncora apontando para os IDs das seções — sem duplicar a navegação com JS:

```html
<style>
  html { scroll-behavior: smooth; }
  .sumario {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 16px;
    font-family: sans-serif;
    font-size: 12px;
    margin-bottom: 20px;
    padding-bottom: 12px;
    border-bottom: 1px solid #ddd;
  }
  .sumario a { color: #7C3AED; text-decoration: none; }
  .sumario a:hover { text-decoration: underline; }
  @media print { .sumario { display: none; } } /* é uma ajuda de tela, não faz parte do documento impresso */
</style>

<nav class="sumario">
  <a href="#secao-objetivos">Objetivos</a>
  <a href="#secao-materiais">Materiais</a>
  <a href="#secao-etapas">Etapas</a>
  <a href="#secao-avaliacao">Avaliação</a>
</nav>
```

Use só quando o documento tiver várias seções (a partir de ~4-5) — num ofício curto de duas seções, o sumário é ruído. O `<nav>` fica fora das `.secao`, porque ele não é conteúdo editável: clicar num link deve rolar a página, não abrir o prompt de "o que quer mudar".

## Passo 5 — Estilo visual

O formato A4 + seções é a estrutura; a aparência (tipografia, cores, se é um ofício formal em preto e branco ou algo mais colorido como um plano de aula) depende do que o usuário pediu ou do exemplo que ele mandou. Se ele enviou uma imagem de referência, replique a hierarquia visual dela (título centralizado, cabeçalhos de seção em caixa alta e negrito, listas com marcadores, rodapé de fontes em fonte menor) antes de inventar um estilo novo. Para decisões de paleta e tipografia quando não há referência clara, consulte o skill `frontend-design`.

## Componentes visuais comuns

Alguns tipos de documento pedem elementos além de título/parágrafo/lista — uma linha do tempo de etapas, uma tabela de materiais, uma checklist de avaliação. Todos seguem a mesma regra: vivem **dentro** de uma `.secao` (o bloco inteiro é editável e comentável como uma unidade), e qualquer elemento interativo próprio (como um checkbox) precisa de `event.stopPropagation()` para não disparar o clique da seção por baixo.

```html
<div class="secao" id="secao-etapas" data-titulo="Etapas" onclick="selecionar(this)">
  <h2>DESENVOLVIMENTO</h2>
  <div style="display:flex; gap:8px;">
    <div style="flex:1; padding:8px; background:#f5f3ff; border-radius:6px; font-size:12px;">
      <b>Abertura</b><br>10 min
    </div>
    <div style="flex:1; padding:8px; background:#f5f3ff; border-radius:6px; font-size:12px;">
      <b>Desenvolvimento</b><br>30 min
    </div>
    <div style="flex:1; padding:8px; background:#f5f3ff; border-radius:6px; font-size:12px;">
      <b>Fechamento</b><br>10 min
    </div>
  </div>
</div>

<div class="secao" id="secao-avaliacao" data-titulo="Avaliação" onclick="selecionar(this)">
  <h2>AVALIAÇÃO</h2>
  <label style="display:block;" onclick="event.stopPropagation()">
    <input type="checkbox"> Participação nas discussões
  </label>
  <label style="display:block;" onclick="event.stopPropagation()">
    <input type="checkbox"> Produção escrita entregue
  </label>
</div>
```

Tabelas de materiais seguem a mesma lógica: um `<table>` comum dentro da `.secao`, sem nada de especial.

## Passo 6 (opcional) — Preparar para impressão real

```css
@media print {
  body { background: none; padding: 0; }
  .pagina { box-shadow: none; margin: 0; page-break-after: always; } /* só importa quando há mais de uma .pagina de verdade — ver Passo 1 */
  .secao:hover, .secao.selecionada { outline: none; background: none; }
  .sumario { display: none; }
}
@page { size: A4; margin: 0; }
```

## Exemplo completo

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Modelo de Ofício A4 Editável</title>
<style>
  :root { --accent: #7C3AED; }
  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  body {
    background: #e8e8e8;
    margin: 0;
    padding: 32px 16px;
    font-family: Georgia, 'Times New Roman', serif;
    color: #1a1a1a;
  }
  .sumario {
    display: flex; flex-wrap: wrap; gap: 4px 16px;
    font-family: sans-serif; font-size: 12px;
    margin-bottom: 20px; padding-bottom: 12px; border-bottom: 1px solid #ddd;
  }
  .sumario a { color: var(--accent); text-decoration: none; }
  .sumario a:hover { text-decoration: underline; }
  .pagina {
    width: 210mm;
    min-height: 297mm;
    margin: 0 auto 24px;
    padding: 20mm 22mm;
    background: #fff;
    box-shadow: 0 4px 18px rgba(0,0,0,0.18);
  }
  h1 { font-size: 20px; text-align: center; margin: 0 0 24px; }
  h2 { font-size: 15px; margin: 0 0 8px; }
  .secao {
    position: relative;
    padding: 10px 14px;
    margin: 0 -14px 14px;
    border-radius: 6px;
    cursor: pointer;
  }
  .secao:hover { background: rgba(124,58,237,.08); outline: 1px dashed var(--accent); }
  .secao.selecionada { background: rgba(124,58,237,.08); outline: 2px solid var(--accent); }
  @media print {
    body { background: none; padding: 0; }
    .pagina { box-shadow: none; margin: 0; page-break-after: always; }
    .sumario { display: none; }
  }
  @page { size: A4; margin: 0; }
</style>
</head>
<body>

  <div class="pagina">
    <div class="secao" id="secao-titulo" data-titulo="Título" onclick="selecionar(this)">
      <h1>INFORMAÇÕES SOBRE O ASSUNTO X</h1>
    </div>

    <nav class="sumario">
      <a href="#secao-abertura">Abertura de processos</a>
      <a href="#secao-tramite">Trâmite</a>
      <a href="#secao-fontes">Fontes</a>
    </nav>

    <div class="secao" id="secao-abertura" data-titulo="Abertura de processos" onclick="selecionar(this)">
      <h2>ABERTURA DE PROCESSOS.</h2>
      <ul>
        <li>Primeiro ponto sobre o procedimento.</li>
        <li>Segundo ponto, com detalhes adicionais.</li>
      </ul>
    </div>

    <div class="secao" id="secao-tramite" data-titulo="Trâmite" onclick="selecionar(this)">
      <h2>TRÂMITE.</h2>
      <p>Texto explicando como o processo deve tramitar entre setores.</p>
    </div>

    <div class="secao" id="secao-fontes" data-titulo="Fontes" onclick="selecionar(this)">
      <p style="font-size:12px;color:#555;">Fontes: ...</p>
    </div>
  </div>

<script>
  function selecionar(el) {
    document.querySelectorAll('.secao').forEach(s => s.classList.remove('selecionada'));
    el.classList.add('selecionada');
  }
</script>
</body>
</html>
```

## Depois que o usuário responder

Quando o usuário voltar com algo como "na secao-tramite, deixa mais direto" (seja digitando direto no chat, seja através de outro input que te repasse o `id` clicado + a mensagem), abra o arquivo, encontre a `<div id="secao-tramite">` correspondente e edite só o conteúdo interno dela com `str_replace` — mantendo o `id`, a classe `secao` e o `data-titulo` intactos, para que a seção continue clicável e reconhecível nas próximas rodadas.

## Nota: uso como arquivo de convenções compartilhado

Se este conteúdo também for carregado por outro agente/pipeline via linha de comando (ex.: um prompt de sistema que roda `cat geracao_html_a4.md` no início do fluxo, antes de escrever o HTML), trate as duas cópias como uma coisa só: qualquer regra nova adicionada aqui precisa ir para essa cópia também, ou os agentes que a carregam vão divergir do skill silenciosamente.