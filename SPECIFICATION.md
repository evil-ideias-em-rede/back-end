# Contraponto — arquitetura e funcionamento dos agentes

Este documento descreve o fluxo implementado no código: entrada de mensagens,
seleção de agentes, consultas de fontes, geração e edição de documentos,
sandbox e persistência. Para instalação e operação com Docker, consulte o
[README.md](README.md).

A descrição corresponde ao código do repositório. Um container construído antes
das alterações pode executar uma versão diferente até ser reconstruído/recriado.
As orientações pedagógicas são instruções aos modelos; não são garantia de que
toda resposta terá qualidade ou de que toda consulta será realizada corretamente.

## 1. Visão geral

O backend é uma API FastAPI. O frontend envia o identificador da sessão, o texto
e o agente solicitado. O backend valida o acesso, prepara o contexto e executa
um grafo LangGraph. O agente usa a LLM configurada e pode solicitar ferramentas.

Não há um supervisor LLM distribuindo livremente tarefas entre especialistas.
O roteamento é determinado pelo agente informado e validado pela aplicação.
Durante uma execução, resultados de ferramentas voltam ao mesmo agente.

```text
Professor → frontend → API FastAPI
                         │
                         ├─ autorização e sessão
                         ├─ histórico e contexto do professor
                         └─ preparação do sandbox
                                  │
                                  ▼
                         router do LangGraph
                                  │
                                  ▼
                           agente selecionado
                            │             ▲
                            │ ferramenta  │ resultado
                            ▼             │
                         ToolNode ────────┘
                            │
                   quando o agente conclui
                            ▼
                  resposta + arquivos da sessão
                            │
                    persistência no banco
                            ▼
               frontend: chat / sugestões / HTML
```

## 2. Entrada no backend

[main.py](main.py) registra as rotas da aplicação. O fluxo de mensagens passa
por [workflow_messages_router.py](routers/workflow_messages_router.py) e pela
lógica compartilhada de [workflow_router.py](routers/workflow_router.py).

### Sessão

`POST /api/workflow/sessions` cria uma sessão com UUID, agente final quando
informado, proprietário autenticado e referência ao diretório de trabalho.
O backend prepara o sandbox e persiste seus arquivos iniciais.

Uma sessão reúne histórico, audiência selecionada, etapa e documento. O
`session_id` não é o ID da audiência nem o ID do professor.

### Mensagens das audiências sugeridas

```http
POST /api/workflow/sessions/{session_id}/messages
```

```json
{
  "text": "Quero trabalhar desmatamento com o 6º ano",
  "agent_name": "brainstorm",
  "hidden": false
}
```

Esse endpoint usa `editor_mode=false`. Também recebe pedidos de geração dos
agentes especializados, como `lesson_plan`, depois da escolha da fonte.
`editor_geral` não é aceito nesse endpoint.

### Mensagens de edição

```http
POST /api/workflow/sessions/{session_id}/editor/messages
```

```json
{
  "text": "Simplifique a segunda atividade sem alterar o restante",
  "agent_name": "lesson_plan",
  "hidden": false,
  "user_edited": true
}
```

Esse endpoint usa `editor_mode=true` e não aceita `brainstorm`.
`user_edited` informa que houve edição manual e reforça a preservação do
documento. Ele não transporta o HTML editado; o conteúdo precisa ser salvo pelo
fluxo de arquivos da interface. `hidden` marca mensagens internas do fluxo,
sem torná-las instruções de sistema nem dispensar a autorização.

### Processamento compartilhado

Antes de invocar o grafo, o backend:

1. Verifica o acesso à sessão e recupera seu estado persistido quando necessário.
2. Valida se o agente solicitado é compatível com o agente final da sessão.
3. Salva a mensagem do usuário no banco e na memória temporária da aplicação.
4. Carrega o contexto privado autorizado do professor.
5. Monta histórico, mensagem atual, agente e flags de modo.
6. Prepara o sandbox e os templates autorizados.
7. Executa o grafo; ao concluir, salva a resposta. Os arquivos são persistidos
   também no bloco de finalização, inclusive quando há falha na geração.

