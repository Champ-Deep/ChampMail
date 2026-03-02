#!/usr/bin/env python3
"""
Migration startup script for Railway deployment.
Handles Alembic migration drift gracefully.

Problem: Tables exist in DB (created by Base.metadata.create_all) but
alembic_version table has no record. Running `alembic upgrade head`
tries to create tables again -> DuplicateTableError.

Solution: Check if tables exist without alembic_version tracking,
stamp head to sync, then run upgrade head.

IMPORTANT: main() is intentionally SYNCHRONOUS. Alembic's env.py uses
asyncio.run() internally for async migrations. If main() were async
(inside its own asyncio.run()), Alembic's nested asyncio.run() would
crash with "cannot be called from a running event loop".
"""

import asyncio
import time

import asyncpg
from alembic.config import Config
from alembic import command


def get_alembic_config() -> Config:
    """Load Alembic configuration."""
    config = Config("alembic.ini")
    return config


async def check_and_fix_migration_state(pg_url: str) -> bool:
    """
    Check if tables exist without alembic_version tracking.
    If so, stamp the current head to sync Alembic's state.

    Returns True if tables exist (need stamping), False otherwise.
    """
    # Convert asyncpg URL format for direct connection
    clean_url = pg_url
    if "+asyncpg://" in clean_url:
        clean_url = clean_url.replace("+asyncpg://", "://")

    try:
        conn = await asyncpg.connect(clean_url, timeout=10)
    except Exception as e:
        print(f"!!! Could not connect to database: {e}", flush=True)
        return False

    try:
        # Check if alembic_version table exists
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'alembic_version'
            )
        """)

        if not table_exists:
            user_tables_exist = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_type = 'BASE TABLE'
                    AND table_name IN ('users', 'teams')
                )
            """)

            if user_tables_exist:
                print("!!! Tables exist but alembic_version table missing", flush=True)
                print("!!! Will stamp head to sync Alembic state", flush=True)
                return True

            print("=== No existing tables found, will run migrations normally", flush=True)
            return False

        # Check if alembic_version has any rows
        version_row = await conn.fetchrow("SELECT version_num FROM alembic_version")

        if version_row is None:
            user_tables_exist = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_type = 'BASE TABLE'
                    AND table_name IN ('users', 'teams')
                )
            """)

            if user_tables_exist:
                print("!!! alembic_version table is empty but user tables exist", flush=True)
                print("!!! Will stamp head to sync Alembic state", flush=True)
                return True

        return False

    except Exception as e:
        print(f"!!! Error checking migration state: {e}", flush=True)
        return False
    finally:
        await conn.close()


def main():
    """Main entry point — SYNCHRONOUS so Alembic can use its own asyncio.run()."""
    start = time.time()

    from app.core.config import settings

    pg_url = settings.postgres_url

    print("=== Checking database migration state ===", flush=True)

    # Run async DB check in its own event loop.
    # This loop completes and closes BEFORE we call any Alembic commands,
    # so env.py's asyncio.run() works fine (no enclosing loop).
    needs_stamp = asyncio.run(check_and_fix_migration_state(pg_url))

    # Now run Alembic commands (synchronous context — no event loop running)
    alembic_cfg = get_alembic_config()

    if needs_stamp:
        try:
            print("=== Stamping Alembic to current head ===", flush=True)
            command.stamp(alembic_cfg, "head")
            print("=== Stamped successfully ===", flush=True)
        except Exception as e:
            print(f"!!! Stamp failed: {e}", flush=True)
            print("!!! Continuing anyway...", flush=True)

    try:
        print("=== Running Alembic upgrade head ===", flush=True)
        command.upgrade(alembic_cfg, "head")
        print("=== Migrations OK ===", flush=True)
    except Exception as e:
        print(f"!!! Upgrade failed: {e}", flush=True)
        print("!!! Starting server anyway...", flush=True)

    elapsed = time.time() - start
    print(f"=== migrate.py completed in {elapsed:.1f}s ===", flush=True)


if __name__ == "__main__":
    main()
