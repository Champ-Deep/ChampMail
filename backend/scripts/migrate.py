#!/usr/bin/env python3
"""
Migration startup script for Railway deployment.
Handles Alembic migration drift gracefully.

Problem: Tables exist in DB (created by Base.metadata.create_all) but
alembic_version table has no record. Running `alembic upgrade head`
tries to create tables again -> DuplicateTableError.

Solution: Check if tables exist without alembic_version tracking,
stamp head to sync, then run upgrade head.
"""

import asyncio
import sys

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
    # Remove the +asyncpg prefix if present
    clean_url = pg_url
    if "+asyncpg://" in clean_url:
        clean_url = clean_url.replace("+asyncpg://", "://")

    try:
        conn = await asyncpg.connect(clean_url)
    except Exception as e:
        print(f"!!! Could not connect to database: {e}")
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
            # Table doesn't exist - check if any user tables exist
            user_tables_exist = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_type = 'BASE TABLE'
                    AND table_name IN ('users', 'teams')
                )
            """)

            if user_tables_exist:
                print("!!! Tables exist but alembic_version table missing")
                print("!!! Will stamp head to sync Alembic state")
                await conn.close()
                return True

            print("=== No existing tables found, will run migrations normally")
            await conn.close()
            return False

        # Check if alembic_version has any rows
        version_row = await conn.fetchrow("SELECT version_num FROM alembic_version")

        if version_row is None:
            # Table exists but no rows - tables were created outside Alembic
            user_tables_exist = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_type = 'BASE TABLE'
                    AND table_name IN ('users', 'teams')
                )
            """)

            if user_tables_exist:
                print("!!! alembic_version table is empty but user tables exist")
                print("!!! Will stamp head to sync Alembic state")
                await conn.close()
                return True

        await conn.close()
        return False

    except Exception as e:
        print(f"!!! Error checking migration state: {e}")
        await conn.close()
        return False


async def main():
    """Main entry point."""
    # Import settings after app dependencies are set up
    from app.core.config import settings

    pg_url = settings.postgres_url

    print("=== Checking database migration state ===")

    # First, check if we need to stamp
    needs_stamp = await check_and_fix_migration_state(pg_url)

    # Now run Alembic commands
    alembic_cfg = get_alembic_config()

    if needs_stamp:
        try:
            print("=== Stamping Alembic to current head ===")
            command.stamp(alembic_cfg, "head")
            print("=== Stamped successfully ===")
        except Exception as e:
            print(f"!!! Stamp failed: {e}")
            print("!!! Continuing anyway...")

    # Run migrations (will be no-op if already at head)
    try:
        print("=== Running Alembic upgrade head ===")
        command.upgrade(alembic_cfg, "head")
        print("=== Migrations OK ===")
    except Exception as e:
        print(f"!!! Upgrade failed: {e}")
        print("!!! Starting server anyway...")


if __name__ == "__main__":
    asyncio.run(main())