Uma falha não deve virar uma falsa resposta de sucesso: a mensagem do usuário
já foi salva, e o erro é devolvido à interface.

### HTTP e streaming

As funções `sendWorkflowMessage` e `sendEditorMessage` do frontend usam POST
HTTP e aguardam uma resposta JSON com `session_id`, `message` e, quando houver,
`html_url`.

Há também `WS /api/workflow/sessions/{session_id}/ws`, com caminho de execução
em streaming e eventos como `token` e `done`. A existência dessa rota não
significa que as telas atuais usem WebSocket. Também não se deve confundir o
streaming interno da LLM com entrega incremental ao navegador.

## 3. Grafo e estado dos agentes

[graph/main.py](graph/main.py) registra os agentes e compila o grafo:

```text
START → router → agente
                  ├─ sem tool_calls → END
                  └─ com tool_calls → ToolNode do agente/modo → mesmo agente
```

`router_state` valida `agent_name` e escolhe o node; não chama uma LLM para essa
decisão. O brainstorm usa `brainstorm_tools`, sem ferramentas que escrevam HTML.
Os especialistas usam `tools` ou `editor_tools`, conforme `editor_mode`.
O brainstorm nunca gera documento, mesmo com solicitação explícita: sua escrita
fica restrita ao planejamento e a criação deve seguir pelo agente final.
O backend
configura atualmente um limite de 64 passos de grafo por execução; isso não
significa 64 agentes nem 64 consultas obrigatórias.

O estado inclui:

| Campo | Finalidade |
|---|---|
| `messages` | Histórico e mensagens produzidas durante a execução, incluindo resultados de ferramentas |
| `chat_id` | Identificador interno derivado da sessão |
| `user_id` | Identificador usado no workspace; no workflow há um valor legado |
| `context` | Contexto autorizado do professor |
| `agent_name` / `selected_agent` | Agente solicitado e node selecionado |
| `editor_mode` | Distingue geração/audiências de edição |
| `user_edited` | Sinaliza alterações manuais no documento |

A identidade privada é transmitida pelo servidor em `teacher_user_id`, na
configuração das ferramentas. O `user_id=10` legado do workflow **não é** a
identidade do professor e não autoriza consultar seus templates ou materiais.

## 4. Agentes de audiências sugeridas e seus editores

Existem oito nodes registrados, não dois agentes independentes para cada
produto. Os seis especialistas de produto escolhem um prompt de geração ou
edição conforme `editor_mode`. O brainstorm é a entrada exploratória; o editor
geral é exclusivo da edição.

| Nome recebido na API | Node | Audiências sugeridas / geração | Edição |
|---|---|---|---|
| `brainstorm` | `brainstorm_node` | Entende a demanda, busca fontes, organiza sugestões em `planning.json` e conversa sobre recortes | Não é aceito no endpoint de edição; uma atividade livre pode seguir para `generic` |
| `lesson_plan` | `lesson_plan_node` | Produz plano com objetivos, etapas, tempos, recursos, BNCC e avaliação | Ajusta o plano existente, preservando alterações manuais e partes fora do pedido |
| `debate` | `debate_outline_node` | Produz questão, papéis, falas-fonte, regras, mediação e fechamento do debate | Altera roteiro, perguntas, tempos ou critérios sem inventar posições da fonte |
| `writing_workshop` | `writing_workshop_node` | Organiza gênero, finalidade, coletânea, escrita, revisão e reescrita | Ajusta comandos, coletânea e rubrica, respeitando o escopo solicitado |
| `political_leteracy` | `political_leteracy_node` | Cria atividades de autoria, contexto, evidência, persuasão e análise de mídia/discurso | Revisa atividades e fichas mantendo atribuição e fidelidade às fontes |
| `slides` | `slides_node` | Produz apresentação com páginas em paisagem, ideias legíveis e interação | Ajusta os slides solicitados preservando identidade e demais páginas |
| `generic` | `generic_activity_node` | Cria atividades personalizadas e material consolidado a partir de exploração livre | Edita o artefato existente sem impor um formato de plano de aula |
| `editor_geral` | `general_editor_node` | Não participa desse modo | Edita templates/documentos existentes conforme o pedido |

