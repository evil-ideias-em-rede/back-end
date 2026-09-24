CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    google_id TEXT UNIQUE,               -- "sub" claim do token do Google
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    picture_url TEXT,
    password_hash TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Migração idempotente para bancos criados antes do login por e-mail.
-- Alguns ambientes antigos tinham apenas id/nome/matrícula/CPF. As colunas
-- abaixo são adicionadas sem remover esses dados.
ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS picture_url TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE users ALTER COLUMN google_id DROP NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_id_unique
    ON users (google_id) WHERE google_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique
    ON users (LOWER(email)) WHERE email IS NOT NULL;

-- Instituições cadastradas pelo professor. Cada conta possui sua própria lista.
CREATE TABLE IF NOT EXISTS schools (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (char_length(trim(name)) BETWEEN 1 AND 200),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_schools_user_name_unique
    ON schools (user_id, LOWER(name));
CREATE INDEX IF NOT EXISTS idx_schools_user_id ON schools(user_id);

CREATE TABLE IF NOT EXISTS chat_tabs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title TEXT,
    context TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chat_tab_id UUID REFERENCES chat_tabs(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT,
    filename TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_tabs_user_id ON chat_tabs(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_tab_id ON chat_messages(chat_tab_id);

-- Dados do painel do professor. Todos os registros pertencem a um usuário
-- autenticado e não são compartilhados entre contas.
CREATE TABLE IF NOT EXISTS turmas (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    school TEXT NOT NULL,
    series TEXT NOT NULL,
    id_series TEXT NOT NULL DEFAULT 'A',
    student_count INTEGER NOT NULL DEFAULT 0 CHECK (student_count >= 0),
    disciplina TEXT NOT NULL,
    color TEXT,
    image TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_turmas_user_id ON turmas(user_id);

CREATE TABLE IF NOT EXISTS templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    html_content TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_templates_user_id ON templates(user_id);

CREATE TABLE IF NOT EXISTS materiais (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    autoral BOOLEAN NOT NULL DEFAULT FALSE,
    orientation TEXT NOT NULL DEFAULT 'V' CHECK (orientation IN ('V', 'H')),
    type TEXT NOT NULL DEFAULT 'source' CHECK (type IN ('source', 'slide', 'atv')),
    category TEXT NOT NULL DEFAULT 'material' CHECK (category IN ('plano', 'material', 'atividade')),
    file_type TEXT NOT NULL DEFAULT 'html' CHECK (file_type IN ('pdf', 'html', 'docx')),
    html_content TEXT NOT NULL DEFAULT '',
    file_url TEXT,
    file_name TEXT,
    file_content BYTEA,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_materiais_user_id ON materiais(user_id);

CREATE TABLE IF NOT EXISTS template_turmas (
    template_id UUID NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
    turma_id UUID NOT NULL REFERENCES turmas(id) ON DELETE CASCADE,
    PRIMARY KEY (template_id, turma_id)
);

CREATE TABLE IF NOT EXISTS material_turmas (
    material_id UUID NOT NULL REFERENCES materiais(id) ON DELETE CASCADE,
    turma_id UUID NOT NULL REFERENCES turmas(id) ON DELETE CASCADE,
    PRIMARY KEY (material_id, turma_id)
);

CREATE INDEX IF NOT EXISTS idx_template_turmas_turma_id ON template_turmas(turma_id);
CREATE INDEX IF NOT EXISTS idx_material_turmas_turma_id ON material_turmas(turma_id);

ALTER TABLE templates ADD COLUMN IF NOT EXISTS file_name TEXT;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS file_content BYTEA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_templates_user_file_name
    ON templates(user_id, file_name)
    WHERE file_name IS NOT NULL;
ALTER TABLE materiais ADD COLUMN IF NOT EXISTS file_name TEXT;
ALTER TABLE materiais ADD COLUMN IF NOT EXISTS file_content BYTEA;

ALTER TABLE materiais DROP CONSTRAINT IF EXISTS materiais_file_type_check;
ALTER TABLE materiais ADD CONSTRAINT materiais_file_type_check CHECK (file_type IN ('pdf', 'html', 'docx'));

-- Fluxo público do ateliê de agentes. Mantém o mock separado de users,
-- porque users.id é UUID e o protótipo usa deliberadamente o usuário 10.
CREATE TABLE IF NOT EXISTS workflow_users (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO workflow_users (id, name, email)
VALUES (10, 'Usuário mock do workflow', 'workflow-user-10@example.local')
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS workflow_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id BIGINT NOT NULL REFERENCES workflow_users(id) ON DELETE CASCADE,
    selected_agent TEXT,
    workdir_id TEXT NOT NULL UNIQUE,
    current_stage TEXT NOT NULL DEFAULT 'audiences',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- A sessão pode voltar para a etapa em que o professor estava, mesmo quando
-- o HTML já foi salvo no sandbox.
ALTER TABLE workflow_sessions
    ADD COLUMN IF NOT EXISTS current_stage TEXT NOT NULL DEFAULT 'audiences';

-- Permite associar uma sessão do workflow a uma conta real sem remover o
-- usuário mock 10 usado pelo protótipo antigo.
ALTER TABLE workflow_sessions
    ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_workflow_sessions_owner_user_id
    ON workflow_sessions(owner_user_id);

CREATE TABLE IF NOT EXISTS workflow_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES workflow_sessions(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT,
    hidden BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_workflow_sessions_user_id ON workflow_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_workflow_messages_session_id ON workflow_messages(session_id);

CREATE TABLE IF NOT EXISTS workflow_files (
    session_id UUID NOT NULL REFERENCES workflow_sessions(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    content BYTEA NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_id, path)
);

CREATE INDEX IF NOT EXISTS idx_workflow_files_session_id ON workflow_files(session_id);
