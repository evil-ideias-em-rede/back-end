# prompts

```
library/        os prompts versionados, em markdown
loader.py       lê a library e resolve as variáveis
audiencias_sugeridas/   composição para os nodes de geração
editor/                 composição para o modo de edição
```

## library/

Um arquivo por prompt, com front-matter YAML (`id`, `system`, `inputs`), um bloco `## SYSTEM` e um bloco `## USER`. As variáveis aparecem como `{{NOME}}`.

`componentes/` traz blocos reutilizáveis — princípios pedagógicos, teorias, regras de uso da fonte e glossário legislativo. O loader os injeta automaticamente nas variáveis correspondentes.

Editar um prompt é editar o markdown. Nada em Python precisa mudar.

## loader.py

```python
from graph.agent.prompts.loader import render

texto = render("20-plano-de-aula")                       # variáveis conhecidas resolvidas
texto = render("13-triagem-de-trechos", {"BRIEFING": b}) # valores explícitos
```

`render` concatena SYSTEM e USER, resolve `{{SYSTEM_GLOBAL}}` e as quatro variáveis de componente, e substitui o que vier em `values`. As variáveis sem valor têm o bloco XML que as envolve removido, de modo que o prompt nunca chega ao modelo com um `{{PLACEHOLDER}}` literal.

`inputs(prompt_id)` lista as variáveis declaradas. `available()` lista os prompts.

## Composição nos nodes

Cada `*_prompt.py` monta o prompt final a partir de três partes: o texto da library, os blocos operacionais de `rules.py` — acervo, neutralidade, planejamento, ponte para o artefato, fluxo do sandbox — e, no modo de edição, o `EDIT_RULES` que `base.py` acrescenta.

| Node | Prompt da library |
|---|---|
| `brainstorm_node` | `18-brainstorm` |
| `lesson_plan_node` | `20-plano-de-aula` |
| `debate_outline_node` | `21-roteiro-de-debate` |
| `writing_workshop_node` | `22-oficina-de-redacao` |
| `slides_node` | `23-slides` |
| `political_leteracy_node` | `24-letramento-midiatico-e-politico` |
| `generic_activity_node` | `25-criacao-livre` |
| `general_editor_node` | `16-editor-no-documento` (somente modo de edição) |
| modo de edição | `16-editor-no-documento` |

## Prompts sem node

`10`, `11`, `12`, `13`, `14`, `15`, `17`, `19` e as quatro verificações `30`–`33` estão na library e ainda não têm node. Ficam disponíveis para quando as etapas forem implementadas; `contratos.md`, no sandbox, descreve o encadeamento previsto.

## Contrato do aplicativo

Os wrappers usam `render_for_agent()`: resolve a biblioteca como `render()`,
mas omite `<output_format>`, cujos contratos XML são de pipelines estruturados.
As regras operacionais determinam a entrega em `HTML.html` e resposta em prosa.
`render()` continua disponível para consumidores do contrato estruturado.

`material_rules.py` define os perfis de plano, debate, redação, letramento,
slides, criação livre e editor geral. No editor, `build_editor_prompt()` combina
o perfil com o prompt 16 e o mapa do acervo. `base.py` acrescenta EDIT_RULES.

Audiências sugeridas só expõe planning.json e HTML.html na ferramenta restrita.
A BNCC e as fontes vêm das ferramentas de consulta; o brainstorm também recebe
consultar_bncc para continuar pedidos de geração após o professor complementar dados.

No editor, o guia ativo é `shared/geral/guia_edicao.md`, copiado à raiz do
sandbox. Templates de plano, formatos e teorias são consultados sob demanda.
Slides seguem A4 paisagem; os demais tipos seguem retrato, conforme o frontend.
O guia não depende das cópias antigas de geracao_html_a4.md nem de prompts/ no
sandbox. Os arquivos antigos não foram removidos ou migrados por esta revisão.

A cópia do acervo só preenche arquivos ausentes: um guia novo chega também a
sessões existentes na próxima ferramenta; alterações em arquivos já copiados
não substituem as versões da sessão. As regras atuais do agente e o guia novo
explicam que o pipeline numerado de contratos antigos não é executado.

Validação local, sem LLM:
`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v`.
