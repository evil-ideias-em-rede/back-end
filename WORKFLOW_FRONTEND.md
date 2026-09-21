# Fluxo do frontend e endpoints do workflow

Este documento descreve o fluxo da tela do Ateliê de Agentes e o contrato entre o frontend e o backend.

## Configuração

Durante o protótipo, o usuário utilizado pelo workflow é fixo:

```text
user_id = 10
```

O frontend é servido pelo próprio backend:

```text
http://localhost:8002
```

Todas as URLs abaixo são relativas à origem atual. O banco guarda as sessões, mensagens e arquivos do sandbox.

## Agentes disponíveis

Os valores enviados pela API são:

| Valor | Uso |
|---|---|
| `debate` | Agente final de debate |
| `generic` | Agente final de atividade genérica |
| `lesson_plan` | Agente final de plano de aula |
| `political_leteracy` | Agente final de letramento político |
| `writing_workshop` | Agente final de oficina de redação |
| `slides` | Agente final de apresentações/slides |
| `brainstorm` | Etapa inicial de brainstorming; não é escolhido como agente final |

O agente final é escolhido uma única vez ao iniciar a sessão. Depois, o frontend deve enviar `brainstorm` apenas na primeira etapa e o agente escolhido nas mensagens da etapa final.

## Fluxo principal da tela

```text
abrir tela
  ├─ listar sessões anteriores
  ├─ escolher uma sessão e retomá-la
  └─ ou escolher um agente e criar uma nova sessão
       ↓
  brainstorm
       ↓ (advance permitido)
  agente final escolhido no início
```

## 1. Listar sessões anteriores

Ao abrir a tela inicial, o frontend deve chamar:

```http
GET /api/workflow/sessions?user_id=10
```

Resposta:

```json
[
  {
    "id": "00b27caa-c72e-4ae7-b20e-f93307bb4ece",
    "created_at": "2026-09-19T02:05:56.272082+00:00",
    "selected_agent": "debate",
    "message_count": 16,
    "last_message_at": "2026-09-19T02:09:00.381147+00:00",
    "last_message": "Oi novamente! Como posso ajudar hoje?"
  }
]
```

`message_count` é a quantidade total de registros na tabela `workflow_messages` para essa sessão. Uma pergunta do professor e uma resposta do agente contam como **2 mensagens**. Portanto, `16` normalmente representa 8 pares de pergunta/resposta quando a conversa está equilibrada, mas o número pode variar porque também inclui mensagens ocultas de controle (`hidden: true`).

O frontend deve mostrar cada item como um chat selecionável. Se a lista estiver vazia, deve mostrar que ainda não há sessões salvas.

## 2. Criar uma nova sessão

Quando o usuário escolher o agente final e clicar em “Começar brainstorm”:

```http
POST /api/workflow/sessions
Content-Type: application/json
```

Body:

```json
{
  "user_id": 10,
  "agent_name": "debate"
}
```

Resposta:

```json
{
  "id": "00b27caa-c72e-4ae7-b20e-f93307bb4ece",
  "created_at": "2026-09-19T02:05:56.272082+00:00",
  "selected_agent": "debate",
  "messages": []
}
```

O frontend deve guardar `id` em `state.sessionId` e `selected_agent` em `state.activeAgent`. Não deve criar a sessão automaticamente ao carregar a página.

## 3. Retomar uma sessão

Ao clicar em um chat anterior:

```http
GET /api/workflow/sessions/{session_id}
```

Resposta:

```json
{
  "id": "00b27caa-c72e-4ae7-b20e-f93307bb4ece",
  "created_at": "2026-09-19T02:05:56.272082+00:00",
  "selected_agent": "debate",
  "messages": [
    {
      "id": "message-id",
      "role": "user",
      "content": "Quero trabalhar água com minha turma.",
      "agent_name": "brainstorm",
      "hidden": false,
      "created_at": "2026-09-19T02:06:00+00:00"
    },
    {
      "id": "message-id-2",
      "role": "assistant",
      "content": "Podemos explorar estas propostas...",
      "agent_name": "brainstorm",
      "hidden": false,
      "created_at": "2026-09-19T02:06:10+00:00"
    }
  ]
}
```

Ao retomar:

1. Carregar `messages` no histórico.
2. Usar `selected_agent` como agente final.
3. Se ainda não houver mensagens do agente final, abrir a etapa do brainstorm.
4. Se já houver mensagens do agente final, abrir a etapa final.
5. Buscar o artefato da etapa atual (`planning.json` ou `HTML.html`).
6. Abrir o WebSocket da sessão antes de enviar uma nova mensagem.

## 4. Conversar com os agentes

O canal principal é WebSocket:

```text
WS /api/workflow/sessions/{session_id}/ws
```

### Enviar mensagem

```json
{
  "type": "message",
  "text": "Quero uma atividade sobre água para o 7º ano.",
  "agent_name": "brainstorm",
  "hidden": false
}
```

`hidden: false` é uma mensagem visível para o professor. Mensagens internas de transição podem usar `hidden: true`; elas continuam sendo salvas, mas o frontend não precisa exibi-las no histórico normal.

### Eventos recebidos

Durante a resposta:

```json
{
  "type": "token",
  "content": "Vamos considerar..."
}
```

O frontend deve acrescentar cada `content` à mensagem em streaming.

