async def get_or_create_user_by_google(conn, google_id, email, name=None, picture_url=None):
    row = await conn.fetchrow(
        "SELECT id, google_id, email, name, picture_url FROM users WHERE google_id=$1",
        google_id,
    )
    if row:
        return await conn.fetchrow(
            """
            UPDATE users
            SET email=$1, name=$2, picture_url=$3, updated_at=NOW()
            WHERE id=$4
            RETURNING id, google_id, email, name, picture_url
            """,
            email, name, picture_url, row["id"],
        )

    return await conn.fetchrow(
        """
        INSERT INTO users (google_id, email, name, picture_url)
        VALUES ($1, $2, $3, $4)
        RETURNING id, google_id, email, name, picture_url
        """,
        google_id, email, name, picture_url,
    )


async def get_user_by_google_id(conn, google_id):
    return await conn.fetchrow(
        "SELECT id, google_id, email, name, picture_url FROM users WHERE google_id=$1",
        google_id,
    )


async def get_user_by_email(conn, email):
    return await conn.fetchrow(
        """
        SELECT id, google_id, email, name, picture_url, password_hash
        FROM users
        WHERE LOWER(email)=LOWER($1)
        """,
        email,
    )


async def create_password_user(conn, email, password_hash, name=None):
    return await conn.fetchrow(
        """
        INSERT INTO users (email, name, password_hash)
        VALUES ($1, $3, $2)
        RETURNING id, google_id, email, name, picture_url, password_hash
        """,
        email,
        password_hash,
        name,
    )


async def get_user_by_id(conn, user_id):
    return await conn.fetchrow(
        """
        SELECT id, google_id, email, name, picture_url
        FROM users
        WHERE id=$1
        """,
        user_id,
    )


async def list_user_schools(conn, user_id):
    return await conn.fetch(
        """
        SELECT id, name, created_at, updated_at
        FROM schools
        WHERE user_id=$1
        ORDER BY LOWER(name), created_at
        """,
        user_id,
    )


async def update_user_profile(conn, user_id, email, name, picture_url):
    return await conn.fetchrow(
        """
        UPDATE users
        SET email=$2, name=$3, picture_url=$4, updated_at=NOW()
        WHERE id=$1
        RETURNING id, google_id, email, name, picture_url
        """,
        user_id,
        email,
        name,
        picture_url,
    )


async def replace_user_schools(conn, user_id, school_names):
    async with conn.transaction():
        await conn.execute("DELETE FROM schools WHERE user_id=$1", user_id)
        for name in school_names:
            await conn.execute(
                "INSERT INTO schools (user_id, name) VALUES ($1, $2)",
                user_id,
                name,
            )


async def create_chat_tab(conn, user_id, title):
    return await conn.fetchrow(
        """
        INSERT INTO chat_tabs (user_id, title)
        VALUES ($1, $2)
        RETURNING id, title, created_at, updated_at
        """,
        user_id, title,
    )


async def delete_chat_tab(conn, chat_tab_id):
    async with conn.transaction():
        await conn.execute("DELETE FROM chat_messages WHERE chat_tab_id=$1", chat_tab_id)
        await conn.execute("DELETE FROM chat_tabs WHERE id=$1", chat_tab_id)


async def update_at_by_chat_tab_id(conn, chat_tab_id):
    await conn.execute("UPDATE chat_tabs SET updated_at = NOW() WHERE id=$1", chat_tab_id)


async def update_chat_tab_context(conn, chat_tab_id, context):
    await conn.execute("UPDATE chat_tabs SET context=$1 WHERE id=$2", context, chat_tab_id)


async def update_chat_title(conn, chat_tab_id, title):
    await conn.execute("UPDATE chat_tabs SET title=$1 WHERE id=$2", title, chat_tab_id)


async def get_chat_tab_context(conn, chat_tab_id):
    row = await conn.fetchrow("SELECT context FROM chat_tabs WHERE id = $1", chat_tab_id)
    return row["context"] if row and "context" in row else None


async def get_chat_tabs_by_google_id(conn, google_id):
    return await conn.fetch(
        """
        SELECT ct.id, ct.title, ct.created_at, ct.updated_at
        FROM chat_tabs ct
        JOIN users u ON ct.user_id = u.id
        WHERE u.google_id = $1
        ORDER BY ct.updated_at DESC
        """,
        google_id,
    )


async def get_chat_tabs_by_user_id(conn, user_id):
    return await conn.fetch(
        """
        SELECT id, title, created_at, updated_at
        FROM chat_tabs
        WHERE user_id = $1
        ORDER BY updated_at DESC
        """,
        user_id,
    )