As grafias `brain_stom_node.py` e `political_leteracy` são as usadas atualmente
no código. Não substitua seus nomes em integrações sem atualizar os mapeamentos.

### Onde estão os prompts de cada modo

Os diretórios são
[audiencias_sugeridas](graph/agent/prompts/audiencias_sugeridas/) e
[editor](graph/agent/prompts/editor/).

| Agente | Arquivo em `audiencias_sugeridas/` | Arquivo em `editor/` |
|---|---|---|
| Brainstorm | `brain_storm_prompt.py` | Não possui editor próprio |
| Plano de aula | `lesson_plan_prompt.py` | `lesson_plan_prompt.py` |
| Debate | `debate_outline_prompt.py` | `debate_outline_prompt.py` |
| Oficina de redação | `writing_workshop_prompt.py` | `writing_workshop_prompt.py` |
| Letramento midiático/político | `political_leteracy_prompt.py` | `political_leteracy_prompt.py` |
| Slides | `slides_prompt.py` | `slides_prompt.py` |
| Atividade personalizada | `generic_activity_prompt.py` | `generic_activity_prompt.py` |
| Editor geral | Não possui geração por audiência | `general_editor_prompt.py` |

### Da sugestão à geração

1. A interface identifica o tipo de material e cria/retoma a sessão.
2. A conversa exploratória normalmente usa `brainstorm`.
3. O agente consulta audiências e escreve sugestões em `planning.json`.
4. Ao selecionar uma audiência, a interface chama
   `POST /sessions/{session_id}/planning/select/{planning_id}` sob o prefixo
   `/api/workflow`. O backend registra a escolha e salva `audiencia.json`.
5. Selecionar um card não é, por si só, autorizar a criação do material.
6. Ao clicar em **Usar essa audiência como fonte**, o fluxo verifica condições
   de avanço e envia o pedido de geração ao agente final. `/advance` valida o
   planejamento e pode pedir complementação ao brainstorm; ele não representa
   uma conversa autônoma entre todos os especialistas.
7. O especialista pede os dados indispensáveis que faltarem ou produz `HTML.html`.
8. A interface verifica a disponibilidade do HTML após a resposta de geração
   antes de seguir para a edição.

O agente final vem de `selected_agent` ou do mapeamento do tipo de material no
frontend. Para uma criação livre sem tipo especializado, existe o fallback
`generic`. A passagem entre agentes é coordenada pelo aplicativo.

## 5. Composição dos prompts e configuração do modelo

[base.py](graph/agent/base.py) concentra `run_agent`, compartilhado pelos nodes.
Ele compõe o prompt específico com regras comuns e apresenta à LLM as
ferramentas disponíveis, o contexto autorizado e o histórico.

| Arquivo | Responsabilidade |
|---|---|
| [loader.py](graph/agent/prompts/loader.py) | Lê os Markdown de `library/`, resolve componentes/variáveis e adapta a biblioteca ao chat |
| [material_rules.py](graph/agent/prompts/material_rules.py) | Critérios específicos de cada produto |
| [audiencias_sugeridas/rules.py](graph/agent/prompts/audiencias_sugeridas/rules.py) | Planejamento, escolha de fonte e geração na tela de sugestões |
| [editor/rules.py](graph/agent/prompts/editor/rules.py) | Preservação do documento e fluxo de edição |
| [delivery_rules.py](graph/agent/prompts/delivery_rules.py) | Contrato de páginas e concisão no chat |
| [template_rules.py](graph/agent/prompts/template_rules.py) | Obrigatoriedade e prioridade dos templates |
| [pedagogical_rules.py](graph/agent/prompts/pedagogical_rules.py) | Consulta seletiva de formatos, teorias, anexos e BNCC |

