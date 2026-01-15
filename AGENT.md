
***

## AGENT.md – Backend Service Repository

```markdown
# AGENT.md – Prooftext Keystroke Biometrics API Service

## Project Purpose

This repository contains the FastAPI backend service for the Prooftext Keystroke Biometrics Authentication System. The service:

- Receives keystroke event streams from client plugins
- Computes behavioral metrics and human probability scores
- Stores sessions and events in PostgreSQL
- Provides full-text search to verify if text was human-authored

---

## Technology Stack

| Language | Technology |
|-----------|------------|
| Language | Python 3.13+ |
| Framework | FastAPI |
| Database Driver | asyncpg |
| Validation | Pydantic v2 |
| ML/Stats | NumPy, scikit-learn |
| Hosting | Render Web Service |

---

## Repository Structure

├── app/
│ ├── init.py
│ ├── main.py # FastAPI app entry point
│ ├── config.py # Settings and environment
│ ├── database.py # asyncpg connection pool
│ ├── models/
│ │ ├── init.py
│ │ ├── requests.py # Pydantic request models
│ │ └── responses.py # Pydantic response models
│ ├── routers/
│ │ ├── init.py
│ │ ├── collect.py # POST /api/v1/keystroke/collect
│ │ └── verify.py # POST /api/v1/keystroke/verify
│ ├── services/
│ │ ├── init.py
│ │ ├── features.py # Feature extraction from events
│ │ ├── scoring.py # Human probability calculation
│ │ └── search.py # Full-text search logic
│ └── repositories/
│ ├── init.py
│ ├── sessions.py # typing_sessions CRUD
│ ├── events.py # keystroke_events CRUD
│ └── users.py # users CRUD
├── tests/
│ ├── conftest.py
│ ├── test_collect.py
│ ├── test_verify.py
│ └── test_scoring.py
├── pyproject.toml
├── poetry.lock
├── Dockerfile
├── render.yaml
└── README.md

text

---

## API Endpoints

### POST /api/v1/keystroke/collect

Receives a typing session with raw keystroke events.

**Request Body:**
```json
{
  "session_id": "uuid",
  "user_id": "uuid",
  "document_text": "The complete typed text...",
  "events": [
    {
      "eventType": "keypress",
      "key": "T",
      "keyCode": 84,
      "timestamp": "2026-01-15T10:00:00.123456Z",
      "pressTime": "2026-01-15T10:00:00.123456Z",
      "releaseTime": "2026-01-15T10:00:00.198234Z",
      "dwellTimeMicros": 74778,
      "flightTimeMicros": null,
      "cursorPosition": 0,
      "sequence": 0
    }
  ],
  "metadata": {
    "device_id": "uuid",
    "app_version": "1.0",
    "platform": "web"
  }
}
Response:

json
{
  "session_id": "uuid",
  "human_probability": 0.92,
  "verification_status": "yes",
  "metrics": {
    "totalKeystrokes": 245,
    "avgDwellTimeMicros": 71500,
    "pasteRatio": 0.02
  }
}
POST /api/v1/keystroke/verify
Checks if a document can be proven human-authored.

Request Body:

json
{
  "document_text": "Text to search for..."
}
Response:

json
{
  "can_prove_human": "yes",
  "confidence": 0.94,
  "matched_session_id": "uuid"
}
Pydantic Models
Request Models (app/models/requests.py)
python
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class KeystrokeEvent(BaseModel):
    eventType: str
    key: Optional[str] = None
    keyCode: Optional[int] = None
    timestamp: datetime
    pressTime: Optional[datetime] = None
    releaseTime: Optional[datetime] = None
    dwellTimeMicros: Optional[int] = None
    flightTimeMicros: Optional[int] = None
    cursorPosition: Optional[int] = None
    sequence: int
    pastedLength: Optional[int] = None
    deletedLength: Optional[int] = None
    formatAction: Optional[str] = None
    selectedRange: Optional[dict] = None
    modifiers: Optional[dict] = None

