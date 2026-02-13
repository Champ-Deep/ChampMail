"""
DEPRECATED: Claude service has been unified into openrouter_service.py.
All AI calls now go through OpenRouter. This file kept for import compatibility.
"""

# Re-export from unified service for backwards compatibility
from app.services.ai.openrouter_service import (
    pitch_service as claude_service,
    PitchService as ClaudeService,
)

__all__ = ["claude_service", "ClaudeService"]