`render()` lê `graph/agent/prompts/library/<prompt_id>.md`, não o acervo do
sandbox. `render_for_agent()` remove o contrato de saída XML da biblioteca para
que a entrega no aplicativo siga as regras de chat e arquivo HTML.

Arquivos numerados da biblioteca não representam automaticamente nodes ativos.
Por exemplo, ter um prompt de verificação ou seleção de teoria não implica
que exista outro agente executando essa etapa separadamente. O grafo ativo é
o registrado em `graph/main.py`; o pipeline histórico em `contratos.md` não
deve ser confundido com uma implementação completa.

[services/llm.py](services/llm.py) centraliza a escolha de provedor e modelo.
`LLM_PROVIDER` seleciona `openai` ou `deepinfra`; os nomes dos modelos vêm de
`OPENAI_MODEL_NAME` e `DEEPINFRA_MODEL`. As credenciais ficam no ambiente, não
nos prompts. Os nodes compartilham essa configuração; a especialização não
exige um modelo treinado ou uma chave diferente para cada agente.

## 6. Ferramentas e fontes

A LLM solicita uma ferramenta por nome e argumentos. O backend executa a
função correspondente, e o resultado entra na conversa da execução como
mensagem de ferramenta. O modelo pode continuar consultando ou concluir.

| Ferramenta | O que oferece | Disponibilidade no fluxo |
|---|---|---|
| `buscar_audiencias` | Busca semântica de matérias, com identificadores para aprofundar a leitura | Audiências sugeridas |
| `consultar_audiencia_por_id` | Conteúdo estruturado da audiência, participantes e falas | Audiências sugeridas |
| `consultar_audiencias_sql` | Consulta do índice para recuperar informações e trechos | Audiências sugeridas |
| `consultar_bncc` | Habilidades filtradas por etapa, ano e componente | Ambos os modos |
| `consultar_acervo` | Guias, formatos, teorias e CSVs públicos por caminho permitido | Ambos os modos |
| `consultar_templates` | Catálogo autorizado e HTML do template escolhido | Ambos os modos |
| `consultar_materiais_professor` | Catálogo e texto dos anexos didáticos do proprietário da sessão | Ambos os modos |
| `execute_brainstorm_planning` | Shell com apenas `planning.json`; não recebe nem sincroniza o HTML da sessão | Brainstorm |
| `execute_planning_restricted` | Shell com apenas `planning.json` e `HTML.html` | Especialistas de geração na tela de audiências |
| `execute_bash` | Shell sobre os arquivos do sandbox da sessão | Edição |
| `web_search` | Busca externa, dependente de configuração Tavily | Especialistas nos dois modos; não faz parte da lista explícita do brainstorm |

A tabela descreve as ferramentas apresentadas aos agentes no fluxo suportado.
O registro de um ToolNode não é, isoladamente, a política de segurança:
autorização, limites de leitura e isolamento precisam ser aplicados pelas
ferramentas e endpoints. Dados retornados pelas fontes não são instruções de
sistema nem autorização para executar comandos arbitrários.

### Acervo pedagógico: leitura seletiva

A referência principal é
[guia_consulta.md](graph/tools/sandbox/shared/geral/guia_consulta.md). Na criação
ou reformulação pedagógica, os prompts orientam o agente a:

1. Recuperar objetivo, turma, duração, recursos e fontes confirmadas.
2. Ler os índices de [formatos](graph/tools/sandbox/shared/geral/formatos-de-aula/_indice.md)
   e [teorias](graph/tools/sandbox/shared/geral/teorias/_indice.md).
3. Escolher a estratégia pertinente e uma teoria, no máximo duas justificadas,
   abrindo apenas as referências necessárias.