class CollectRequest(BaseModel):
    session_id: str
    user_id: str
    document_text: str
    events: List[KeystrokeEvent]
    metadata: dict = {}

class VerifyRequest(BaseModel):
    document_text: str
Response Models (app/models/responses.py)
python
from pydantic import BaseModel
from typing import Optional

class CollectResponse(BaseModel):
    session_id: str
    human_probability: float
    verification_status: str
    metrics: dict

class VerifyResponse(BaseModel):
    can_prove_human: str  # "yes", "no", "maybe"
    confidence: float
    matched_session_id: Optional[str] = None
Service Layer
Feature Extraction (app/services/features.py)
Extracts behavioral metrics from raw keystroke events.

python
import numpy as np
from typing import List
from app.models.requests import KeystrokeEvent

def extract_metrics(events: List[KeystrokeEvent]) -> dict:
    """
    Compute session-level metrics from raw events.
    
    Returns dict with:
    - totalKeystrokes
    - avgDwellTimeMicros, stdDwellTimeMicros
    - avgFlightTimeMicros, stdFlightTimeMicros
    - wpm (words per minute)
    - pasteEvents, copyEvents
    - backspaceCount, deleteCount
    - formatChanges
    - pausesOver2Sec, longestPauseMs
    - pasteRatio
    """
    # Implementation here
    pass
Scoring (app/services/scoring.py)
Calculates human probability from metrics.

python
def calculate_human_score(metrics: dict) -> float:
    """
    Returns probability (0.0 - 1.0) that session was human-typed.
    
    Key indicators:
    - High paste ratio → lower score
    - Low timing variance → lower score (AI is too consistent)
    - No backspaces → lower score
    - Very high WPM with low errors → lower score
    """
    score = 1.0
    
    # Paste behavior
    if metrics.get("pasteRatio", 0) > 0.5:
        score -= 0.4
    elif metrics.get("pasteRatio", 0) > 0.2:
        score -= 0.2
    
    # Timing variance (humans have natural variability)
    std_dwell = metrics.get("stdDwellTimeMicros", 0)
    if std_dwell < 5000:  # Too consistent
        score -= 0.3
    
    # Error correction (humans make mistakes)
    total = metrics.get("totalKeystrokes", 1)
    backspaces = metrics.get("backspaceCount", 0)
    error_rate = backspaces / total if total > 0 else 0
    if error_rate < 0.01:  # Suspiciously few corrections
        score -= 0.2
    
    return max(0.0, min(1.0, score))


def determine_status(probability: float) -> str:
    """Map probability to verification status."""
    if probability > 0.9:
        return "yes"
    elif probability > 0.5:
        return "maybe"
    return "no"
Search (app/services/search.py)
Full-text search across all documents.

python
async def search_document(conn, text: str) -> dict:
    """
    Search typing_sessions for matching document.
    Returns best match with human probability.
    """
    row = await conn.fetchrow("""
        SELECT session_id, user_id, human_probability, verification_status,
               ts_rank_cd(document_tsvector, query) AS rank
        FROM typing_sessions, plainto_tsquery('english', $1) query
        WHERE document_tsvector @@ query
        ORDER BY rank DESC
        LIMIT 1
    """, text)
    return dict(row) if row else None
Database Access (app/database.py)
python
import asyncpg
from app.config import settings

pool = None

async def init_db():
    global pool
    pool = await asyncpg.create_pool(
        settings.DATABASE_URL,
        min_size=2,
        max_size=10
    )

async def close_db():
    global pool
    if pool:
        await pool.close()

def get_pool():
    return pool
Configuration (app/config.py)
python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    DEBUG: bool = False
    API_VERSION: str = "v1"
    
    class Config:
        env_file = ".env"

settings = Settings()
Main Application (app/main.py)
python
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
    title="Keystroke Biometrics API",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(collect.router, prefix="/api/v1/keystroke", tags=["collect"])
app.include_router(verify.router, prefix="/api/v1/keystroke", tags=["verify"])

@app.get("/health")
async def health():
    return {"status": "healthy"}
