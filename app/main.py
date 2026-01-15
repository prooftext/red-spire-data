from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.database import init_db, close_db
from app.routers import collect, verify

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()

app = FastAPI(
    title="Prooftext API",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(collect.router, prefix="/api/v1/keystroke", tags=["collect"])
app.include_router(verify.router, prefix="/api/v1/keystroke", tags=["verify"])

@app.get("/health")
async def health():
    return {"status": "healthy"}