# Test Setup Guide

## Local Unit Tests
**Location:** `tests/conftest.py` and `tests/test_*.py` (except test_live_server.py)

**Database:** Local Docker PostgreSQL
- Connection: `postgresql://test_user:test_password@localhost:5432/test_prooftext`
- Managed by: conftest.py pytest fixtures
- Lifecycle: Created fresh before each test run, torn down after

**Run command:**
```bash
poetry run pytest -v
# or
./run_tests.sh
```

**What's tested:**
- Unit tests in test_collect.py, test_verify.py, test_scoring.py
- All tests use local Docker database
- Tests are isolated and don't affect production data

---

## Live Server Integration Tests
**Location:** `tests/test_live_server.py`

**Target:** https://red-spire-data.onrender.com (live Render server)

**Database:** Live Render PostgreSQL
- Connection: `postgresql://prooftext_user:yTzTV7xmLlX5xjtveMEWjrnqB7FA8UaR@dpg-d5ka614oud1c73ef14ng-a.oregon-postgres.render.com/prooftext`
- Managed by: Render platform
- Lifecycle: Persistent, shared with production

Current replacement database:
- Connection: `postgresql://prooftext_db_28ip_user:KuDAiPqw90nMJpgjhUmNhhRmfrj3Apql@dpg-d7g81inlk1mc7382b8lg-a.oregon-postgres.render.com/prooftext_db_28ip`

**Run command:**
```bash
poetry run pytest tests/test_live_server.py -v
```

**What's tested:**
- Health endpoint responds
- API documentation accessible
- Full collect endpoint workflow
- Full verify endpoint workflow
- Input validation
- Database connectivity and data persistence

---

## Production Configuration
**How the Python server uses live database credentials:**

1. **Environment variable:** Render sets `DATABASE_URL` as an environment variable in the Web Service dashboard
2. **Configuration loading:** `app/config.py` uses Pydantic's `BaseSettings` with `ConfigDict(env_file=".env")`
   - In development: reads from `.env` file (contains live credentials as backup)
   - In production (Render): reads from environment variable (takes precedence over .env)
3. **Database initialization:** `app/database.py` uses `settings.DATABASE_URL` from config
4. **Connection pool:** FastAPI lifespan calls `init_db()` on startup, which creates the AsyncConnectionPool

**The chain:**
```
Render dashboard environment variable (DATABASE_URL)
  ↓
app/config.py (Settings.DATABASE_URL from BaseSettings)
  ↓
app/database.py init_db() (uses settings.DATABASE_URL)
  ↓
AsyncConnectionPool with live database connection
  ↓
All endpoints use pool.connection() for queries
```

---

## Environment Files
- `.env` - Local development (contains live DB credentials as backup)
- `.env.test` - Local test database config (used by conftest.py)
- Render dashboard - Production environment variables (takes precedence)

---

## Running Tests
```bash
# Local unit tests (uses Docker DB)
poetry run pytest -v

# Live server integration tests (uses live API)
poetry run pytest tests/test_live_server.py -v

# Specific test file
poetry run pytest tests/test_collect.py -v

# With output
poetry run pytest -v -s
```
