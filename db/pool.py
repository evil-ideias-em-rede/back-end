import asyncpg
from typing import Optional
from pathlib import Path

from config import DATABASE_URL


_pool: Optional[asyncpg.Pool] = None


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        schema_path = Path(__file__).resolve().parent.parent / "schema" / "schema.sql"
        pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=10)
        try:
            await pool.execute(schema_path.read_text(encoding="utf-8"))
        except Exception:
            await pool.close()
            raise
        _pool = pool
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None: raise RuntimeError("Pool não inicializada. Confirme que o lifespan do FastAPI rodou init_pool().")
    return _pool
