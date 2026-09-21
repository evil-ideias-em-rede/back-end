# Contratos

## Encadeamento

```
mensagem do professor
  → 10 roteador                      → rota + campos extraídos
  → 11 briefing                      → BRIEFING
  → 12 consultas                     → queries
  → [RAG]                            → RETRIEVED_FALAS
  → 13 triagem                       → EXCERPTS, STANCE_MAP, COVERAGE_REPORT    ← professor verifica
  → 18 brainstorm                    → PLANNING_NOTES                           ← conversa com o professor
  → 14 formato       ─┐                                                         ← professor escolhe
  → 15 BNCC          ─┼─ em paralelo                                            ← professor confirma
  → 17 teoria        ─┘                                                         ← professor é informado
  → 19 especificação                 → SPECIFICATION, OPEN_QUESTIONS            ← professor inspeciona
  → 20..25 geração                   → GENERATED_DOCUMENT, SOURCE_ANALYSIS, PLANNING
  → 30..33 verificação (paralelo)    → verdict + findings
  → professor
  → 16 editor (a cada ajuste pedido)
```

`18` roda depois que o professor verifica os trechos: ele propõe recortes possíveis a partir do que o material sustenta, conversa, e fecha um planejamento. `14`, `15` e `17` usam esse planejamento como entrada; `17` roda depois de `14`, porque usa o formato escolhido como um dos critérios. `19` consolida tudo em uma especificação de requisitos, que é o que os geradores obedecem. O professor não nomeia a teoria: `17` a deduz do pedido em linguagem natural e devolve a justificativa em `message_to_teacher`, que vai para o chat ou para a nota do plano.

## Variáveis

| Variável | Produzida por | Consumida por |
|---|---|---|
| `SYSTEM_GLOBAL` | `00` | 11, 13, 14, 16, 20–25 |
| `USER_MESSAGE`, `SESSION_STATE`, `RECENT_TURNS` | aplicação | 10, 11 |
| `PARTIAL_BRIEFING` | aplicação | 11 |
| `BRIEFING` | `11` | 12–15, 17–25, 31 |
| `PLANNING_NOTES` | `18` | 14, 17, 19 |
| `SPECIFICATION`, `OPEN_QUESTIONS` | `19` | 20–25 |
| `PREVIOUS_QUERIES` | aplicação | 12 |
| `RETRIEVED_FALAS` | recuperação semântica, falas anotadas | 13 |
| `DEBATE_METADATA` | banco, sobre o debate escolhido | 12, 13 |
| `EXCERPTS` | `13` | 16, 18, 19, 20–25, 30, 33 |
| `STANCE_MAP` | `13` | 14, 15, 17, 18, 19, 20–25, 33 |
| `COVERAGE_REPORT` | `13` | 14, 18, 19, 20–25 |
| `FORMAT_INDEX` | `formatos-de-aula/_indice.md` | 14, 25 |
| `LESSON_FORMAT` | `formatos-de-aula/<escolhido>.md` | 19, 20–24 |
| `LESSON_FORMAT_SUMMARY` | idem, resumido | 15, 17 |
| `BNCC_CANDIDATES` | `dados/bncc.csv` filtrado | 15, 32 |
| `SELECTED_SKILLS` → `BNCC_SKILLS` | `15` | 19, 20–25, 32 |
| `THEORY_INDEX` | `teorias/_indice.md` | 17 |
| `TEACHER_REQUEST` | professor, texto literal | 17 |
| `THEORY` | `teorias/<escolhida>.md` | 19, 20–25 |
| `HTML_TEMPLATE` | `templates/<escolhido>.html` | 20 |
| `TEACHER_MATERIALS` | arquivos cadastrados pelo professor | 20–25 |
| `TEXT_GENRE` | professor | 22 |
| `PRESS_ITEMS` | professor, opcional | 24 |
| `FREE_REQUEST` | professor | 25 |
| `EDIT_REQUEST`, `CURRENT_DOCUMENT` | professor e aplicação | 16 |
| `PEDAGOGICAL_PRINCIPLES`, `SOURCE_RULES`, `LEGISLATIVE_GLOSSARY`, `THEORY_USAGE` | `prompts/componentes/` | 12–16, 20–25, 31 |
| `GENERATED_DOCUMENT`, `SOURCE_ANALYSIS`, `PLANNING` | `20`–`25` | 30–33 |

## Modelo de dados do debate

A unidade é a **fala**: tudo o que um participante disse até passar a palavra. A anotação incide sobre a fala inteira.

**Fala anotada** — o que a recuperação devolve, entrada de `13`:

