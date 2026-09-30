# Contraponto — instalação Linux com Docker

Esta distribuição prepara o cadastro de professores, turmas, templates,
materiais e os agentes de criação/edição em uma instalação independente.
O Compose de instalação inclui PostgreSQL, backend e frontend estático com
proxy HTTP/WebSocket. Não é necessário instalar Python, Node ou PostgreSQL no host.

## Arquitetura

O diagrama mostra a comunicação entre frontend, API, agente, ferramentas,
fontes de dados e sandbox de execução.

![Arquitetura frontend/backend do Contraponto](docs/arquitetura-front-back.svg)

### Agente LangGraph

Grafo exportado diretamente com `GRAPH_BUILDER.get_graph().draw_mermaid()`.
As setas condicionais mostram os destinos declarados; durante a execução,
o roteamento escolhe o caminho conforme o estado da conversa.

![Grafo do agente Contraponto gerado pelo LangGraph](docs/agente-langgraph-gerado.svg)

Consulte a [documentação da arquitetura](docs/arquitetura-contraponto.md)
para os endpoints, os dados enviados e as ferramentas disponíveis em cada modo.

## Requisitos

- Linux **x86_64**, Docker Engine e plugin Docker Compose v2 recente (com `up --wait`).
- Virtualização habilitada e `/dev/kvm` funcional. Em uma VM, habilite virtualização
  aninhada. Este pacote Docker **não foi preparado para Docker Desktop no Windows/macOS**.
- Sugestão inicial: 8 GB de RAM, 2 CPUs e pelo menos 10 GB de disco livre;
  uso simultâneo e quantidade de materiais podem exigir mais recursos.
- Internet no primeiro build/download e para as chamadas aos provedores de IA.
- Uma chave própria e um modelo com suporte a ferramentas no provedor de geração
  escolhido: OpenAI ou DeepInfra. OpenAI usa Responses API; DeepInfra usa
  Chat Completions. As chamadas de geração e embeddings podem gerar cobrança.
- Uma chave OpenAI continua necessária para a busca vetorial, mesmo com DeepInfra.
- A busca usa o índice distribuído com embeddings `text-embedding-3-small`,
  1536 dimensões. Não altere o modelo de embeddings sem reconstruir esse índice.

Não oferecemos execução de código do agente diretamente no host como fallback:
sem KVM, o instalador para com uma mensagem de orientação.

## Instalação

Obtenha os dois repositórios da mesma versão, em pastas irmãs:

```text
contraponto/
├── back-end/
└── front-end/
```

