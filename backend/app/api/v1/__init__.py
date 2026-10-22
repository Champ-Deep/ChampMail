from fastapi import APIRouter

from app.api.v1 import inboxkit_webhooks, send

router = APIRouter(prefix="/api/v1")
router.include_router(inboxkit_webhooks.router)
router.include_router(send.router)
# M2 routers (domains, mailboxes) are included here.