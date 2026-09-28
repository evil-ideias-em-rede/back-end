# Back-End do Contraponto

Back-end do Contraponto, uma plataforma baseada em agentes de inteligência artificial para apoiar docentes na criação de materiais didáticos a partir de fontes primárias.

O projeto disponibiliza a API responsável pela comunicação entre a interface web, os agentes de IA, o banco de dados e os serviços externos utilizados pela aplicação.

## Tecnologias

* **Python**
* **FastAPI** — API REST
* **LangGraph** — orquestração dos agentes
* **LangChain** — integração com modelos e componentes de recuperação
* **PostgreSQL** — persistência dos dados da aplicação
* **SQLite / sqlite-vec** — componentes relacionados à recuperação de informações
* **OpenAI API** — modelos de linguagem e embeddings
* **JWT** — autenticação
* **Docker / Docker Compose** — execução dos serviços

As dependências do projeto estão disponíveis em `requirements.txt`.

## Estrutura

A organização principal do projeto é:

```text
back-end/
├── auth/             # Autenticação e gerenciamento de usuários
├── db/               # Configuração e acesso ao banco de dados
├── graph/            # Fluxos e agentes do sistema
├── routers/          # Endpoints da API
├── schema/           # Estruturas relacionadas aos dados
├── services/         # Serviços utilizados pela aplicação
├── .env-example      # Exemplo das variáveis de ambiente
├── API_FRONTEND.md   # Documentação da API utilizada pelo front-end
├── Dockerfile
├── docker-compose.yml
├── docker-entrypoint.sh
├── config.py
├── main.py           # Ponto de entrada da aplicação
├── README.md
├── requirements.txt
├── schemas.py
└── test_agent.py
```

## Requisitos

Para executar o projeto localmente, são necessários:

* Python 3.9 ou superior;
* PostgreSQL;
* Docker e Docker Compose, caso seja utilizada a configuração em containers;
* uma chave de API da OpenAI;
* uma chave de API do Tavily.

## Configuração

Clone o repositório e entre no diretório:

```bash
git clone https://github.com/evil-ideias-em-rede/back-end.git
cd back-end
```

Crie o arquivo `.env` a partir do exemplo disponibilizado:

```bash
cp .env-example .env
```

O arquivo `.env.example` apresenta as variáveis utilizadas pela aplicação, que são:

| Variável             | Descrição                                          |
| -------------------- | -------------------------------------------------- |
| `GOOGLE_CLIENT_ID`   | Identificador utilizado na autenticação com Google |
| `DATABASE_URL`       | URL de conexão com o PostgreSQL                    |
| `JWT_SECRET`         | Chave utilizada para geração dos tokens JWT        |
| `JWT_ALGORITHM`      | Algoritmo utilizado na autenticação JWT            |
| `JWT_EXPIRE_MINUTES` | Tempo de expiração dos tokens                      |
| `OPENAI_MODEL_NAME`  | Modelo de linguagem utilizado pela aplicação       |
| `OPENAI_API_KEY`     | Chave de acesso à API da OpenAI                    |

Preencha as variáveis de acordo com o ambiente de execução.

**Não versione o arquivo `.env` nem chaves de API ou outras credenciais.**

## Execução com Python

Crie um ambiente virtual:

```bash
python -m venv .venv
```

Ative o ambiente virtual.

No Linux/macOS:

```bash
source .venv/bin/activate
```

No Windows:

```powershell
.venv\Scripts\activate
```

Instale as dependências:

```bash
pip install -r requirements.txt
```

A aplicação pode então ser iniciada pelo ponto de entrada definido em `main.py`.

Para executar o servidor diretamente com Uvicorn:

```bash
uvicorn main:app --reload
```

A opção `--reload` deve ser utilizada durante o desenvolvimento.

## Execução com Docker

O projeto também disponibiliza `Dockerfile` e `docker-compose.yml` para execução em containers.

Após configurar o arquivo `.env`, execute:

```bash
docker compose up --build
```

O `docker-compose.yml` configura o serviço do back-end e o banco de dados utilizado pela aplicação.

Por padrão, a API é disponibilizada localmente na porta configurada pelo projeto.

Para interromper os serviços:

```bash
docker compose down
```

## API

A API é organizada em diferentes grupos de endpoints, incluindo funcionalidades relacionadas a:

* autenticação;
* usuários;
* turmas;
* templates;
* materiais;
* interação com os agentes.

A documentação destinada à integração com o front-end está disponível em [API_FRONTEND.md](https://github.com/evil-ideias-em-rede/back-end/blob/sandbox/API_FRONTEND.md)

Quando a aplicação está em execução, o FastAPI também disponibiliza sua documentação interativa nos endpoints padrão de documentação da aplicação.

## Agentes

A lógica dos agentes está organizada no diretório `graph/`.

O fluxo utiliza **LangGraph** para organizar as etapas de processamento e geração dos materiais.

De forma simplificada:

```text
Solicitação do docente
        ↓
API
        ↓
Fluxo de agentes
        ↓
Recuperação de informações
        ↓
Modelo de linguagem
        ↓
Material gerado
        ↓
API
        ↓
Front-end
```

Os agentes utilizam informações recuperadas de diferentes fontes disponíveis ao sistema para fornecer contexto ao processo de geração.

## Banco de dados e recuperação

O projeto utiliza PostgreSQL para persistência dos dados da aplicação.

Componentes relacionados à recuperação de informações também estão presentes na configuração do projeto, incluindo `sqlite-vec` e estruturas de índice utilizadas pelo sistema.

O `docker-compose.yml` configura os serviços necessários para o ambiente de desenvolvimento e disponibiliza os volumes utilizados pela aplicação.

## Integração com o front-end

O back-end fornece a API consumida pelo repositório `front-end`.

As rotas, métodos HTTP, parâmetros e estruturas das requisições e respostas utilizadas pela interface estão documentados em:

```text
API_FRONTEND.md
```

O front-end deve estar configurado para utilizar o endereço da API correspondente ao ambiente em que o back-end estiver sendo executado.

## Reprodução do ambiente

Para reproduzir o ambiente utilizado no desenvolvimento do projeto:

1. Clone o repositório.
2. Configure as variáveis de ambiente a partir de `.env-example`.
3. Instale as dependências de `requirements.txt` ou utilize Docker.
4. Configure o PostgreSQL.
5. Inicie o back-end.
6. Verifique a documentação da API em `API_FRONTEND.md`.
7. Configure o front-end para utilizar a URL da API.

O objetivo deste repositório é disponibilizar o código e a configuração necessários para executar o back-end do protótipo do Contraponto.