Router Examples
Collect Router (app/routers/collect.py)
python
from fastapi import APIRouter, BackgroundTasks
from app.models.requests import CollectRequest
from app.models.responses import CollectResponse
from app.services.features import extract_metrics
from app.services.scoring import calculate_human_score, determine_status
from app.repositories.sessions import create_session
from app.repositories.events import bulk_insert_events
from app.database import get_pool

router = APIRouter()

@router.post("/collect", response_model=CollectResponse)
async def collect_keystroke(request: CollectRequest, background: BackgroundTasks):
    pool = get_pool()
    async with pool.acquire() as conn:
        # Extract metrics
        metrics = extract_metrics(request.events)
        
        # Calculate human probability
        human_prob = calculate_human_score(metrics)
        status = determine_status(human_prob)
        
        # Store session
        await create_session(conn, request, metrics, human_prob, status)
        
        # Store events in background (non-blocking)
        background.add_task(bulk_insert_events, request.session_id, request.events)
        
        return CollectResponse(
            session_id=request.session_id,
            human_probability=human_prob,
            verification_status=status,
            metrics=metrics
        )
Verify Router (app/routers/verify.py)
python
from fastapi import APIRouter
from app.models.requests import VerifyRequest
from app.models.responses import VerifyResponse
from app.services.search import search_document
from app.database import get_pool

router = APIRouter()

@router.post("/verify", response_model=VerifyResponse)
async def verify_text(request: VerifyRequest):
    pool = get_pool()
    async with pool.acquire() as conn:
        result = await search_document(conn, request.document_text)
        
        if not result:
            return VerifyResponse(
                can_prove_human="no",
                confidence=0.0,
                matched_session_id=None
            )
        
        prob = result.get("human_probability", 0.0)
        if prob > 0.9:
            verdict = "yes"
        elif prob > 0.5:
            verdict = "maybe"
        else:
            verdict = "no"
        
        return VerifyResponse(
            can_prove_human=verdict,
            confidence=prob,
            matched_session_id=str(result["session_id"])
        )
Dependencies (pyproject.toml)
toml
[tool.poetry.dependencies]
python = "^3.13"
fastapi = "0.109.0"
uvicorn = {extras = ["standard"], version = "0.27.0"}
gunicorn = "21.2.0"
asyncpg = "0.29.0"
pydantic = "2.0.0"
pydantic-settings = "2.0.0"
python-jose = {extras = ["cryptography"], version = "3.3.0"}
passlib = {extras = ["bcrypt"], version = "1.7.4"}
httpx = "0.26.0"

[tool.poetry.group.dev.dependencies]
pytest = "7.4.4"
pytest-asyncio = "0.23.3"
Render Deployment (render.yaml)
text
services:
  - type: web
    name: red-spire-data
    runtime: python
    buildCommand: "poetry install --no-dev"
    startCommand: "poetry run gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:10000"
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: prooftext
          property: connectionString
      - key: DEBUG
        value: "false"

databases:
  - name: prooftext
    plan: free
Environment Variables
Variable	Required	Description
DATABASE_URL	Yes	PostgreSQL connection string
DEBUG	No	Enable debug mode (default: false)
Testing Guidelines
Use pytest with pytest-asyncio for async tests

Mock database with asyncpg test utilities or in-memory fixtures

Test scoring edge cases:

100% paste session → should return low score

Normal typing with backspaces → should return high score

Zero timing variance → should flag as suspicious

Test full-text search with partial matches and exact matches

Coding Standards
Async everywhere: All database calls must be async

Type hints: All functions must have type annotations

Pydantic validation: Use Pydantic models for all request/response bodies

Repository pattern: Keep SQL in repository layer, not in routers

Service layer: Business logic in services, not routers

Background tasks: Use FastAPI BackgroundTasks for heavy processing

Error handling: Return proper HTTP status codes (400, 404, 500)

Logging: Use structured logging for debugging

Future Enhancements
Replace heuristic scoring with trained ML model (TypeNet-style LSTM)

Add Redis caching for frequently searched documents

Implement rate limiting per user

Add webhook notifications for verification results

Support batch document verification


