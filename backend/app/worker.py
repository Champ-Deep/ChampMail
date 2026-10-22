"""Worker loop: poll mailboxes for DSNs, then drain the outbound events outbox."""
import asyncio
import logging
import signal

import httpx

from app.config import get_settings
from app.db.postgres import async_session_maker
from app.services.bounce_poller import poll_all
from app.services.outbound_events import drain

log = logging.getLogger("champmail.worker")


async def tick(client: httpx.AsyncClient) -> None:
    try:
        async with async_session_maker() as session:
            await poll_all(session)
    except Exception:  # a poll failure must not block event delivery
        log.exception("bounce poll failed")
    await drain(async_session_maker, client)


async def run(stop: asyncio.Event) -> None:
    settings = get_settings()
    log.info("worker started env=%s", settings.champmail_env)
    async with httpx.AsyncClient(timeout=10) as client:
        while not stop.is_set():
            try:
                await tick(client)
            except Exception:
                log.exception("worker tick failed")
            try:
                await asyncio.wait_for(stop.wait(), settings.worker_interval_seconds)
            except asyncio.TimeoutError:
                pass
    log.info("worker stopped")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    async def _main() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        await run(stop)

    asyncio.run(_main())


if __name__ == "__main__":
    main()
