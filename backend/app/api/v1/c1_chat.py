"""
Thesys C1 Generative UI chat endpoints.
Provides streaming SSE and sync chat, plus conversation management.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenData, require_auth
from app.db.postgres import get_db_session
from app.db.redis import redis_client
from app.schemas.c1 import (
    C1ChatRequest,
    C1ChatSyncResponse,
    ConversationSummary,
)
from app.services.ai.thesys_service import thesys_service
from app.services.ai.c1_context import c1_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/c1", tags=["C1 Chat"])

CONVERSATION_TTL = 86400  # 24 hours


def _conv_key(user_id: str, conv_id: str) -> str:
    return f"c1:chat:{user_id}:{conv_id}"


def _conv_index_key(user_id: str) -> str:
    return f"c1:conversations:{user_id}"


async def _save_conversation(
    user_id: str,
    conv_id: str,
    messages: list[dict],
    title: str | None = None,
):
    """Save conversation to Redis with TTL."""
    if not title and messages:
        # Use first user message as title
        for m in messages:
            if m.get("role") == "user":
                title = m["content"][:80]
                break
    title = title or "Untitled"

    data = {
        "id": conv_id,
        "title": title,
        "messages": messages,
        "message_count": len(messages),
        "updated_at": datetime.utcnow().isoformat(),
    }
    await redis_client.set_json(_conv_key(user_id, conv_id), data, ex=CONVERSATION_TTL)

    # Update conversation index
    index = await redis_client.get_json(_conv_index_key(user_id)) or []
    # Remove existing entry if present
    index = [c for c in index if c["id"] != conv_id]
    index.insert(0, {"id": conv_id, "title": title, "message_count": len(messages), "updated_at": data["updated_at"]})
    # Keep max 50 conversations in index
    index = index[:50]
    await redis_client.set_json(_conv_index_key(user_id), index, ex=CONVERSATION_TTL)


@router.post("/chat")
async def c1_chat_stream(
    body: C1ChatRequest,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Streaming SSE chat endpoint for C1 Generative UI.

    Enriches with user data context, then streams SSE from Thesys C1.
    """
    if not thesys_service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Thesys C1 is not configured. Set THESYS_API_KEY to enable AI Assistant.",
        )

    # Build data-enriched system prompt
    system_prompt = await c1_context.build_system_prompt(user, session, body.context_type)

    # Build message list with system prompt prepended
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend([m.model_dump() for m in body.messages])

    # Generate or reuse conversation ID
    conv_id = body.conversation_id or str(uuid.uuid4())

    async def stream_response():
        full_content = ""
        try:
            async for chunk in thesys_service.chat_stream(messages):
                full_content += chunk
                yield f"data: {json.dumps({'content': chunk})}\n\n"

            # Send completion event with conversation ID
            yield f"data: {json.dumps({'done': True, 'conversation_id': conv_id})}\n\n"

            # Save conversation after streaming completes
            all_messages = [m.model_dump() for m in body.messages]
            all_messages.append({"role": "assistant", "content": full_content})
            await _save_conversation(user.user_id, conv_id, all_messages)

        except Exception as e:
            logger.error(f"C1 streaming error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/sync", response_model=C1ChatSyncResponse)
async def c1_chat_sync(
    body: C1ChatRequest,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Non-streaming C1 chat for simple queries."""
    if not thesys_service.is_configured:
        raise HTTPException(status_code=503, detail="Thesys C1 is not configured.")

    system_prompt = await c1_context.build_system_prompt(user, session, body.context_type)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend([m.model_dump() for m in body.messages])

    conv_id = body.conversation_id or str(uuid.uuid4())

    content = await thesys_service.chat(messages)

    # Save conversation
    all_messages = [m.model_dump() for m in body.messages]
    all_messages.append({"role": "assistant", "content": content})
    await _save_conversation(user.user_id, conv_id, all_messages)

    return C1ChatSyncResponse(content=content, conversation_id=conv_id)


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(user: TokenData = Depends(require_auth)):
    """List user's saved chat conversations."""
    index = await redis_client.get_json(_conv_index_key(user.user_id)) or []
    return [ConversationSummary(**c) for c in index]


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    user: TokenData = Depends(require_auth),
):
    """Get a specific conversation with full message history."""
    data = await redis_client.get_json(_conv_key(user.user_id, conversation_id))
    if not data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return data


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    user: TokenData = Depends(require_auth),
):
    """Delete a conversation."""
    await redis_client.delete(_conv_key(user.user_id, conversation_id))
    # Remove from index
    index = await redis_client.get_json(_conv_index_key(user.user_id)) or []
    index = [c for c in index if c["id"] != conversation_id]
    await redis_client.set_json(_conv_index_key(user.user_id), index, ex=CONVERSATION_TTL)
