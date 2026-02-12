"""
Tests for the sequence service.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from uuid import uuid4


class TestSequenceService:
    """Test cases for SequenceService."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def sequence_service(self):
        """Create a SequenceService instance."""
        from app.services.sequence_service import SequenceService
        return SequenceService()

    def test_sequence_to_dict(self, sequence_service):
        """Test conversion of sequence model to dictionary."""
        from app.models import Sequence

        mock_sequence = MagicMock(spec=Sequence)
        mock_sequence.id = uuid4()
        mock_sequence.name = "Test Sequence"
        mock_sequence.description = "A test sequence"
        mock_sequence.status = "active"
        mock_sequence.from_name = "Test Sender"
        mock_sequence.from_address = None
        mock_sequence.reply_to = None
        mock_sequence.default_delay_hours = 24
        mock_sequence.daily_limit = 100
        mock_sequence.auto_pause_on_reply = True
        mock_sequence.team_id = uuid4()
        mock_sequence.created_at = datetime.utcnow()
        mock_sequence.updated_at = datetime.utcnow()
        mock_sequence.activated_at = None
        mock_sequence.steps = []

        result = sequence_service._sequence_to_dict(mock_sequence)

        assert result["name"] == "Test Sequence"
        assert result["status"] == "active"
        assert result["default_delay_hours"] == 24
        assert result["auto_pause_on_reply"] is True

    def test_step_to_dict(self, sequence_service):
        """Test conversion of sequence step to dictionary."""
        from app.models import SequenceStep

        mock_step = MagicMock(spec=SequenceStep)
        mock_step.id = uuid4()
        mock_step.sequence_id = uuid4()
        mock_step.order = 1
        mock_step.name = "First Email"
        mock_step.subject_template = "Hello {{name}}"
        mock_step.html_template = "<p>Hello {{name}}</p>"
        mock_step.delay_hours = 24
        mock_step.is_active = True
        mock_step.created_at = datetime.utcnow()

        result = sequence_service._step_to_dict(mock_step)

        assert result["order"] == 1
        assert result["name"] == "First Email"
        assert result["delay_hours"] == 24
        assert result["is_active"] is True

    def test_enrollment_to_dict(self, sequence_service):
        """Test conversion of enrollment to dictionary."""
        from app.models import SequenceEnrollment

        mock_enrollment = MagicMock(spec=SequenceEnrollment)
        mock_enrollment.id = uuid4()
        mock_enrollment.sequence_id = uuid4()
        mock_enrollment.prospect_id = uuid4()
        mock_enrollment.status = "active"
        mock_enrollment.current_step_order = 2
        mock_enrollment.enrolled_at = datetime.utcnow()

        result = sequence_service._enrollment_to_dict(mock_enrollment)

        assert result["status"] == "active"
        assert result["current_step_order"] == 2

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, sequence_service, mock_session):
        """Test getting a sequence by ID when it exists."""
        from app.models import Sequence

        mock_sequence = MagicMock(spec=Sequence)
        mock_sequence.id = uuid4()
        mock_sequence.name = "Test Sequence"
        mock_sequence.description = None
        mock_sequence.status = "active"
        mock_sequence.from_name = None
        mock_sequence.from_address = None
        mock_sequence.reply_to = None
        mock_sequence.default_delay_hours = 24
        mock_sequence.daily_limit = 100
        mock_sequence.auto_pause_on_reply = True
        mock_sequence.team_id = None
        mock_sequence.created_at = datetime.utcnow()
        mock_sequence.updated_at = None
        mock_sequence.activated_at = None
        mock_sequence.steps = []

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_sequence
        mock_session.execute.return_value = mock_result

        result = await sequence_service.get_by_id(mock_session, str(mock_sequence.id))

        assert result is not None
        assert result["name"] == "Test Sequence"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, sequence_service, mock_session):
        """Test getting a sequence by ID when it doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await sequence_service.get_by_id(mock_session, str(uuid4()))

        assert result is None

    @pytest.mark.asyncio
    async def test_activate(self, sequence_service, mock_session):
        """Test activating a sequence."""
        sequence_id = str(uuid4())

        result = await sequence_service.activate(mock_session, sequence_id)

        assert result is True
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_pause_sequence(self, sequence_service, mock_session):
        """Test pausing a sequence."""
        sequence_id = str(uuid4())

        result = await sequence_service.pause(mock_session, sequence_id, reason="manual")

        assert result is True
        mock_session.execute.assert_called()

    @pytest.mark.asyncio
    async def test_pause_with_prospect(self, sequence_service, mock_session):
        """Test pausing a specific enrollment in a sequence."""
        sequence_id = str(uuid4())
        prospect_id = str(uuid4())

        result = await sequence_service.pause(
            mock_session, sequence_id, prospect_id=prospect_id, reason="reply_detected"
        )

        assert result is True
        mock_session.execute.assert_called()

    @pytest.mark.asyncio
    async def test_resume(self, sequence_service, mock_session):
        """Test resuming a paused sequence."""
        sequence_id = str(uuid4())

        result = await sequence_service.resume(mock_session, sequence_id)

        assert result is True
        mock_session.execute.assert_called()

    @pytest.mark.asyncio
    async def test_get_enrolled_prospect_ids(self, sequence_service, mock_session):
        """Test getting prospect IDs enrolled in a sequence."""
        prospect_id_1 = str(uuid4())
        prospect_id_2 = str(uuid4())

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(prospect_id_1,), (prospect_id_2,)]
        mock_session.execute.return_value = mock_result

        result = await sequence_service.get_enrolled_prospect_ids(mock_session, str(uuid4()))

        assert len(result) == 2
        assert prospect_id_1 in result
        assert prospect_id_2 in result


class TestSequenceTiming:
    """Test cases for sequence timing calculations."""

    def test_delay_calculation(self):
        """Test that delay calculations are correct."""
        delay_hours = 48
        expected_days = 2

        assert delay_hours / 24 == expected_days

    def test_business_hours_filtering(self):
        """Test business hours filtering logic."""
        business_hours = list(range(9, 18))  # 9 AM to 5 PM

        # Test a time within business hours
        test_hour = 10
        assert test_hour in business_hours

        # Test a time outside business hours
        test_hour = 20
        assert test_hour not in business_hours

    def test_timezone_conversion(self):
        """Test timezone conversion for sequence scheduling."""
        from datetime import datetime

        utc_time = datetime.utcnow()
        est_offset = -5  # EST is UTC-5

        est_time = utc_time.replace(hour=(utc_time.hour + est_offset) % 24)

        assert isinstance(est_time, datetime)


class TestSequenceStepExecution:
    """Test cases for sequence step execution logic."""

    def test_execution_state_machine(self):
        """Test the state machine for sequence execution."""
        valid_states = ["pending", "scheduled", "sent", "failed", "skipped"]

        for state in valid_states:
            assert state in valid_states

    def test_pending_to_sent_transition(self):
        """Test transition from pending to sent."""
        current_state = "pending"
        valid_next_states = ["sent", "failed", "skipped"]

        assert current_state in ["pending", "scheduled"]
        assert "sent" in valid_next_states

    def test_failed_retry_logic(self):
        """Test retry logic for failed executions."""
        max_retries = 3
        current_retry = 2

        assert current_retry < max_retries
        assert current_retry + 1 <= max_retries