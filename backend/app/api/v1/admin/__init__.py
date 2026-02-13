"""Admin API namespace."""
from fastapi import APIRouter
from app.api.v1.admin.prospect_lists import router as prospect_lists_router
from app.api.v1.admin.ai_campaigns import router as ai_campaigns_router

router = APIRouter(prefix="/admin", tags=["Admin"])
router.include_router(prospect_lists_router)
router.include_router(ai_campaigns_router)