Repositórios: [backend](https://github.com/evil-ideias-em-rede/back-end) e
[frontend](https://github.com/evil-ideias-em-rede/front-end). Utilize uma versão
que contenha `compose.install.yml`, `scripts/install.sh` e o target `production`
no Dockerfile do frontend. Não misture versões antigas e novas.

Dentro de `back-end`:

```bash
bash scripts/install.sh --check
bash scripts/install.sh
```

Na primeira execução, o script cria `.env.install` com permissão 600 e senhas
aleatórias exclusivas para o banco e para a assinatura dos tokens. **Não utiliza
nem sobrescreve seu `.env` de desenvolvimento.** Edite `.env.install` e preencha:

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=sua-chave-openai
OPENAI_MODEL_NAME=modelo-disponivel-na-sua-conta
DEEPINFRA_API_KEY=
DEEPINFRA_MODEL=XiaomiMiMo/MiMo-V2.6-Pro
```

Para usar DeepInfra, troque apenas `LLM_PROVIDER=deepinfra` e preencha
`DEEPINFRA_API_KEY`. O modelo de geração será `DEEPINFRA_MODEL`;
`OPENAI_MODEL_NAME` só é necessário quando selecionar OpenAI. A flag vale para
todos os agentes (audiências e edição), SQL, classificação e reranking com LLM.
Embeddings continuam OpenAI (`text-embedding-3-small`): mantenha
`OPENAI_API_KEY` para usar o índice existente, sem reconstruí-lo. Não há troca
automática de provedor em caso de erro. Modelos precisam suportar ferramentas.

Referências: [DeepInfra Chat Completions](https://docs.deepinfra.com/chat/overview)
e [OpenAI Responses](https://developers.openai.com/api/docs/guides/migrate-to-responses).

No desenvolvimento, use as mesmas variáveis em `.env`. Depois de mudar provedor,
modelo ou chave, recrie o container do backend para carregar o ambiente novo
(um simples `docker compose restart` não atualiza variáveis de `env_file`):

```bash
docker compose up -d --build --force-recreate backend
```

Na instalação, execute novamente:

```bash
bash scripts/install.sh
```

O build inicial e a preparação da imagem do sandbox podem demorar. O instalador
aguarda a saúde dos serviços. Por padrão, abra **http://127.0.0.1:5173** e crie
sua conta por e-mail e senha; não há usuário/senha de administrador compartilhados.
O nome do modelo e a validade/quota da chave só são confirmados quando o provedor
recebe uma chamada; `/health` não consome créditos de IA.

`GOOGLE_CLIENT_ID` e `TAVILY_API_KEY` são opcionais. O cadastro por e-mail não
depende do Google. A busca externa na web depende da chave Tavily.

## Templates usados pelos agentes

Exceto no agente de slides, templates de `/home/templates` têm prioridade exclusiva: havendo uploads, o
sandbox contém apenas cópias dos templates do professor. Sem uploads, usa os
modelos de `shared/geral/templates`. Slides sempre recebe `slide-template.html`
como base obrigatória, mesmo com uploads pessoais; estes ficam disponíveis como
apoio. Os padrões de plano não entram no catálogo de slides. O brainstorm é
exclusivamente exploratório: só escreve `planning.json`, nunca gera `HTML.html`.
O catálogo é atualizado na criação da sessão,
antes de cada mensagem e na preparação das ferramentas, sem exigir reinício.
`consultar_templates` lista o catálogo e lê um HTML por vez nas duas telas,
validando o dono da sessão. Os prompts exigem uma base para gerar material;
edições pontuais preservam o documento atual. Originais no cadastro e no
repositório são preservados. Templates pessoais vazios não habilitam padrões.

## Dados e primeiro download

O PostgreSQL é criado vazio e o backend aplica `schema/schema.sql` de maneira
idempotente. Nenhuma conta, turma ou material da máquina do desenvolvedor é copiado.

Os dados públicos base e anotados precisam acompanhar a distribuição:

- `graph/tools/retrieval/public_hearing/PublicHearingBR_LDS.jsonl`;
- `graph/tools/retrieval/dados_camara/resultados_mimo_corpus/resultados_mimo_corpus.csv.gz`;
- os arquivos de `graph/tools/sandbox/shared/` e `graph/tools/retrieval/dados/`.

O instalador verifica os dois corpora. Se faltar o CSV compactado, obtenha o
pacote completo da mesma versão; não crie um CSV vazio para contornar a checagem.

O índice SQLite é baixado por HTTPS de `INDEX_DOWNLOAD_URL`, sem cookies ou login,
validado e instalado em volume. O endereço padrão é público, mas está sujeito à
disponibilidade e às quotas do provedor. É possível apontar para outro endereço
HTTPS com um arquivo `indice_busca.sqlite` compatível ou para uma pasta do Drive
contendo exatamente esse arquivo. Não coloque credenciais privadas nessa URL.
`INDEX_SHA256` permite conferir o checksum fornecido pelo distribuidor.

Um índice válido existente não é baixado novamente. Trocar apenas a URL **não**
substitui automaticamente o índice persistido. Em caso de índice incompatível,
uma cópia anterior é preservada antes da troca, e falhas no download não apagam
o arquivo existente. Mudanças de versão do índice devem ser planejadas com backup.

## Comandos do dia a dia

Todos os comandos de instalação precisam destes dois argumentos:

```bash
docker compose --env-file .env.install -f compose.install.yml ps
docker compose --env-file .env.install -f compose.install.yml logs --tail 100 backend
docker compose --env-file .env.install -f compose.install.yml down
docker compose --env-file .env.install -f compose.install.yml up -d --wait
```

Após atualizar os dois repositórios, faça backup e rode `bash scripts/install.sh`.
Se o Compose mantiver uma imagem antiga, use `up -d --build --force-recreate --wait`
com os mesmos argumentos. Isso reinicia os serviços; não atualize durante geração.

**Não use `down -v` nem `docker volume prune` para atualizar:** esses comandos
podem apagar banco, materiais e demais dados persistentes. Não troque
`POSTGRES_PASSWORD` em um volume já inicializado apenas editando o arquivo:
PostgreSQL não aplica essa mudança à senha existente; faça a rotação no banco.
Trocar `JWT_SECRET` encerra a validade dos tokens já emitidos.

Os volumes recebem por padrão o prefixo `contraponto_`. O compose antigo
`docker-compose.yml` continua reservado ao seu ambiente de desenvolvimento e
não migra seus dados automaticamente para a instalação nova.

## Backup e restauração

Pare novas conversas durante o backup. Guarde o banco, o volume `workdirs` e
`.env.install` em local privado; o índice pode ser baixado novamente e o cache
do microsandbox pode ser reconstruído. O banco também contém snapshots de
sandbox, mas o volume preserva arquivos ainda não persistidos.

Exemplo de backup do banco (o arquivo de saída não deve existir):

```bash
docker compose --env-file .env.install -f compose.install.yml exec -T db \
  pg_dump -U contraponto -d contraponto -Fc > contraponto-backup.dump
```

Para restaurar, use uma **instalação separada com banco vazio** e as mesmas
versões da aplicação. Inicie apenas `db`, importe com `pg_restore -U contraponto
-d contraponto --no-owner` dentro do serviço e restaure `workdirs` antes de
iniciar o backend. Não restaure sobre uma instalação com dados sem planejar a
mesclagem. Preserve `.env.install` para manter as chaves da instalação original.

## Rede e segurança

A instalação publica somente o frontend, em `127.0.0.1` por padrão. Banco e
backend não publicam portas no host. O navegador usa a mesma origem para a
interface, API e WebSocket: não depende de um IP específico compilado no JS.

Para LAN, altere `APP_BIND_ADDRESS` e `APP_PORT` conscientemente, configure
firewall e HTTPS em um proxy externo. **Este instalador local não é uma receita
completa de hospedagem pública:** TLS, limites de uso, antiautomação de cadastro,
observabilidade, backups e revisão de endpoints legados precisam ser definidos
antes de expor o serviço na internet. Cada execução do agente tem limites de
CPU/memória/tempo, mas não há limite de gastos de IA por usuário implementado.

## Problemas comuns

- **KVM ausente:** configure BIOS/UEFI, módulos KVM e, em VMs, virtualização aninhada.
- **Porta ocupada:** troque `APP_PORT` em `.env.install`; não encerre outros serviços.
- **Índice não baixa:** verifique acesso público à URL, quota do Drive e conectividade.
- **Serviço não fica saudável:** consulte os logs do backend e do banco, sem publicar
  `.env.install`, tokens ou chaves em pedidos de suporte.
- **401/403/429 do provedor:** confira chave, modelo disponível, saldo e limites da conta.
- **Frontend de desenvolvimento:** o target `development` mantém Vite; o target
  `production`, usado na instalação, serve o build estático via Nginx.

## Antes de distribuir uma versão (mantenedor)

- Versione os arquivos novos desta preparação e os dois corpora, especialmente
  o CSV compactado. Um arquivo só presente na sua máquina não chega ao clone.
- Publique versões compatíveis dos dois repositórios; não distribua `.env*`,
  `workdirs`, índices locais, backups ou chaves reais.
- Teste em volumes vazios e confirme cadastro/login, vínculos de turma,
  geração real com uma chave de teste própria e exportação PDF.
- Execute os testes em `tests/` e `npm run build` no frontend.
- Documente a versão/checksum do índice para distribuição reproduzível.

Referência de inicialização ordenada: [Docker Compose — dependências e saúde](https://docs.docker.com/compose/how-tos/startup-order/).
