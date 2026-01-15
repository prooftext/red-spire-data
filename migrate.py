import asyncio
import asyncpg
import os
from pathlib import Path

async def run_migrations():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    conn = await asyncpg.connect(database_url)

    migrations_dir = Path("../database-fiiles/migrations")
    if not migrations_dir.exists():
        raise FileNotFoundError("Migrations directory not found")

    for sql_file in sorted(migrations_dir.glob("*.sql")):
        print(f"Running {sql_file.name}")
        sql = sql_file.read_text()
        await conn.execute(sql)

    await conn.close()
    print("Migrations completed")

if __name__ == "__main__":
    asyncio.run(run_migrations())