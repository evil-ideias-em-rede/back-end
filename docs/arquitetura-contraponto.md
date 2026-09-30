# Contraponto: agente LangGraph e arquitetura frontend/backend

Diagramas produzidos a partir do código do Contraponto nas pastas `back-end` e
`front-end`. Referência dos checkouts: backend `a4db659`, frontend `5d2935c`.
O escopo é o fluxo de exploração de audiências, geração e edição de materiais,
com as ferramentas, os dados consultados e a execução em sandbox.

As figuras descrevem a implementação encontrada no código. O levantamento não
executou uma conversa com um provedor de IA nem uma sessão de sandbox.

Os arquivos `.mmd` foram renderizados para conferir a sintaxe. Os SVGs
usam o layout ELK com junção de arestas para reduzir cruzamentos; os fontes
Mermaid mantêm o layout padrão para facilitar a abertura em outros editores.

## 1. Fluxo do agente no LangGraph

[Fonte Mermaid editável](agente-langgraph.mmd) · [Figura vetorial SVG](agente-langgraph.svg)

![Fluxo do agente LangGraph do Contraponto](agente-langgraph.svg)

Também está disponível a exportação direta do grafo compilado:
[Mermaid gerado pelo LangGraph](agente-langgraph-gerado.mmd) ·
[SVG do grafo gerado](agente-langgraph-gerado.svg).
O arquivo `.mmd` dessa versão contém a saída de `draw_mermaid()` sem edição.
Para obter a mesma saída, no ambiente Python do backend:

```python
from graph.main import GRAPH_BUILDER

print(GRAPH_BUILDER.get_graph().draw_mermaid())
```

O diagrama automático apresenta todos os destinos dos mapas de arestas
condicionais declarados no código. Durante a execução, as funções de roteamento
escolhem o caminho conforme o estado; a figura não é um registro de uma conversa.

### Como ler o grafo

1. A API monta `ChatGraphState` com o histórico de mensagens, o pedido atual, o
   contexto pedagógico autorizado, o nome do agente e as flags de edição.
   `RunnableConfig` transporta os identificadores da sessão, do professor e do
   workspace. O limite de recursão do workflow é 64.
2. `router_state` valida `agent_name`, atribui `selected_agent` e encaminha ao nó
   correspondente. Essa escolha vem da aplicação; o router é uma função Python
   determinística.
3. O nó especializado chama `run_agent`. Essa função compartilhada escolhe o
   prompt do papel/modo, acrescenta regras e contexto, vincula as ferramentas
   com `bind_tools` e acumula os chunks retornados pelo modelo.
4. Sem chamadas de ferramentas, o grafo termina. Com `tool_calls`,
   `route_after_agent` seleciona `brainstorm_tools`, `editor_tools` ou `tools`.
5. Os resultados entram em `messages` como `ToolMessage`. O grafo retorna ao
   mesmo `selected_agent`, que pode consultar mais ferramentas ou responder.
6. Ao terminar, a API persiste a resposta e os arquivos da sessão.

Os oito nós representam papéis especializados. Uma execução seleciona um papel;
o código não executa os oito em paralelo. A passagem do brainstorm para o papel
que produz o material é uma nova chamada da aplicação após a confirmação da
audiência. `run_agent` aparece na figura para explicar o interior dos nós, mas
não é um nó adicional registrado no `StateGraph`.

### Ferramentas anunciadas ao modelo por modo

| Grupo | Brainstorm | Geração na tela de audiências | Edição |
|---|---|---|---|
| Shell | `execute_brainstorm_planning` | `execute_planning_restricted` | `execute_bash` |
| Arquivos acessíveis ao shell | `planning.json` | `planning.json` e `HTML.html` | Diretório completo do sandbox da sessão |
| Audiências | `buscar_audiencias`, `consultar_audiencias_sql`, `consultar_audiencia_por_id` | As mesmas três ferramentas | Não são vinculadas ao modelo nesse modo |
| Referências | `consultar_bncc`, `consultar_templates`, `consultar_acervo`, `consultar_materiais_professor` | As mesmas quatro ferramentas | As mesmas quatro ferramentas |
| Web | Não é vinculada ao modelo nesse modo | `web_search` | `web_search` |

O nome Python `execute_suggested_files` corresponde à ferramenta exposta como
`execute_planning_restricted`. O executor `ToolNode("tools")` também registra
`execute_bash`; a montagem normal do modelo para geração anuncia a ferramenta
restrita. A lista de ferramentas anunciadas ao modelo e o registro de funções
do executor são conceitos distintos.

O grafo usa `graph.compile()` sem checkpointer configurado. A persistência é
implementada pela aplicação: mensagens de usuário/assistente no PostgreSQL,
cache em `InMemoryWorkflowStore` e arquivos por sessão. Os resultados de
ferramentas ficam no estado da execução; o histórico reconstruído pela API
contém as mensagens de usuário e assistente.

## 2. Arquitetura e circulação dos dados

[Fonte Mermaid editável](arquitetura-front-back.mmd) · [Figura vetorial SVG](arquitetura-front-back.svg)

