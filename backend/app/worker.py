"""No-op worker loop. M1 replaces the body of tick() with dispatch work."""
import logging
import signal
import threading

from app.config import get_settings

log = logging.getLogger("champmail.worker")
stop = threading.Event()


def tick() -> None:
    log.info("worker tick")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    settings = get_settings()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    log.info("worker started env=%s", settings.champmail_env)
    while not stop.is_set():
        tick()
        stop.wait(settings.worker_interval_seconds)
    log.info("worker stopped")


if __name__ == "__main__":
    main()
