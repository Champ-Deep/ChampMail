from unittest.mock import AsyncMock, MagicMock

import pytest

from app.tasks import sequences, sending
from app.services.sequence_service import sequence_service
from app.db.champgraph import graph_db


@pytest.mark.parametrize("result", [
    {"success": True, "message_id": "sink-message"},
    {"status": "skipped", "reason": "suppressed"},
    {"status": "blocked", "reason": "send_gate:paused"},
    {"status": "deferred", "reason": "Throttle limit reached"},
    RuntimeError("transport failed"),
])
def test_sequence_uses_guarded_sender(monkeypatch, result):
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(sequences, "async_session", lambda: session)
    step = dict(id="execution", prospect_id="prospect", prospect_email="sink@example.test",
                sequence_id="sequence", step_order=1, subject="Hello", body="Body")
    for name in ("get_pending_steps", "mark_step_sent", "mark_step_failed", "schedule_next_step"):
        monkeypatch.setattr(sequence_service, name, AsyncMock())
    sequence_service.get_pending_steps.return_value = [step]
    sender = AsyncMock(side_effect=result if isinstance(result, Exception) else None,
                       return_value=result)
    monkeypatch.setattr(sending, "_send_email", sender)
    monkeypatch.setattr(graph_db, "record_email_sent", AsyncMock())

    sequences.execute_pending_steps.run()

    sender.assert_awaited_once_with(prospect_id="prospect", template_id="",
                                   subject="Hello", html_body="Body")
    if isinstance(result, dict) and result.get("success"):
        sequence_service.mark_step_sent.assert_awaited_once_with(session, "execution", "sink-message")
        sequence_service.schedule_next_step.assert_awaited_once_with(session, "sequence", "prospect", 2)
        sequence_service.mark_step_failed.assert_not_awaited()
    else:
        sequence_service.mark_step_sent.assert_not_awaited()
        sequence_service.schedule_next_step.assert_not_awaited()
        if isinstance(result, dict) and result.get("status") == "deferred":
            sequence_service.mark_step_failed.assert_not_awaited()
        else:
            sequence_service.mark_step_failed.assert_awaited_once()
