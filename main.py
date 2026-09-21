from contextlib import asynccontextmanager
import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from db.pool import close_pool, init_pool
from routers import (
    auth_router,
    chat_router,
    content_router,
    html_pdf_router,
    sandbox_router,
    workflow_messages_router,
    workflow_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Só libera a aplicação depois que o pool existe. Caso contrário o
    # /health fica verde, mas as rotas de cadastro, chat e workflow retornam 500.
    for attempt in range(5):
        try:
            await asyncio.wait_for(init_pool(), timeout=60)
            break
        except Exception:
            await close_pool()
            if attempt == 4:
                raise
            await asyncio.sleep(2)
    yield
    await close_pool()


app = FastAPI(title="Chat API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(chat_router.router)
app.include_router(content_router.router)
app.include_router(workflow_router.router)
app.include_router(workflow_messages_router.router)
app.include_router(html_pdf_router.router)
app.include_router(sandbox_router.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


frontend_dir = Path(__file__).parent / "frontend"
if frontend_dir.is_dir():
    # Em desenvolvimento o frontend pode rodar em um container/processo
    # separado. Nesse caso o backend não deve falhar só porque não há uma
    # cópia estática dentro da imagem.
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
