#!/usr/bin/env python3
"""
Run database migrations on the live database using psycopg.
This script applies all SQL migrations from the database-fiiles/migrations directory.
"""

import asyncio
import os
import sys
from pathlib import Path

import psycopg


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
        conn = await psycopg.AsyncConnection.connect(database_url)
        print("✓ Connected to database")
        
        # Run each migration
        for migration_file in migration_files:
            migration_name = migration_file.name
            print(f"\nRunning migration: {migration_name}")
            
            try:
                sql_content = migration_file.read_text()
                
                # Split by common SQL comment blocks to extract just the UP section
                # (ignoring DOWN sections which are rollback instructions)
                if "-- UP" in sql_content:
                    sql_content = sql_content.split("-- UP")[1]
                    if "-- DOWN" in sql_content:
                        sql_content = sql_content.split("-- DOWN")[0]
                
                # Execute the migration
                await conn.execute(sql_content)
                print(f"✓ {migration_name} completed")
                
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
