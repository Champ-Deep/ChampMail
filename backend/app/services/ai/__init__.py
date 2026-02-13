"""
AI services module for ChampMail.
OpenRouter handles research/segmentation/pitch/HTML generation.
Thesys C1 handles generative UI chat.
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
from app.services.ai.thesys_service import thesys_service, ThesysC1Service
from app.services.ai.c1_context import c1_context, C1ContextBuilder

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
    "thesys_service",
    "ThesysC1Service",
    "c1_context",
    "C1ContextBuilder",
]