4. Consultar o catálogo de templates e ler a base escolhida.
5. Ler os anexos de apoio relevantes e as falas reais da audiência.
6. Verificar habilidades BNCC e alinhar objetivo, atividade e avaliação.

Os índices cobrem 61 referências de estratégias/técnicas e cinco teorias. O
[guia dos dados](graph/tools/sandbox/shared/geral/dados/README.md) explica colunas,
filtros, prioridades e relações entre os CSVs. A ferramenta pública pagina as
respostas; não é necessário carregar tudo a cada mensagem. Correções pontuais
de texto ou cor não exigem refazer esse percurso.

As referências consultadas por `consultar_acervo` vêm da versão canônica da
aplicação. A ferramenta não expõe caminhos arbitrários nem os templates padrão
como alternativa para contornar um catálogo pessoal.

### Contexto, templates e materiais do professor

[teacher_context.py](services/teacher_context.py) fornece metadados autorizados
de escolas, turmas, disciplinas, quantidade de alunos e vínculos com templates
e materiais. Metadados não equivalem a ler o conteúdo dos anexos.

[template_library.py](services/template_library.py) resolve a biblioteca:

- Slides (`slides` / `slides_node`): `slide-template.html` é sempre a base
  obrigatória, mesmo com uploads. Pessoais continuam disponíveis como apoio;
  os padrões de plano não são disponibilizados ao agente de slides.
- Demais agentes, com uploads: somente os templates pessoais são disponibilizados.
- Demais agentes, sem uploads: padrões de `shared/geral/templates`, sem a base de slides.
- Template pessoal vazio não autoriza fallback silencioso para padrões.
- O agente trabalha sobre uma cópia; não deve alterar o original cadastrado.
- Edição pontual preserva a base do documento existente.

[teacher_materials.py](services/teacher_materials.py) lê materiais didáticos
armazenados: PDF por página e HTML/DOCX por trechos de texto. Não baixa URLs
externas nem interpreta imagens. PDFs digitalizados podem precisar de OCR ou
transcrição. A leitura é limitada e não deve ser apresentada como integral se
o conteúdo foi paginado ou não pôde ser extraído.

## 7. Sandbox e arquivos produzidos

[workdir.py](graph/tools/sandbox/workdir.py) deriva um identificador opaco a
partir de usuário/chat e prepara:

```text
workdirs/<hash>/sandbox/
├── planning.json           # sugestões, quando presentes
├── audiencia.json          # fonte selecionada, quando presente
├── HTML.html               # documento atual
├── templates/              # cópias autorizadas
├── formatos-de-aula/
├── teorias/
├── dados/
└── guias e utilitários
```

Nem todos esses arquivos são visíveis em todas as ferramentas. Na tela de
audiências sugeridas, o shell do brainstorm recebe somente `planning.json`.
O shell dos especialistas de geração recebe `planning.json` e `HTML.html`.
Mesmo se um comando do brainstorm criar HTML na área temporária, esse arquivo
não é sincronizado para a sessão. O backend pode manter outros arquivos sem
montá-los nesse shell; consultas de leitura oferecem o acesso necessário.

Os comandos de shell executam em microVM descartável via Microsandbox/KVM,
não diretamente no host. A disponibilidade física de arquivos no sandbox não
significa que a LLM já leu seu conteúdo. Consultas de banco e acervo são funções
do backend; nem toda ferramenta passa pela microVM.

| Artefato | Origem e uso |
|---|---|
| `planning.json` | O brainstorm organiza uma lista de sugestões; a interface consulta a lista para apresentar cards |
| `audiencia.json` | O backend salva a audiência escolhida; serve de fonte para o editor |
| `HTML.html` | O agente gera/edita o documento; a interface o carrega separadamente do texto do chat |
| Templates e guias | Referências para produção, não a resposta final ao professor |

### Contrato do documento

