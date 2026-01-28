from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager
import os
from app.database import init_db, close_db
from app.routers import collect, verify

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.getenv("TESTING"):
        await init_db()
        yield
        await close_db()
    else:
        yield

app = FastAPI(
    title="Prooftext API",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(collect.router, prefix="/api/v1/keystroke", tags=["collect"])
app.include_router(verify.router, prefix="/api/v1/keystroke", tags=["verify"])

@app.get("/")
async def root():
    return RedirectResponse(url="/docs")

@app.get("/health")
async def health():
    return {"status": "healthy"}