![Arquitetura frontend/backend do Contraponto](arquitetura-front-back.svg)

As setas bidirecionais representam solicitação e resposta ou leitura e escrita.
As ligações tracejadas entre fontes de dados indicam caminhos de fallback.
Linhas tracejadas ligadas a notas são explicações, sem tráfego de execução.

### Trocas entre frontend e backend

Na tabela abaixo, `S` representa `/api/workflow/sessions/{session_id}`.
As requisições autenticadas levam `Authorization: Bearer <token>`. O backend
obtém a identidade do professor pelo token e confere o acesso à sessão.

| Momento | Requisição do frontend | Dados enviados | Retorno ou efeito |
|---|---|---|---|
| Abrir fluxo | `POST /api/workflow/sessions` | JSON com `agent_name`, quando escolhido | Sessão com UUID; preparação e persistência inicial do workspace |
| Retomar fluxo | `GET S` | ID na URL | Sessão, agente escolhido, fonte selecionada e histórico |
| Listar/visualizar audiências | `GET /api/audiencias` e `GET /api/audiencias/{id}` | ID na URL quando necessário | Estrutura da audiência para a interface |
| Conversar no brainstorm | `POST S/messages` | JSON: `text`, `agent_name: "brainstorm"`, `hidden`, `viewed_audience_id` opcional | JSON: `session_id`, `message`, `html_url` quando aplicável |
| Ler sugestões | `GET S/planning` | ID da sessão | Lista derivada de `planning.json` |
| Confirmar fonte | `POST S/planning/select/{planning_id}` | ID do item na URL | Grava `audiencia.json`, atualiza a seleção da sessão e devolve a audiência |
| Validar passagem | `POST S/advance` | JSON: `from_agent: "brainstorm"` | `allowed: true` ou erro de validação; a geração ocorre em outra requisição |
| Gerar material | `POST S/messages` | JSON: pedido, agente final e `hidden` quando a mensagem é interna | Resposta textual após o grafo; o arquivo produzido é `HTML.html` |
| Observar produção | `GET S/html/exists` | ID na URL | Booleano de presença de HTML com conteúdo |
| Carregar documento | `GET S/html` | ID na URL | HTML em `text/html`, lido como texto pelo cliente |
| Salvar edição manual | `POST S/files` | `multipart/form-data`, parte `file`, normalmente `HTML.html` | Grava arquivo no workspace e persiste o snapshot |
| Pedir edição ao agente | `POST S/editor/messages` | JSON: `text`, `agent_name`, `user_edited` | Resposta do agente; depois o frontend busca novamente `S/html` |
| Baixar material | `POST S/download?format=html\|pdf\|docx&filename=...&orientation=...` | Multipart com o HTML atualmente aberto no editor | Bytes do arquivo e `Content-Disposition: attachment` |
| Baixar slides | `POST S/pptx` | Multipart com o HTML atual | Arquivo PPTX |

O frontend atual usa `fetch`/HTTP para o chat. `SuggestPage` observa a existência
de HTML a cada cinco segundos enquanto há trabalho pendente. Essa presença
serve como sinal parcial; a conclusão depende da resposta da requisição.
O backend também declara uma rota WebSocket e o cliente possui uma função que
monta sua URL, mas não há conexão WebSocket nas telas atuais inspecionadas.
A figura representa o caminho HTTP efetivamente chamado por elas.

No editor, o autosave envia o HTML após 500 ms sem nova alteração. Antes de
enviar um pedido ao agente, `MaterialEditorPage` aguarda explicitamente o upload
da versão atual de `HTML.html`; em seguida envia a mensagem e, ao receber a
resposta, busca o HTML atualizado. `user_edited` sinaliza alterações manuais e
é incorporado pelo backend às instruções do turno.

`viewed_audience_id` informa qual audiência está aberta na tela, sem confirmar
sua seleção como fonte. A confirmação usa o endpoint de seleção e grava
`audiencia.json`. O conteúdo do HTML e a resposta do chat percorrem requisições
distintas. O canvas exibe o HTML em iframe e comunica seleções/edições à página
React por `postMessage`; isso é comunicação local no navegador.

### O que circula entre agente, ferramentas e fontes

| Componente | Recebe | Consulta ou executa | Devolve ao agente |
|---|---|---|---|
| Modelo do agente | Prompt, histórico, contexto autorizado e schemas das ferramentas | Provedor configurado por `LLM_PROVIDER` | Texto e/ou chamadas com nome, argumentos e identificador |
| `buscar_audiencias` | Pergunta e `k` | Embedding da pergunta na OpenAI; KNN por cosseno em `audiencias_vec`; matéria por ID | JSON com `ref_id`, distância e matéria; cada audiência aparece no máximo uma vez |
| `consultar_audiencias_sql` | Pergunta em linguagem natural | LLM gera SELECT; código valida tipo de consulta e tabelas `audiencias`/`documentos`; executa no SQLite | JSON com pergunta, SQL e linhas do resultado |
| `consultar_audiencia_por_id` | ID, seção, posição e ID de fala opcional | Corpus local; estrutura do índice como fallback | Página de até 12.000 caracteres, com informação de continuação |
| `consultar_bncc` | Etapa, ano e componente | CSV local da BNCC | Habilidades correspondentes em JSON |
| `consultar_acervo` | Arquivo permitido, posição e filtros | Guias, teorias, formatos e CSVs da aplicação | Conteúdo paginado |
| `consultar_templates` | Nenhum arquivo para catálogo, ou um nome permitido | Templates autorizados do professor ou padrões conforme o papel | Catálogo ou HTML do template |
| `consultar_materiais_professor` | ID do material e paginação | Anexos autorizados do professor no banco | Catálogo ou texto de HTML, PDF ou DOCX |
| `web_search` | Pergunta | Tavily, a partir do backend | Texto, títulos e URLs dos resultados |
| Ferramenta de shell | Comando Bash | MicroVM com o volume permitido para o modo | JSON com `stdout`, `stderr`, `returncode`, `sucesso` |

