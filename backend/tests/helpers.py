"""Shared fixtures for the events/tracking/IMAP tests: dispatch rows and a real TCP HTTP receiver."""
from __future__ import annotations

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from sqlalchemy import select

from app.models import OutboundEvent, SendDispatch


async def add_dispatch(Session, domain_id, mailbox_id, message_id=None, status="sent") -> str:
    """A known send_dispatches row (what every event must refer to)."""
    message_id = message_id or f"{uuid.uuid4().hex}@fixture.test"
    async with Session() as s:
        s.add(SendDispatch(message_id=message_id, domain_id=domain_id, mailbox_id=mailbox_id,
                           payload_hash="0" * 64, status=status))
        await s.commit()
    return message_id


async def outbox(Session) -> list[OutboundEvent]:
    async with Session() as s:
        return list((await s.execute(select(OutboundEvent).order_by(OutboundEvent.created_at, OutboundEvent.event_type))).scalars())


class Receiver:
    """Real HTTP server on a loopback port. `script` is the list of status codes to answer with, in order;
    after it runs out every request gets 200. `lose_ack=True` records the request then drops the connection."""

    def __init__(self, script=(), lose_ack=False):
        self.script, self.requests, self.lose_ack = list(script), [], lose_ack
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append((dict(self.headers), body))
                if outer.lose_ack:
                    self.connection.close()
                    return
                code = outer.script.pop(0) if outer.script else 200
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"updated":1}')

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
