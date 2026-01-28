import pytest
import os
import sys
import asyncio
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import init_db, close_db, get_pool
from app.config import settings
import psycopg

# Set environment variables before importing app
os.environ["TESTING"] = "1"

async def create_test_database():
    """Create the test database if it doesn't exist"""
    try:
        conn = await psycopg.AsyncConnection.connect(
            "postgresql://postgres:password@localhost:5432",
            autocommit=True  # Disable transaction for CREATE DATABASE
        )
        try:
            # Drop the database if it exists
            try:
                # Terminate all connections to the database first
                await conn.execute("""
                    SELECT pg_terminate_backend(pg_stat_activity.pid)
                    FROM pg_stat_activity
                    WHERE pg_stat_activity.datname = 'testdb_new'
                    AND pid <> pg_backend_pid()
                """)
                await conn.execute("DROP DATABASE IF EXISTS testdb_new")
            except Exception:
                pass  # Database might not exist yet
            
            # Create the database
            await conn.execute("CREATE DATABASE testdb_new")
        finally:
            await conn.close()
    except Exception as e:
        print(f"Error creating test database: {e}")
        raise

async def run_migrations():
    pool = get_pool()
    if pool is None:
        raise RuntimeError("Database pool is not initialized")
    async with pool.connection() as conn:
        migration_dir = Path(__file__).parent.parent.parent / "database-fiiles" / "migrations"
        for sql_file in sorted(migration_dir.glob("*.sql")):
            with open(sql_file, 'r') as f:
                sql = f.read()
            await conn.execute(sql)

def pytest_configure(config):
    """Initialize database before tests run"""
    # Update settings for test database
    settings.DATABASE_URL = "postgresql://postgres:password@localhost:5432/testdb_new"
    settings.DEBUG = True
    settings.API_VERSION = "v1"
    
    # Run async setup in a new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(asyncio.sleep(5))  # Wait for DB to be ready
        loop.run_until_complete(create_test_database())  # Create test database
        loop.run_until_complete(init_db())
        loop.run_until_complete(run_migrations())
    finally:
        # Keep the loop alive for tests
        pass

def pytest_unconfigure(config):
    """Cleanup after tests"""
    try:
        loop = asyncio.get_event_loop()
        if not loop.is_closed():
            loop.run_until_complete(close_db())
    except Exception as e:
        print(f"Error during cleanup: {e}")

@pytest.fixture(scope="session")
def db_pool():
    """Fixture that ensures database is initialized before tests run.
    The actual initialization happens in pytest_configure."""
    yield None