Ao finalizar:

```json
{
  "type": "done",
  "session_id": "00b27caa-c72e-4ae7-b20e-f93307bb4ece",
  "message": {
    "id": "message-id-3",
    "role": "assistant",
    "content": "Resposta completa do agente.",
    "agent_name": "brainstorm",
    "hidden": false,
    "created_at": "2026-09-19T02:06:20+00:00"
  },
  "artifact_name": "planning.json",
  "artifact_url": "/api/workflow/sessions/00b27caa-c72e-4ae7-b20e-f93307bb4ece/planning.json"
}
```

Se o evento `done` trouxer `artifact_url`, o frontend deve buscar o arquivo e atualizar a pré-visualização.

Erro:

```json
{
  "type": "error",
  "message": "Descrição do erro"
}
```

## 5. Artefato do brainstorm

O brainstorm normalmente produz `planning.json`.

```http
GET /api/workflow/sessions/{session_id}/planning.json
```

O frontend deve exibir as ideias e permitir que o professor selecione uma delas.

### Selecionar uma ideia/audiência

```http
POST /api/workflow/sessions/{session_id}/planning/select/{planning_id}
```

Resposta resumida:

```json
{
  "session_id": "00b27caa-c72e-4ae7-b20e-f93307bb4ece",
  "selected_id": "aud-001",
  "selected_index": 0,
  "changed": true,
  "audiencia": {
    "id": "aud-001",
    "titulo": "Audiência pública"
  },
  "planning": []
}
```

Depois dessa resposta, o frontend deve atualizar a lista, mostrar a audiência selecionada e aguardar a resposta do brainstorm antes de liberar o avanço.

> No protótipo atual, o frontend usa a audiência mock `aud-001`. Quando houver audiência real, o valor enviado no path deve ser substituído pelo id correspondente à opção escolhida.

## 6. Avançar para o agente final

O frontend só deve enviar este evento depois que o brainstorm tiver respondido e houver planejamento/audiência válidos:

```json
{
  "type": "advance",
  "from_agent": "brainstorm"
}
```

Se for permitido:

```json
{
  "type": "done",
  "session_id": "00b27caa-c72e-4ae7-b20e-f93307bb4ece",
  "allowed": true
}
```

O frontend deve mudar para a etapa 3 e enviar as próximas mensagens usando exatamente o `selected_agent` salvo na sessão.

Se não for permitido:

```json
{
  "type": "error",
  "status_code": 400,
  "detail": ["O plano de audiência está vazio..."],
  "message": "Não é possível escolher o agente final: ..."
}
```

Nesse caso, permanecer no brainstorm e mostrar a mensagem ao professor.

## 7. Arquivos anexados

Para anexar um arquivo ao sandbox da sessão:

```http
POST /api/workflow/sessions/{session_id}/files
Content-Type: multipart/form-data
```

Campo do formulário: `file`.

Resposta:

```json
{
  "filename": "referencia.pdf",
  "sandbox_path": "sandbox/referencia.pdf",
  "size": 12345
}
```

O frontend deve enviar o arquivo antes da mensagem e informar o caminho retornado ao agente, quando necessário.

## 8. HTML, arquivos e PDF

HTML gerado pelo agente final:

```http
GET /api/workflow/sessions/{session_id}/html
```

Qualquer arquivo persistido do sandbox:

```http
GET /api/workflow/sessions/{session_id}/{filename}
```

O frontend deve usar o HTML retornado no iframe e atualizar a URL com um parâmetro de cache, por exemplo `?v=${Date.now()}`.

Gerar PDF a partir do HTML:

```http
POST /api/workflow/sessions/{session_id}/pdf
Content-Type: multipart/form-data
```

Campo do formulário: `file`, contendo o HTML. A resposta é binária com `Content-Type: application/pdf`; o frontend deve criar um `Blob` e iniciar o download.

## Persistência do sandbox

O backend mantém duas camadas:

1. O workdir local da sessão, em `workdirs/{hash}/sandbox`.
2. A tabela `workflow_files`, que guarda caminho e conteúdo dos arquivos associados ao `session_id`.

Mensagens ficam em `workflow_messages`, sempre com:

```text
agent_name, role, content, hidden, created_at
```

Arquivos criados, alterados, anexados ou removidos são sincronizados ao finalizar a operação. Ao retomar uma sessão, o backend restaura o sandbox persistido e remove arquivos locais que não existem mais no banco.

## Endpoints auxiliares existentes

Esses endpoints pertencem a fluxos mais antigos ou genéricos:

| Método | Endpoint | Uso |
|---|---|---|
| `GET` | `/health` | Verificar se a API está viva |
| `POST` | `/auth/google` | Login Google do fluxo autenticado |
| `GET` | `/chats` | Listar chats autenticados tradicionais |
| `POST` | `/chats` | Criar chat tradicional |
| `GET` | `/chats/{chat_id}/messages` | Listar mensagens tradicionais |
| `POST` | `/chats/{chat_id}/messages` | Enviar mensagem no chat tradicional |
| `DELETE` | `/chats/{chat_id}` | Excluir chat tradicional |
| `PATCH` | `/chats/{chat_id}/title` | Renomear chat tradicional |

Para a tela do Ateliê de Agentes, usar prioritariamente os endpoints `/api/workflow/...` documentados acima.
