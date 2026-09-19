# API para integração com o frontend

O frontend pode continuar usando os mocks por enquanto. Quando a integração for
ativada, ele deverá guardar o `access_token` retornado pelo login e enviá-lo em
todas as chamadas protegidas:

```http
Authorization: Bearer <access_token>
```

## Autenticação

### Cadastrar professor

`POST /auth/register`

```json
{
  "email": "professor@escola.gov.br",
  "password": "uma-senha-com-8-ou-mais-caracteres",
  "name": "Professor(a)"
}
```

### Entrar com e-mail e senha

`POST /auth/login`

```json
{
  "email": "professor@escola.gov.br",
  "password": "uma-senha-com-8-ou-mais-caracteres"
}
```

Resposta dos dois endpoints:

```json
{
  "access_token": "jwt...",
  "user_id": "uuid-do-usuario",
  "email": "professor@escola.gov.br",
  "name": "Professor(a)",
  "picture_url": null
}
```

Também continua disponível `POST /auth/google` para o fluxo existente com
Google. Para conferir a sessão atual, use `GET /auth/me`.

## Turmas

Todas as rotas abaixo exigem Bearer JWT:

- `GET /api/turmas`
- `POST /api/turmas`
- `GET /api/turmas/{id}`
- `PATCH /api/turmas/{id}` ou `PUT /api/turmas/{id}`
- `DELETE /api/turmas/{id}`

Exemplo de criação/edição:

```json
{
  "school": "E.E. Cecília Meireles",
  "series": "6º Ano",
  "idSeries": "A",
  "qtd": 32,
  "disciplina": "Português",
  "color": "#7C3AED",
  "image": null
}
```

A resposta usa os mesmos nomes do tipo `Turma` do frontend: `id`, `school`,
`series`, `idSeries`, `qtd`, `disciplina`, `color`, `image` e
`lastModifiedAt`.

## Templates

- `GET /api/templates`
- `POST /api/templates`
- `GET /api/templates/{id}`
- `PATCH /api/templates/{id}` ou `PUT /api/templates/{id}`
- `DELETE /api/templates/{id}`

Payload:

```json
{
  "title": "Plano de aula padrão",
  "description": "Estrutura com objetivos e avaliação",
  "htmlContent": "<h1>Plano de aula</h1>",
  "turmaIds": ["uuid-da-turma"]
}
```

A resposta inclui `qtd`, `turmaIds`, `htmlContent` e `lastModifiedAt`.

## Materiais

- `GET /api/materiais`
- `POST /api/materiais`
- `GET /api/materiais/{id}`
- `PATCH /api/materiais/{id}` ou `PUT /api/materiais/{id}`
- `DELETE /api/materiais/{id}`

Payload:

```json
{
  "title": "Atividade de redação",
  "autoral": true,
  "orientation": "V",
  "type": "atv",
  "category": "atividade",
  "fileType": "html",
  "htmlContent": "<h1>Atividade</h1>",
  "fileUrl": null,
  "turmaIds": ["uuid-da-turma"]
}
```

Os valores aceitos são:

- `orientation`: `V` ou `H`;
- `type`: `source`, `slide` ou `atv`;
- `category`: `plano`, `material` ou `atividade`;
- `fileType`: `pdf` ou `html`.

## Sessões do workflow/agentes

O fluxo existente continua disponível em `/api/workflow/sessions`. Sem token,
ele mantém compatibilidade com o usuário mock `10`. Com Bearer JWT, a sessão é
vinculada à conta autenticada:

- `POST /api/workflow/sessions` cria a sessão;
- `GET /api/workflow/sessions` lista somente as sessões da conta;
- `GET /api/workflow/sessions/{id}` retoma uma sessão;
- `POST /api/workflow/sessions/{id}/messages` envia uma mensagem;
- `POST /api/workflow/sessions/{id}/advance` valida a passagem do brainstorm;
- `WS /api/workflow/sessions/{id}/ws` mantém o streaming existente.

No WebSocket, o token pode ser enviado como `?token=<access_token>` (ou pelo
header `Authorization: Bearer ...`). Sem token, o endpoint continua aceitando
o modo mock legado.

O banco também mantém os arquivos do sandbox vinculados à sessão. Portanto,
turmas, materiais, templates, mensagens e sessões não dependem do estado em
memória do processo.

## Estado atual da integração

Este contrato já está implementado no backend, mas o frontend ainda usa os
mocks e não chama esses endpoints. A próxima mudança no frontend deverá apenas
substituir as funções locais por chamadas para esta API e armazenar o JWT.