async def get_chat_tab_for_user(conn, chat_id, google_id):
    return await conn.fetchrow(
        """
        SELECT ct.id, ct.title, ct.context
        FROM chat_tabs ct
        JOIN users u ON ct.user_id = u.id
        WHERE ct.id = $1 AND u.google_id = $2
        """,
        chat_id, google_id,
    )


async def get_chat_tab_for_user_id(conn, chat_id, user_id):
    return await conn.fetchrow(
        """
        SELECT id, title, context
        FROM chat_tabs
        WHERE id = $1 AND user_id = $2
        """,
        chat_id,
        user_id,
    )



async def get_chat_messages_by_chat_id(conn, chat_id):
    return await conn.fetch(
        """
        SELECT id, role, content, filename, created_at
        FROM chat_messages
        WHERE chat_tab_id = $1
        ORDER BY created_at
        """,
        chat_id,
    )


async def add_chat_message(conn, chat_tab_id, role, content, filename):
    await conn.execute(
        """
        INSERT INTO chat_messages (chat_tab_id, role, content, filename)
        VALUES ($1, $2, $3, $4)
        """,
        chat_tab_id, role, content, filename,
    )


async def create_workflow_session(conn, session_id, user_id, selected_agent, workdir_id, owner_user_id=None):
    return await conn.fetchrow(
        """
        INSERT INTO workflow_sessions
            (id, user_id, owner_user_id, selected_agent, workdir_id, current_stage)
        VALUES ($1, $2, $3, $4, $5, 'audiences')
        RETURNING id, user_id, owner_user_id, selected_agent, workdir_id,
                  current_stage, created_at, updated_at
        """,
        session_id, user_id, owner_user_id, selected_agent, workdir_id,
    )


async def get_workflow_sessions(conn, user_id):
    return await conn.fetch(
        """
        SELECT
            s.id,
            s.selected_agent,
            s.current_stage,
            s.created_at,
            s.updated_at,
            COUNT(m.id)::int AS message_count,
            MAX(m.created_at) AS last_message_at,
            (
                SELECT recent.content
                FROM workflow_messages recent
                WHERE recent.session_id = s.id
                ORDER BY recent.created_at DESC, recent.id DESC
                LIMIT 1
            ) AS last_message
        FROM workflow_sessions s
        LEFT JOIN workflow_messages m ON m.session_id = s.id
        WHERE s.user_id = $1
        GROUP BY s.id, s.selected_agent, s.current_stage, s.created_at, s.updated_at
        ORDER BY COALESCE(MAX(m.created_at), s.created_at) DESC
        """,
        user_id,
    )


async def get_workflow_session(conn, session_id):
    return await conn.fetchrow(
        """
        SELECT id, user_id, owner_user_id, selected_agent, workdir_id,
               current_stage, created_at, updated_at
        FROM workflow_sessions
        WHERE id=$1
        """,
        session_id,
    )


async def get_workflow_session_for_owner(conn, session_id, owner_user_id):
    return await conn.fetchrow(
        """
        SELECT id, user_id, owner_user_id, selected_agent, workdir_id,
               current_stage, created_at, updated_at
        FROM workflow_sessions
        WHERE id=$1 AND (owner_user_id=$2 OR owner_user_id IS NULL)
        """,
        session_id,
        owner_user_id,
    )


async def delete_workflow_session(conn, session_id, owner_user_id=None):
    return await conn.fetchrow(
        """
        DELETE FROM workflow_sessions
        WHERE id=$1 AND ($2::uuid IS NULL OR owner_user_id=$2::uuid OR owner_user_id IS NULL)
        RETURNING id, workdir_id
        """,
        session_id,
        owner_user_id,
    )


async def add_workflow_message(conn, session_id, agent_name, role, content, hidden=False):
    return await conn.fetchrow(
        """
        INSERT INTO workflow_messages (session_id, agent_name, role, content, hidden)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, session_id, agent_name, role, content, hidden, created_at
        """,
        session_id, agent_name, role, content, hidden,
    )


async def get_workflow_messages(conn, session_id):
    return await conn.fetch(
        """
        SELECT id, session_id, agent_name, role, content, hidden, created_at
        FROM workflow_messages
        WHERE session_id=$1
        ORDER BY created_at, id
        """,
        session_id,
    )


async def replace_workflow_files(conn, session_id, files):
    await conn.execute("DELETE FROM workflow_files WHERE session_id=$1", session_id)
    if files:
        await conn.executemany(
            """
            INSERT INTO workflow_files (session_id, path, content)
            VALUES ($1, $2, $3)
            """,
            [(session_id, path, content) for path, content in files],
        )


