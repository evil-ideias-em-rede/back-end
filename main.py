from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from db.pool import close_pool, init_pool
from routers import auth_router, chat_router, workflow_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # O protótipo do fluxo usa memória e pode subir sem Postgres. As rotas
    # legadas de chat continuam disponíveis quando o banco estiver configurado.
    try:
        await init_pool()
    except Exception as exc:
        app.state.database_error = str(exc)
    yield
    await close_pool()


app = FastAPI(title="Chat API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrinja aos domínios do seu frontend em produção
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(chat_router.router)
app.include_router(workflow_router.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


app.mount("/", StaticFiles(directory=Path(__file__).parent / "frontend", html=True), name="frontend")
