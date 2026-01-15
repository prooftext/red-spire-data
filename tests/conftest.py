import pytest
from app.database import init_db, close_db

@pytest.fixture(scope="session")
async def db_pool():
    await init_db()
    yield
    await close_db()