async def get_workflow_files(conn, session_id):
    return await conn.fetch(
        """
        SELECT path, content, updated_at
        FROM workflow_files
        WHERE session_id=$1
        ORDER BY path
        """,
        session_id,
    )


async def create_workflow_session_for_owner(
    conn,
    session_id,
    user_id,
    selected_agent,
    workdir_id,
    owner_user_id,
):
    return await conn.fetchrow(
        """
        INSERT INTO workflow_sessions
            (id, user_id, owner_user_id, selected_agent, workdir_id, current_stage)
        VALUES ($1, $2, $3, $4, $5, 'audiences')
        RETURNING id, user_id, owner_user_id, selected_agent, workdir_id,
                  current_stage, created_at, updated_at
        """,
        session_id,
        user_id,
        owner_user_id,
        selected_agent,
        workdir_id,
    )


async def get_workflow_sessions_for_owner(conn, owner_user_id):
    return await conn.fetch(
        """
        SELECT
            s.id,
            s.selected_agent,
            s.current_stage,
            s.created_at,
            s.updated_at,
            COUNT(m.id)::int AS message_count,
            MAX(m.created_at) AS last_message_at,
            (
                SELECT recent.content
                FROM workflow_messages recent
                WHERE recent.session_id = s.id
                ORDER BY recent.created_at DESC, recent.id DESC
                LIMIT 1
            ) AS last_message
        FROM workflow_sessions s
        LEFT JOIN workflow_messages m ON m.session_id = s.id
        WHERE s.owner_user_id = $1
        GROUP BY s.id, s.selected_agent, s.current_stage, s.created_at, s.updated_at
        ORDER BY COALESCE(MAX(m.created_at), s.created_at) DESC
        """,
        owner_user_id,
    )


async def update_workflow_session_stage(conn, session_id, current_stage):
    return await conn.fetchrow(
        """
        UPDATE workflow_sessions
        SET current_stage = $2, updated_at = CURRENT_TIMESTAMP
        WHERE id = $1
        RETURNING id, current_stage, updated_at
        """,
        session_id,
        current_stage,
    )


# ---------------------------------------------------------------------------
# Recursos do painel do professor
# ---------------------------------------------------------------------------

async def list_turmas(conn, user_id):
    return await conn.fetch(
        """
        SELECT id, school, series, id_series, student_count, disciplina,
               color, image, created_at, updated_at
        FROM turmas
        WHERE user_id=$1
        ORDER BY updated_at DESC, created_at DESC
        """,
        user_id,
    )


async def get_turma(conn, user_id, turma_id):
    return await conn.fetchrow(
        """
        SELECT id, school, series, id_series, student_count, disciplina,
               color, image, created_at, updated_at
        FROM turmas
        WHERE id=$1 AND user_id=$2
        """,
        turma_id,
        user_id,
    )


async def create_turma(conn, user_id, school, series, id_series, student_count, disciplina, color, image):
    return await conn.fetchrow(
        """
        INSERT INTO turmas
            (user_id, school, series, id_series, student_count, disciplina, color, image)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id, school, series, id_series, student_count, disciplina,
                  color, image, created_at, updated_at
        """,
        user_id,
        school,
        series,
        id_series,
        student_count,
        disciplina,
        color,
        image,
    )


async def update_turma(conn, user_id, turma_id, school, series, id_series, student_count, disciplina, color, image):
    return await conn.fetchrow(
        """
        UPDATE turmas
        SET school=$3, series=$4, id_series=$5, student_count=$6,
            disciplina=$7, color=$8, image=$9, updated_at=NOW()
        WHERE id=$2 AND user_id=$1
        RETURNING id, school, series, id_series, student_count, disciplina,
                  color, image, created_at, updated_at
        """,
        user_id,
        turma_id,
        school,
        series,
        id_series,
        student_count,
        disciplina,
        color,
        image,
    )


async def delete_turma(conn, user_id, turma_id):
    return await conn.execute(
        "DELETE FROM turmas WHERE id=$1 AND user_id=$2",
        turma_id,
        user_id,
    )


async def list_templates(conn, user_id):
    return await conn.fetch(
        """
        SELECT t.id, t.title, t.description, t.html_content,
               t.created_at, t.updated_at,
               COALESCE(array_agg(tt.turma_id) FILTER (WHERE tt.turma_id IS NOT NULL), ARRAY[]::uuid[]) AS turma_ids,
               COUNT(tt.turma_id)::int AS qtd
        FROM templates t
        LEFT JOIN template_turmas tt ON tt.template_id=t.id
        WHERE t.user_id=$1
        GROUP BY t.id
        ORDER BY t.updated_at DESC, t.created_at DESC
        """,
        user_id,
    )


