from pydantic import BaseModel

from rfp_intel.agents.llm import LLMError, ScriptedLLM, Usage
from rfp_intel.agents.ratelimit import RateLimitedLLM


class Out(BaseModel):
    text: str


class Clock:
    """A fake clock whose sleep advances time, so pacing is tested without waiting."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _paced(limit: int, clock: Clock) -> RateLimitedLLM:
    inner = ScriptedLLM({"Out": lambda system, user: Out(text="ok")})
    return RateLimitedLLM(inner, tokens_per_minute=limit, clock=clock, sleep=clock.sleep)


def _call(llm: RateLimitedLLM, chars: int = 400, max_tokens: int = 100) -> Usage:
    _, usage = llm.structured(
        system="s", user="x" * chars, schema=Out, model="m", max_tokens=max_tokens
    )
    return usage


def test_calls_within_the_quota_do_not_wait() -> None:
    clock = Clock()
    llm = _paced(10_000, clock)
    for _ in range(5):
        _call(llm)
    assert clock.sleeps == []


def test_a_call_that_would_overflow_the_window_waits_for_it() -> None:
    clock = Clock()
    llm = _paced(1_000, clock)
    _call(llm, chars=2_000, max_tokens=300)  # reserves ~800, settles to the real usage
    _call(llm, chars=2_000, max_tokens=300)
    assert clock.sleeps and clock.now >= 60.0


def test_a_single_call_larger_than_the_quota_fails_with_advice() -> None:
    llm = _paced(500, Clock())
    try:
        _call(llm, chars=4_000)
    except LLMError as exc:
        assert "RFP_LLM_MAX_PROMPT_TOKENS" in str(exc)
    else:
        raise AssertionError("expected LLMError")
