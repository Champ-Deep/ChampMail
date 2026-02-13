"""
AI services module for ChampMail.
All AI operations route through OpenRouter.
"""

from app.services.ai.openrouter_service import (
    research_service,
    segmentation_service,
    essence_service,
    pitch_service,
    html_service,
    OpenRouterClient,
    ResearchService,
    SegmentationService,
    CampaignEssenceService,
    PitchService,
    HTMLGenerationService,
)

__all__ = [
    "research_service",
    "segmentation_service",
    "essence_service",
    "pitch_service",
    "html_service",
    "OpenRouterClient",
    "ResearchService",
    "SegmentationService",
    "CampaignEssenceService",
    "PitchService",
    "HTMLGenerationService",
]
