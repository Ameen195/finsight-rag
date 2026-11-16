"""Groq wrapper: client-side tokens-per-minute limiter + retry on 429/5xx."""

import logging
import threading
import time
from collections import deque

import groq
from groq import Groq
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from finsight.config import get_settings

log = logging.getLogger(__name__)


class TPMLimiter:
    """Sliding 60 s window; `acquire(n)` blocks until n tokens fit in the budget."""

    def __init__(self, limit: int, window: float = 60.0) -> None:
        self.limit, self.window = limit, window
        self._events: deque[tuple[float, int]] = deque()
        self._lock = threading.Lock()

    def acquire(self, tokens: int) -> None:
        """Block until `tokens` can be spent, then record them."""
        tokens = min(tokens, self.limit)  # an oversized request must still be able to run
        while True:
            with self._lock:
                now = time.monotonic()
                while self._events and now - self._events[0][0] >= self.window:
                    self._events.popleft()
                if sum(t for _, t in self._events) + tokens <= self.limit:
                    self._events.append((now, tokens))
                    return
                wait = self.window - (now - self._events[0][0])
            log.info("TPM budget full, sleeping %.1fs", wait)
            time.sleep(wait)


def _retryable(exc: BaseException) -> bool:
    """Retry on 429, connection errors and 5xx; fail fast on other 4xx."""
    return isinstance(exc, groq.RateLimitError | groq.APIConnectionError) or (
        isinstance(exc, groq.APIStatusError) and exc.status_code >= 500
    )


_limiter: TPMLimiter | None = None
_client: Groq | None = None


@retry(
    retry=retry_if_exception(_retryable),
    wait=wait_exponential(multiplier=2, max=30),
    stop=stop_after_attempt(5),
    reraise=True,
)
def complete(
    messages: list[dict[str, str]],
    model: str,
    json_mode: bool = False,
    max_tokens: int = 1024,
) -> str:
    """Run a chat completion and return the text. Rate-limited and retried."""
    global _limiter, _client
    s = get_settings()
    _limiter = _limiter or TPMLimiter(s.groq_tpm_limit)
    _client = _client or Groq(api_key=s.groq_api_key)
    # ~4 chars/token estimate of the prompt, plus the max completion we allow
    _limiter.acquire(sum(len(m["content"]) for m in messages) // 4 + max_tokens)
    kwargs: dict = {"response_format": {"type": "json_object"}} if json_mode else {}
    if model.startswith("openai/gpt-oss"):
        # reasoning tokens count against max_tokens; low effort keeps small budgets usable
        kwargs["reasoning_effort"] = "low"
    resp = _client.chat.completions.create(
        model=model, messages=messages, max_tokens=max_tokens, **kwargs
    )
    return resp.choices[0].message.content or ""