- Salvar HTML completo, não apenas um fragmento nem Markdown cercado por crases.
- Cada página é uma `section` com `data-ied-page`, diretamente no `body`.
- Planos e demais documentos usam A4 retrato; slides usam A4 paisagem.
- Distribuir excesso de conteúdo em páginas, sem scroll dentro da folha nem
  corte de texto para fazê-lo caber.
- Preservar IDs, edições manuais e partes fora do pedido na edição pontual.
- No editor, usar os guias/utilitários de validação quando houver alterações;
  gerar um PDF/PNG não equivale a uma inspeção visual pela LLM.

O endpoint `GET /api/workflow/sessions/{session_id}/html/exists` verifica a
presença de conteúdo não vazio no arquivo. Ele não certifica qualidade,
correção pedagógica ou ausência de problemas de layout. A interface deve
considerar a conclusão da geração, não apenas a existência inicial do arquivo.

## 8. Persistência e retomada

O PostgreSQL armazena cadastro, sessões, mensagens, vínculos e snapshots de
arquivos. [workflow_files.py](services/workflow_files.py) persiste e restaura
os arquivos do sandbox associados à sessão. Existe também memória temporária
do processo para o estado da conversa.

O grafo atual é compilado sem um checkpointer próprio configurado. A retomada
entre requisições depende da persistência implementada pela aplicação: o
backend reconstrói o contexto a partir do histórico e dos arquivos. O histórico
de usuário/assistente não deve ser confundido com um registro persistente
completo de todas as chamadas internas de ferramentas.

Os dados de busca de audiências usam o corpus público/anotado e índices de
recuperação, incluindo SQLite. Eles têm finalidade diferente do PostgreSQL
de contas, turmas e conversas.

Nada disso treina o modelo em tempo real. A memória é fornecida como contexto
a cada execução; arquivos e mensagens persistidos permitem continuar o trabalho.

## 9. Exemplo completo: plano de aula

1. O professor escolhe Plano de Aula e começa uma sessão para `lesson_plan`.
2. Escreve o tema; a conversa inicial usa o brainstorm para buscar audiências.
3. O brainstorm consulta fontes e salva sugestões em `planning.json`.
4. A escolha de uma audiência faz o backend salvar a fonte em `audiencia.json`.
5. O professor solicita usar a fonte; o frontend chama `lesson_plan` no endpoint
   de mensagens, ainda com `editor_mode=false`.
6. O especialista usa histórico/contexto, lê referências pertinentes, template,
   anexos e BNCC. Se faltar informação indispensável, pergunta; caso contrário,
   gera e confere `HTML.html`.
7. O backend salva a resposta e os arquivos; o frontend carrega o documento.
8. Um pedido posterior de alteração usa `/editor/messages`, com o mesmo
   `lesson_plan`, agora com o prompt de edição e as ferramentas desse modo.

## 10. Verificação e limites

Os testes relevantes estão em `tests/`, incluindo:

- `test_prompt_contracts.py`: composição dos prompts e referências existentes.
- `test_agent_delivery.py`: regras comuns apresentadas ao agente.
- `test_template_library.py` e `test_template_graph.py`: autorização, prioridade
  de templates e integração com os ToolNodes.
- `test_pedagogical_access.py`: leitura, filtros, paginação e isolamento de anexos.
- `test_pedagogical_graph.py`: disponibilidade/execução das consultas nos agentes
  e modos suportados, com LLM simulada.
- `test_html_pagination.py`: contrato de páginas e exportação.

Com as dependências de desenvolvimento instaladas:

```bash
python -B -m unittest discover -s tests -v
```

Alguns testes dependem do ambiente Docker/Microsandbox ou de navegador e podem
ser pulados fora desse ambiente. Testes com modelo simulado verificam a ligação
entre componentes, não a qualidade pedagógica de uma geração real, a validade
das credenciais ou a disponibilidade do provedor.

Não publique `.env`, tokens, anexos privados ou snapshots de sessões para
diagnosticar falhas. Atualizações de código/modelo em Docker devem seguir o
README; editar arquivos no host não garante que a imagem em execução os utilize.
