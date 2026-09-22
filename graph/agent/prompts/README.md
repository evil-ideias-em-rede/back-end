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
| modo de edição | `16-editor-no-documento` |

## Prompts sem node

`10`, `11`, `12`, `13`, `14`, `15`, `17`, `19` e as quatro verificações `30`–`33` estão na library e ainda não têm node. Ficam disponíveis para quando as etapas forem implementadas; `contratos.md`, no sandbox, descreve o encadeamento previsto.