A busca usada por `buscar_audiencias` compara embeddings da **matéria completa**,
com uma linha por audiência. A leitura das falas pode ocorrer depois por ID ou
SQL. Busca híbrida, FTS e reranking possuem utilitários no repositório, mas não
compõem obrigatoriamente o caminho dessa ferramenta no código inspecionado.

O carregador de anotações usa o CSV compactado original e seleciona as linhas
`categoria = anotado`; as linhas `auditoria` não viram audiências adicionais no
agente. O CSV filtrado criado para a análise do artigo é um artefato separado.

O contexto pedagógico injetado a cada turno autenticado contém metadados de
escolas, turmas, templates e materiais autorizados. Conteúdos completos de
templates e anexos são consultados pelas ferramentas, conforme a necessidade.

### Sandbox, arquivos e persistência

- O diretório durável da sessão fica em `workdirs/<id>/sandbox`. O backend
  calcula esse identificador; o modelo não escolhe o caminho do host.
- `execute_bash` monta o diretório completo da sessão em `/workspace` na
  microVM. As ferramentas restritas criam um diretório temporário, copiam
  somente os nomes permitidos e sincronizam esses arquivos de volta.
- Cada chamada cria uma microVM descartável, com perfil restrito, rede
  desabilitada, 1 CPU e 1.024 MiB de memória. O comando tem timeout de 300 s;
  a duração máxima configurada para a microVM é 330 s.
- O descarte da microVM não apaga o workspace da sessão. O serviço
  `workflow_files` persiste caminhos relativos e bytes no PostgreSQL e os
  restaura quando a sessão é retomada. A aplicação também mantém o diretório
  local de trabalho.
- Busca na web, embeddings, geração de texto e consultas de referência são
  executados por ferramentas Python no backend, fora da microVM sem rede.
- Os endpoints de exportação chamam conversores do backend. A exportação
  HTML/PDF/DOCX usa o upload atual do editor sem depender de uma nova geração
  pelo agente. A exportação PPTX também utiliza o workspace da sessão.

Na instalação Docker, o Nginx entrega o build do frontend e encaminha `/api`
para o FastAPI. No desenvolvimento, o cliente usa o endereço configurado por
`VITE_API_URL`. O PostgreSQL guarda dados da aplicação; o SQLite guarda o índice
de consulta do corpus. São armazenamentos com funções diferentes.

## Referências no código

| Parte | Arquivos principais |
|---|---|
| Grafo e roteamento | [graph/main.py](../graph/main.py) |
| Execução comum dos agentes | [graph/agent/base.py](../graph/agent/base.py) |
| Mensagens, estado e sessão | [workflow_router.py](../routers/workflow_router.py), [workflow_messages_router.py](../routers/workflow_messages_router.py) |
| Cliente HTTP | [front-end/src/api/client.ts](../../front-end/src/api/client.ts) |
| Exploração e geração | [SuggestPage.tsx](../../front-end/src/components/editor/SuggestPage.tsx) |
| Edição e sincronização | [MaterialEditorPage.tsx](../../front-end/src/components/editor/MaterialEditorPage.tsx), [HtmlCanvas.tsx](../../front-end/src/components/editor/HtmlCanvas.tsx) |
| Consulta ao corpus | [tool_buscar_audiencias.py](../graph/tools/retrieval/tool_buscar_audiencias.py), [tool_consultar_audiencias_sql.py](../graph/tools/retrieval/tool_consultar_audiencias_sql.py), [audiencias.py](../graph/tools/retrieval/audiencias.py) |
| Provedor e contexto | [llm.py](../services/llm.py), [teacher_context.py](../services/teacher_context.py) |
| Preparação e execução isolada | [workdir.py](../graph/tools/sandbox/workdir.py), [restricted_file.py](../graph/tools/sandbox/restricted_file.py), [microsandbox_runtime.py](../graph/tools/sandbox/microsandbox_runtime.py) |
| Arquivos e snapshots | [sandbox_router.py](../routers/sandbox_router.py), [workflow_files.py](../services/workflow_files.py) |
| Exportação | [html_pdf_router.py](../routers/html_pdf_router.py) |
| Proxy da instalação | [front-end/nginx.conf](../../front-end/nginx.conf) |
