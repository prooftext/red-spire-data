from psycopg_pool import AsyncConnectionPool
from app.config import settings
import asyncio

pool = None

async def init_db():
    global pool
    for _ in range(10):  # Retry up to 10 times
        try:
            pool = AsyncConnectionPool(settings.DATABASE_URL, min_size=2, max_size=10, open=False)
            await pool.open()
            # Test the connection
            async with pool.connection() as conn:
                await conn.execute("SELECT 1")
            break  # Success
        except Exception:
            if pool:
                await pool.close()
            pool = None
            await asyncio.sleep(2)  # Wait 2 seconds before retry
    if pool is None:
        raise RuntimeError("Failed to connect to database after retries")

async def close_db():
    global pool
    if pool:
        await pool.close()

def get_pool():
    return pool