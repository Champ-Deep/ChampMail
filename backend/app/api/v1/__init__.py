from fastapi import APIRouter

from app.api.v1 import domains, inboxkit_webhooks, mailboxes, send

router = APIRouter(prefix="/api/v1")
router.include_router(inboxkit_webhooks.router)
router.include_router(send.router)
router.include_router(domains.router)
router.include_router(mailboxes.router)
