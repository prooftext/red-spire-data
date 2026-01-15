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