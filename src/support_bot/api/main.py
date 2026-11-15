from contextlib import asynccontextmanager

from fastapi import FastAPI

from .. import __version__, db, llm
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.open_pool(wait=False)
    yield
    llm.flush()
    db.close_pool()


app = FastAPI(title="Order Support Bot", version=__version__, lifespan=lifespan)
app.include_router(router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}
