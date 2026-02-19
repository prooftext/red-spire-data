from fastapi import FastAPI
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os
from pathlib import Path
from app.database import init_db, close_db
from app.routers import collect, verify, documentation
from app.routers import sessions as sessions_router

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
    description="Keystroke biometrics API - Captures typing patterns and verifies text authenticity",
    lifespan=lifespan
)

app.include_router(collect.router, prefix="/api/v1/keystroke", tags=["collect"])
app.include_router(verify.router, prefix="/api/v1/keystroke", tags=["verify"])
app.include_router(sessions_router.router, prefix="/api/v1/keystroke", tags=["sessions"])
app.include_router(documentation.router, prefix="/api/v1/keystroke", tags=["documentation"])

# Serve static files
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/")
async def root():
    landing_page = static_dir / "index.html" if static_dir.exists() else None
    if landing_page and landing_page.exists():
        return FileResponse(str(landing_page), media_type="text/html")
    return RedirectResponse(url="/docs")

@app.get("/verify")
async def verify_page():
    verify_page_file = static_dir / "verify.html" if static_dir.exists() else None
    if verify_page_file and verify_page_file.exists():
        return FileResponse(str(verify_page_file), media_type="text/html")
    return RedirectResponse(url="/docs")

@app.get("/test-verify")
async def test_verify_page():
    test_verify_file = static_dir / "test-verify.html" if static_dir.exists() else None
    if test_verify_file and test_verify_file.exists():
        return FileResponse(str(test_verify_file), media_type="text/html")
    return RedirectResponse(url="/docs")

@app.get("/health")
async def health():
    return {"status": "healthy"}