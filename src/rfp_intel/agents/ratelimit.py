"""Client-side token pacing for providers with a tokens-per-minute quota.

Free tiers (Groq's is 8,000 tokens per minute per model) reject a burst of large prompts. This
wrapper keeps a 60-second window of tokens spent per model and waits before a call that would
overflow it. It wraps any `LLM`, so providers stay unaware of quotas, and it is thread-safe,
so parallel graph branches share one budget.
"""

import threading
import time
from collections import deque
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel

from rfp_intel.agents.llm import LLM, LLMError, Usage, estimate_tokens

T = TypeVar("T", bound=BaseModel)
WINDOW_S = 60.0


class RateLimitedLLM:
    def __init__(
        self,
        inner: LLM,
        *,
        tokens_per_minute: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.inner = inner
        self.limit = tokens_per_minute
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._spent: dict[str, deque[tuple[float, int]]] = {}

    @property
    def mode(self) -> object:
        """Expose the wrapped client's structured-output mode, for `rfp llm-check`."""
        return getattr(self.inner, "mode", None)

    def _used(self, model: str, now: float) -> int:
        window = self._spent.setdefault(model, deque())
        while window and now - window[0][0] >= WINDOW_S:
            window.popleft()
        return sum(tokens for _, tokens in window)

    def _reserve(self, model: str, tokens: int) -> float:
        """Block until `tokens` fit in the model's window; return the reservation time."""
        if tokens > self.limit:
            raise LLMError(
                f"one call needs about {tokens} tokens but the quota is {self.limit} per minute; "
                "lower RFP_LLM_MAX_PROMPT_TOKENS or RFP_LLM_MAX_OUTPUT_TOKENS"
            )
        while True:
            with self._lock:
                now = self._clock()
                if self._used(model, now) + tokens <= self.limit:
                    self._spent[model].append((now, tokens))
                    return now
                oldest = self._spent[model][0][0]
            self._sleep(max(0.5, WINDOW_S - (now - oldest)))

    def _settle(self, model: str, at: float, reserved: int, actual: int) -> None:
        """Replace the reservation with the tokens the call really used."""
        with self._lock:
            window = self._spent.get(model, deque())
            for i, (when, tokens) in enumerate(window):
                if when == at and tokens == reserved:
                    window[i] = (when, actual)
                    break

    def structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        model: str,
        effort: str = "medium",
        max_tokens: int = 8000,
    ) -> tuple[T, Usage]:
        reserved = estimate_tokens(system) + estimate_tokens(user) + max_tokens
        at = self._reserve(model, reserved)
        try:
            out, usage = self.inner.structured(
                system=system, user=user, schema=schema, model=model, effort=effort,
                max_tokens=max_tokens,
            )  # fmt: skip
        except Exception:
            self._settle(model, at, reserved, estimate_tokens(system) + estimate_tokens(user))
            raise
        actual = usage.input_tokens + usage.cache_read_tokens + usage.output_tokens
        self._settle(model, at, reserved, actual or reserved)
        return out, usage
