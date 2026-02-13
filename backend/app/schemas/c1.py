"""Pydantic schemas for C1 Chat endpoints."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """A single chat message."""
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str


class C1ChatRequest(BaseModel):
    """Request body for C1 chat endpoint."""
    messages: list[ChatMessage]
    context_type: str = Field(default="general", pattern="^(general|analytics|campaign)$")
    conversation_id: Optional[str] = None


class C1ChatSyncResponse(BaseModel):
    """Response body for non-streaming C1 chat."""
    content: str
    conversation_id: Optional[str] = None


class ConversationSummary(BaseModel):
    """Summary of a saved conversation."""
    id: str
    title: str
    message_count: int
    updated_at: str
