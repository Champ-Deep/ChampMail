"""Ramp-governor — closed-loop warmup/throttle keyed to live reputation metrics.

ChampMail's 8-step warmup is a static schedule. The governor turns it into a
feedback loop: it reads each domain's recent bounce / complaint / seed-placement
rates and decides whether to ADVANCE the ramp, HOLD, THROTTLE, or PAUSE the
domain — using the thresholds verified from Gmail/Yahoo/Microsoft sender docs:

  - complaint rate: target < 0.1%, hard stop at >= 0.3%
  - hard bounce:    hold at >= 2%, stop at >= 4%
  - seed inbox placement: advance only if >= 85%
  - cold ceiling:   50-100 emails / mailbox / day

The decision function is pure (no DB) so it is unit-tested offline; the Celery
task wraps it with metric reads + cap writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# 8-step warmup ramp (emails/day) — matches ChampMail's existing progression.
WARMUP_CAPS = [10, 25, 50, 100, 200, 500, 750, 1000]

COMPLAINT_PAUSE = 0.003   # 0.3%
COMPLAINT_HOLD = 0.001    # 0.1%
BOUNCE_PAUSE = 0.04       # 4%
BOUNCE_HOLD = 0.02        # 2%
SEED_ADVANCE_MIN = 0.85   # 85%


class RampAction(str, Enum):
    ADVANCE = "advance"     # bump to the next warmup step
    HOLD = "hold"           # stay at current cap
    THROTTLE = "throttle"   # cut the cap (reputation slipping)
    PAUSE = "pause"         # stop sending on this domain


@dataclass
class DomainMetrics:
    bounce_rate: float          # hard bounces / sent (0..1)
    complaint_rate: float       # complaints / sent (0..1)
    seed_placement: float       # inbox-placement fraction (0..1); 1.0 if unknown
    warmup_day: int             # current warmup step index (0-based)
    sent_today: int = 0
    sample_size: int = 0        # messages the rates are computed over
    sending_ip: str | None = None  # reputation is owned PER SENDING IP (plan H);
    #                                metrics should be fed per (domain, ip)


@dataclass
class RampDecision:
    action: RampAction
    new_cap: int
    reason: str


def evaluate_domain(m: DomainMetrics) -> RampDecision:
    step = max(0, min(m.warmup_day, len(WARMUP_CAPS) - 1))
    cap = WARMUP_CAPS[step]

    # Hard stops first — reputation-protecting, override everything.
    if m.complaint_rate >= COMPLAINT_PAUSE:
        return RampDecision(RampAction.PAUSE, 0,
                            f"complaint rate {m.complaint_rate:.3%} >= 0.3% — pause")
    if m.bounce_rate >= BOUNCE_PAUSE:
        return RampDecision(RampAction.PAUSE, 0,
                            f"hard bounce {m.bounce_rate:.2%} >= 4% — pause")

    # Throttle band — slipping but not critical: cut to the previous step's cap.
    if m.complaint_rate >= COMPLAINT_HOLD or m.bounce_rate >= BOUNCE_HOLD:
        lower = WARMUP_CAPS[max(0, step - 1)]
        return RampDecision(RampAction.THROTTLE, lower,
                            f"bounce {m.bounce_rate:.2%} / complaint {m.complaint_rate:.3%} "
                            f"in caution band — throttle to {lower}/day")

    # Healthy: advance only with enough evidence + good seed placement.
    enough_evidence = m.sample_size >= 50
    if (enough_evidence and m.seed_placement >= SEED_ADVANCE_MIN
            and step < len(WARMUP_CAPS) - 1):
        return RampDecision(RampAction.ADVANCE, WARMUP_CAPS[step + 1],
                            f"healthy (seed {m.seed_placement:.0%}) — advance to step {step + 1}")

    return RampDecision(RampAction.HOLD, cap,
                        "healthy but holding (insufficient evidence or seed < 85% or at max)")


def next_warmup_day(action: RampAction, warmup_day: int) -> int:
    """Warmup step index after applying an action.

    THROTTLE steps the index DOWN (plan H): a throttle that only cut the cap but
    left warmup_day untouched would let the next ADVANCE jump back to the ORIGINAL
    step, undoing the throttle. Stepping the index down means a later ADVANCE
    resumes from the throttled step. PAUSE/HOLD leave the index where it is.
    """
    last = len(WARMUP_CAPS) - 1
    if action == RampAction.ADVANCE:
        return min(warmup_day + 1, last)
    if action == RampAction.THROTTLE:
        return max(0, warmup_day - 1)
    return warmup_day


if __name__ == "__main__":  # pure self-check (no DB)
    # THROTTLE must decrement so ADVANCE resumes from the throttled step.
    assert next_warmup_day(RampAction.THROTTLE, 3) == 2
    assert next_warmup_day(RampAction.THROTTLE, 0) == 0          # floor
    assert next_warmup_day(RampAction.ADVANCE, 2) == 3
    assert next_warmup_day(RampAction.ADVANCE, len(WARMUP_CAPS) - 1) == len(WARMUP_CAPS) - 1
    assert next_warmup_day(RampAction.HOLD, 4) == 4
    # caution band → THROTTLE to the lower cap.
    d = evaluate_domain(DomainMetrics(bounce_rate=0.025, complaint_rate=0.0,
                                      seed_placement=0.9, warmup_day=3, sample_size=100))
    assert d.action == RampAction.THROTTLE and d.new_cap == WARMUP_CAPS[2], d
    # 4% bounce → PAUSE.
    p = evaluate_domain(DomainMetrics(bounce_rate=0.04, complaint_rate=0.0,
                                      seed_placement=1.0, warmup_day=2, sample_size=100))
    assert p.action == RampAction.PAUSE, p
    print("ramp_governor self-check OK")
