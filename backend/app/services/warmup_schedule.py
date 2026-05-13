"""
Warmup Schedule — authoritative send limits for IP/domain warmup.

warmup_day is 0-based (day 0 = first day of existence).
Graduation occurs at WARMUP_GRADUATION_DAY — warmup_enabled is disabled
and the domain moves to its configured daily_send_limit.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

WARMUP_GRADUATION_DAY = 60  # warmup_day >= 60 → graduated

# ---------------------------------------------------------------------------
# Schedule table — (day_start inclusive, day_end inclusive or None, daily, hourly)
# All values are 0-based warmup_day.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WarmupSlot:
    day_start: int
    day_end: Optional[int]   # None = open-ended (already graduated)
    daily_limit: int
    hourly_limit: int


_SCHEDULE: list[WarmupSlot] = [
    WarmupSlot(0,  2,  15,    5),   # days 1-3
    WarmupSlot(3,  6,  50,   10),   # days 4-7
    WarmupSlot(7,  13, 150,  20),   # days 8-14
    WarmupSlot(14, 20, 500,  50),   # days 15-21
    WarmupSlot(21, 29, 1_000, 100), # days 22-30
    WarmupSlot(30, 44, 3_000, 300), # days 31-45
    WarmupSlot(45, 59, 8_000, 800), # days 46-60
    WarmupSlot(60, None, 15_000, 1_500),  # graduated
]


def get_warmup_slot(warmup_day: int) -> WarmupSlot:
    """Return the warmup slot for a given 0-based warmup_day."""
    day = max(0, warmup_day)
    for slot in _SCHEDULE:
        if slot.day_end is None or day <= slot.day_end:
            return slot
    return _SCHEDULE[-1]


def get_daily_limit(warmup_day: int) -> int:
    """Daily send cap for the given warmup day."""
    return get_warmup_slot(warmup_day).daily_limit


def get_hourly_limit(warmup_day: int) -> int:
    """Hourly send cap for the given warmup day."""
    return get_warmup_slot(warmup_day).hourly_limit


def is_graduated(warmup_day: int) -> bool:
    """True once warmup is complete and the domain can send at full rate."""
    return warmup_day >= WARMUP_GRADUATION_DAY


def effective_daily_limit(domain: dict) -> int:
    """
    Return the send cap that must be enforced for this domain today.

    - If warmup is active and not yet graduated → warmup schedule cap.
    - Otherwise → domain's configured daily_send_limit.
    """
    if domain.get("warmup_enabled") and not is_graduated(domain.get("warmup_day", 0)):
        return get_daily_limit(domain["warmup_day"])
    return domain.get("daily_send_limit", 50)


def warmup_progress_pct(warmup_day: int) -> float:
    """Return 0–100 warmup progress percentage."""
    return min(100.0, round(warmup_day / WARMUP_GRADUATION_DAY * 100, 1))
