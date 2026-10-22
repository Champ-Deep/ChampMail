from fastapi import APIRouter

from app.api.v1 import inboxkit_webhooks

router = APIRouter(prefix="/api/v1")
router.include_router(inboxkit_webhooks.router)
# M2 routers (send, domains, mailboxes) are included here.