async def get_template(conn, user_id, template_id):
    return await conn.fetchrow(
        """
        SELECT t.id, t.title, t.description, t.html_content,
               t.created_at, t.updated_at,
               COALESCE(array_agg(tt.turma_id) FILTER (WHERE tt.turma_id IS NOT NULL), ARRAY[]::uuid[]) AS turma_ids,
               COUNT(tt.turma_id)::int AS qtd
        FROM templates t
        LEFT JOIN template_turmas tt ON tt.template_id=t.id
        WHERE t.id=$1 AND t.user_id=$2
        GROUP BY t.id
        """,
        template_id,
        user_id,
    )


async def create_template(conn, user_id, title, description, html_content):
    return await conn.fetchrow(
        """
        INSERT INTO templates (user_id, title, description, html_content)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        user_id,
        title,
        description,
        html_content,
    )


async def update_template(conn, user_id, template_id, title, description, html_content):
    return await conn.fetchrow(
        """
        UPDATE templates
        SET title=$3, description=$4, html_content=$5, updated_at=NOW()
        WHERE id=$2 AND user_id=$1
        RETURNING id
        """,
        user_id,
        template_id,
        title,
        description,
        html_content,
    )


async def delete_template(conn, user_id, template_id):
    return await conn.execute(
        "DELETE FROM templates WHERE id=$1 AND user_id=$2",
        template_id,
        user_id,
    )


async def replace_template_turmas(conn, template_id, turma_ids):
    await conn.execute("DELETE FROM template_turmas WHERE template_id=$1", template_id)
    if turma_ids:
        await conn.executemany(
            "INSERT INTO template_turmas (template_id, turma_id) VALUES ($1, $2)",
            [(template_id, turma_id) for turma_id in turma_ids],
        )


async def list_materiais(conn, user_id):
    return await conn.fetch(
        """
        SELECT m.id, m.title, m.autoral, m.orientation, m.type, m.category,
               m.file_type, m.html_content, m.file_url,
               m.created_at, m.updated_at,
               COALESCE(array_agg(mt.turma_id) FILTER (WHERE mt.turma_id IS NOT NULL), ARRAY[]::uuid[]) AS turma_ids,
               COUNT(mt.turma_id)::int AS qtd
        FROM materiais m
        LEFT JOIN material_turmas mt ON mt.material_id=m.id
        WHERE m.user_id=$1
        GROUP BY m.id
        ORDER BY m.updated_at DESC, m.created_at DESC
        """,
        user_id,
    )


async def get_material(conn, user_id, material_id):
    return await conn.fetchrow(
        """
        SELECT m.id, m.title, m.autoral, m.orientation, m.type, m.category,
               m.file_type, m.html_content, m.file_url,
               m.created_at, m.updated_at,
               COALESCE(array_agg(mt.turma_id) FILTER (WHERE mt.turma_id IS NOT NULL), ARRAY[]::uuid[]) AS turma_ids,
               COUNT(mt.turma_id)::int AS qtd
        FROM materiais m
        LEFT JOIN material_turmas mt ON mt.material_id=m.id
        WHERE m.id=$1 AND m.user_id=$2
        GROUP BY m.id
        """,
        material_id,
        user_id,
    )


async def create_material(conn, user_id, title, autoral, orientation, material_type, category, file_type, html_content, file_url):
    return await conn.fetchrow(
        """
        INSERT INTO materiais
            (user_id, title, autoral, orientation, type, category, file_type, html_content, file_url)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING id
        """,
        user_id,
        title,
        autoral,
        orientation,
        material_type,
        category,
        file_type,
        html_content,
        file_url,
    )


async def update_material(conn, user_id, material_id, title, autoral, orientation, material_type, category, file_type, html_content, file_url):
    return await conn.fetchrow(
        """
        UPDATE materiais
        SET title=$3, autoral=$4, orientation=$5, type=$6, category=$7,
            file_type=$8, html_content=$9, file_url=$10, updated_at=NOW()
        WHERE id=$2 AND user_id=$1
        RETURNING id
        """,
        user_id,
        material_id,
        title,
        autoral,
        orientation,
        material_type,
        category,
        file_type,
        html_content,
        file_url,
    )


async def delete_material(conn, user_id, material_id):
    return await conn.execute(
        "DELETE FROM materiais WHERE id=$1 AND user_id=$2",
        material_id,
        user_id,
    )


async def replace_material_turmas(conn, material_id, turma_ids):
    await conn.execute("DELETE FROM material_turmas WHERE material_id=$1", material_id)
    if turma_ids:
        await conn.executemany(
            "INSERT INTO material_turmas (material_id, turma_id) VALUES ($1, $2)",
            [(material_id, turma_id) for turma_id in turma_ids],
        )
