#!/usr/bin/env python3
"""
Verify that the live database has all required tables and columns from migrations.
This script connects directly to the database without requiring Docker or local setup.

Usage:
    export DATABASE_URL="postgresql://user:pass@host/dbname"
    poetry run python verify_live_db.py
"""

import asyncio
import os
import sys
import psycopg


async def verify_migrations():
    """Verify the live database has all required tables from migrations"""
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        print("Usage: export DATABASE_URL='postgresql://...' && poetry run python verify_live_db.py")
        sys.exit(1)
    
    try:
        conn = await psycopg.AsyncConnection.connect(database_url)
        print("✓ Connected to live database\n")
        
        # Check for required tables (migrations 001-005)
        required_tables = [
            "users",
            "typing_sessions", 
            "keystroke_events",
            "typing_profiles"
        ]
        
        print("Checking tables:")
        all_tables_exist = True
        for table in required_tables:
            cursor = await conn.execute(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
                (table,)
            )
            result = await cursor.fetchone()
            exists = result[0] if result else False
            status = "✓" if exists else "✗"
            print(f"  {status} '{table}'")
            if not exists:
                all_tables_exist = False
        
        # Check for important columns from recent migrations
        print("\nChecking migration-specific columns:")
        
        # Check for document_id column (from migration 008)
        cursor = await conn.execute(
            "SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='typing_sessions' AND column_name='document_id')"
        )
        result = await cursor.fetchone()
        doc_id_exists = result[0] if result else False
        status = "✓" if doc_id_exists else "✗"
        print(f"  {status} typing_sessions.document_id (migration 008)")
        
        # Check for longestPauseMicros in session_metrics JSONB (from migration 007)
        # This is a JSONB key, not a column, so we check a sample row
        # If the table is empty or no rows have the old key, migration 007 may have run without updates
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM typing_sessions WHERE session_metrics ? 'longestPauseMicros'"
        )
        result = await cursor.fetchone()
        longestpause_count = result[0] if result else 0
        
        # Also check if table has any data
        cursor = await conn.execute("SELECT COUNT(*) FROM typing_sessions")
        result = await cursor.fetchone()
        sessions_count = result[0] if result else 0
        
        longest_pause_exists = longestpause_count > 0 or sessions_count == 0
        status = "✓" if longest_pause_exists else "✗"
        if sessions_count == 0:
            print(f"  {status} typing_sessions.session_metrics['longestPauseMicros'] (migration 007 - table empty, skipped)")
        else:
            print(f"  {status} typing_sessions.session_metrics['longestPauseMicros'] (migration 007)")
        
        # Check extensions (from migration 001)
        print("\nChecking extensions:")
        cursor = await conn.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'uuid-ossp')"
        )
        result = await cursor.fetchone()
        uuid_ext_exists = result[0] if result else False
        status = "✓" if uuid_ext_exists else "✗"
        print(f"  {status} uuid-ossp extension")
        
        await conn.close()
        
        # Summary
        print("\n" + "="*50)
        if all_tables_exist and doc_id_exists and longest_pause_exists and uuid_ext_exists:
            print("✓ All migrations verified successfully!")
            print("="*50)
            return 0
        else:
            print("✗ Some migrations are missing!")
            print("="*50)
            return 1
        
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    exit_code = asyncio.run(verify_migrations())
    sys.exit(exit_code)