```json
{
  "id": "f00006",
  "ordem_no_debate": 6,
  "texto": "…",
  "taxonomia": {
    "Alinhamento Temático": ["Focalizado"],
    "Postura do Orador": ["Emocional", "Confiante", "Técnica"],
    "Credibilidade e Validação": ["Autoridade Própria", "Referência Externa", "Recursos Retóricos"],
    "Posicionamento": ["Favorável"]
  },
  "resumo": "…",
  "objeto_do_posicionamento": "…",
  "propostas": ["…"],
  "interrupcoes": [],
  "pendencias_revisao": ["…"]
}
```

**As quatro dimensões admitem mais de um valor**: uma fala pode ser ao mesmo tempo Emocional, Confiante e Técnica. **`objeto_do_posicionamento` antecede `Posicionamento`**: duas falas Favoráveis sobre objetos diferentes não concordam entre si. A parte final de `resumo` repete a classificação e o objeto, e não é reaproveitada.

`interrupcoes` não é consumido por nenhum prompt.

**Excerto** — saída de `13`, entrada de todos os seguintes:

```xml
<excerpt id="T-01" fala_id="f00006" ordem="6" speaker="Nome" role="cargo"
         alinhamento_tematico="Focalizado"
         postura="Emocional; Confiante; Técnica"
         credibilidade="Autoridade Própria; Referência Externa; Recursos Retóricos"
         posicionamento="Favorável"
         objeto_do_posicionamento="…" context="opcional" pendencias="opcional">
  <text>trecho literal recortado da fala</text>
  <propostas>copiadas da fala, quando houver</propostas>
</excerpt>
```

Valores múltiplos vão separados por ponto e vírgula. `13` recorta e copia: não escreve resumo, não reformula o objeto do posicionamento e não reescreve proposta. Uma fala longa pode render mais de um excerto, com o mesmo `fala_id`.

**Habilidade candidata** — entrada de `15` e `32`:

```xml
<skill code="EF09HI26" component="História" grade="9" field="..." knowledge_object="...">
  redação literal da coluna description
</skill>
```

**Teoria** — `{{THEORY}}` recebe o conteúdo do arquivo escolhido em `teorias/`, inteiro. Nenhuma montagem adicional é necessária.

## Busca

Duas etapas, dois mecanismos.

**Seleção do debate** — similaridade vetorial entre a consulta do professor e os resumos dos debates. Não usa prompt: o texto do professor é embeddado diretamente.

**Recuperação durante a geração** — busca semântica sobre as falas do debate escolhido, mais filtros de metadado. O prompt `12` escreve as consultas e os filtros.

## Autoridade da especificação

`19` produz o contrato que `20`–`25` obedecem. Onde a especificação for explícita, o gerador a segue sem reinterpretar; onde for omissa, decide pelos princípios e registra. `out_of_scope` é limite, não sugestão. Requisito impossível de cumprir com o material recebido é declarado, não substituído por um parecido.

## Referências de estrutura

A forma do material vem de três lugares desta pasta: `templates/` para a estrutura do plano de aula, `formatos-de-aula/` para a condução da aula, e `prompts/componentes/` para os princípios de redação. `TEACHER_MATERIALS` acrescenta o que o professor cadastrou e tem precedência sobre os três.

## Regras de carregamento

Ordem dos blocos no prompt: dados longos primeiro, instruções e exemplos depois, pedido do professor por último.

Nada entra inteiro quando pode entrar filtrado. A BNCC entra filtrada por `education_stage` + `grade` + `component`; o acervo de formatos entra como índice, e só o escolhido por extenso; as teorias entram como índice em `17`, e só a escolhida por extenso em `20`–`25`.

Teoria: uma, no máximo duas. Regras de prioridade 100 sempre; 80 quando couber; 60 opcional. Conflito entre regra e formato de aula resolve a favor do formato.

Verificações rodam em paralelo, uma por critério. `30` e `32` reprovam com qualquer achado grave. `31` reprova com avaliação órfã ou tempo estourado. `33` reprova com resposta induzida ou assimetria de procedimento.

## Versionamento

`VERSION` traz a versão do conjunto de prompts. A aplicação registra esse valor junto de cada material gerado, com a habilidade da BNCC, a teoria, o formato de aula e os identificadores dos excertos usados.

## Arquivos derivados

`teorias/*.md` são gerados a partir de `dados/teorias-principios.csv` e `dados/teorias-regras.csv`. Os CSVs são a fonte. Ao alterar uma regra, altere o CSV e regenere o `.md`.
