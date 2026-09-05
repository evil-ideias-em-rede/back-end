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