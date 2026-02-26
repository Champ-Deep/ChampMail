"""
Seed script to sync PostgreSQL data to FalkorDB knowledge graph.
Run once: python -m app.scripts.seed_graph
"""

import asyncio
import logging
from uuid import UUID

from app.db.postgres import async_session
from app.db.falkordb import graph_db, FALKORDB_AVAILABLE
from app.models.campaign import Prospect
from sqlalchemy import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def seed_prospects():
    """Sync prospects from PostgreSQL to FalkorDB."""
    logger.info("Starting prospect seeding...")

    async with async_session() as session:
        result = await session.execute(select(Prospect).limit(10000))
        prospects = result.scalars().all()

    logger.info(f"Found {len(prospects)} prospects in PostgreSQL")

    created = 0
    for prospect in prospects:
        try:
            graph_db.create_prospect(
                email=prospect.email,
                first_name=prospect.first_name or "",
                last_name=prospect.last_name or "",
                title=prospect.job_title or "",
                company_name=prospect.company_name or "",
                company_domain=prospect.company_domain or "",
                industry=prospect.industry or "",
                company_size=prospect.company_size or "",
                linkedin_url=prospect.linkedin_url or "",
                status=prospect.status or "active",
                source=prospect.source or "",
            )
            created += 1

            if prospect.company_domain:
                graph_db.create_company(
                    name=prospect.company_name or prospect.company_domain,
                    domain=prospect.company_domain,
                    industry=prospect.industry or "",
                    employee_count=0,
                )

                graph_db.link_prospect_to_company(
                    prospect_email=prospect.email,
                    company_domain=prospect.company_domain,
                    title=prospect.job_title or "",
                )
        except Exception as e:
            logger.warning(f"Failed to create prospect {prospect.email}: {e}")

    logger.info(f"Created {created} prospect nodes in FalkorDB")


async def seed_sequences():
    """Sync sequences from PostgreSQL to FalkorDB."""
    from app.models.sequence import Sequence

    logger.info("Starting sequence seeding...")

    async with async_session() as session:
        result = await session.execute(select(Sequence).limit(1000))
        sequences = result.scalars().all()

    logger.info(f"Found {len(sequences)} sequences in PostgreSQL")

    created = 0
    for sequence in sequences:
        try:
            graph_db.create_sequence(
                name=sequence.name,
                owner_id=str(sequence.created_by) if sequence.created_by else "",
                steps_count=len(sequence.steps) if sequence.steps else 0,
            )
            created += 1
        except Exception as e:
            logger.warning(f"Failed to create sequence {sequence.name}: {e}")

    logger.info(f"Created {created} sequence nodes in FalkorDB")


async def main():
    """Run the seed script."""
    if not FALKORDB_AVAILABLE:
        logger.error("FalkorDB is not available. Install falkordb package to run seed.")
        return

    logger.info("=" * 50)
    logger.info("FalkorDB Knowledge Graph Seeding")
    logger.info("=" * 50)

    try:
        await seed_prospects()
        await seed_sequences()
        logger.info("=" * 50)
        logger.info("Seeding complete!")
        logger.info("=" * 50)
    except Exception as e:
        logger.error(f"Seeding failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
