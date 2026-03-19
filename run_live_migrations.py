#!/usr/bin/env python3
"""
Run database migrations on the live database using psycopg.
This script applies all SQL migrations from the database-fiiles/migrations directory.
"""

import asyncio
import os
import sys
import hashlib
from typing import LiteralString, cast
from pathlib import Path

import psycopg


SCHEMA_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_name TEXT PRIMARY KEY,
    migration_checksum TEXT NOT NULL,
    applied_method TEXT NOT NULL DEFAULT 'executed',
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

# Common PostgreSQL error codes for "already exists" duplicate object states.
IDEMPOTENT_SQLSTATES = {
    "42P07",  # duplicate_table
    "42710",  # duplicate_object
    "42701",  # duplicate_column
}


def _checksum(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _extract_up_sql(sql_content: str) -> str:
    if "-- UP" in sql_content:
        sql_content = sql_content.split("-- UP", 1)[1]
        if "-- DOWN" in sql_content:
            sql_content = sql_content.split("-- DOWN", 1)[0]
    return sql_content.strip()


def _is_idempotent_error(error: Exception) -> bool:
    if isinstance(error, psycopg.Error) and error.sqlstate in IDEMPOTENT_SQLSTATES:
        return True

    error_text = str(error).lower()
    return "already exists" in error_text


async def _ensure_schema_migrations_table(conn: psycopg.AsyncConnection) -> None:
    await conn.execute(SCHEMA_MIGRATIONS_TABLE)


async def _get_applied_migrations(conn: psycopg.AsyncConnection) -> dict[str, str]:
    cursor = await conn.execute("SELECT migration_name, migration_checksum FROM schema_migrations")
    rows = await cursor.fetchall()
    return {row[0]: row[1] for row in rows}


async def _record_migration(
    conn: psycopg.AsyncConnection,
    migration_name: str,
    migration_checksum: str,
    applied_method: str,
) -> None:
    await conn.execute(
        """
        INSERT INTO schema_migrations (migration_name, migration_checksum, applied_method, applied_at)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (migration_name) DO UPDATE
        SET migration_checksum = EXCLUDED.migration_checksum,
            applied_method = EXCLUDED.applied_method,
            applied_at = EXCLUDED.applied_at
        """,
        (migration_name, migration_checksum, applied_method),
    )


async def _run_migration_statements(conn: psycopg.AsyncConnection, sql_content: str) -> str:
    if not sql_content.strip():
        return "noop"

    try:
        await conn.execute(cast(LiteralString, sql_content))
        return "executed"
    except Exception as error:
        if _is_idempotent_error(error):
            return "adopted"
        raise


async def run_migrations():
    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        print("Please set DATABASE_URL to your database connection string")
        print("Example: postgresql://user:password@host:5432/dbname")
        sys.exit(1)
    
    # Find migrations directory
    migrations_dir = Path(__file__).parent.parent / "database-fiiles" / "migrations"
    
    if not migrations_dir.exists():
        print(f"ERROR: Migrations directory not found at {migrations_dir}")
        sys.exit(1)
    
    # Get all SQL migration files, sorted by name
    migration_files = sorted(migrations_dir.glob("*.sql"))
    
    if not migration_files:
        print(f"No migration files found in {migrations_dir}")
        sys.exit(1)
    
    print(f"Found {len(migration_files)} migration files")
    print(f"Connecting to database: {database_url.split('@')[1] if '@' in database_url else database_url}")
    
    try:
        # Connect to the database
        conn = await psycopg.AsyncConnection.connect(database_url, autocommit=True)
        print("✓ Connected to database")

        await _ensure_schema_migrations_table(conn)
        applied = await _get_applied_migrations(conn)
        
        # Run each migration
        for migration_file in migration_files:
            migration_name = migration_file.name
            file_content = migration_file.read_text()
            up_sql = _extract_up_sql(file_content)
            migration_checksum = _checksum(up_sql)

            if migration_name in applied:
                existing_checksum = applied[migration_name]
                if existing_checksum != migration_checksum:
                    print(f"✗ ERROR: checksum mismatch for already-applied migration {migration_name}")
                    print("  Existing migration record differs from current file contents.")
                    await conn.close()
                    sys.exit(1)
                print(f"- Skipping {migration_name} (already applied)")
                continue

            print(f"\nRunning migration: {migration_name}")
            
            try:
                method = await _run_migration_statements(conn, up_sql)
                await _record_migration(conn, migration_name, migration_checksum, method)
                print(f"✓ {migration_name} completed ({method})")
                
            except Exception as e:
                print(f"✗ ERROR in {migration_name}: {e}")
                await conn.close()
                sys.exit(1)
        
        await conn.close()
        print("\n" + "="*50)
        print("✓ All migrations completed successfully!")
        print("="*50)
        
    except Exception as e:
        print(f"✗ Database connection error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_migrations())
