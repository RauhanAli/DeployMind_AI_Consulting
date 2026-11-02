"""Provider abstraction: application code depends on LLMProvider, never on a vendor SDK directly."""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, TypeVar

from pydantic import BaseModel

log = logging.getLogger("deploymind.ai")

T = TypeVar("T", bound=BaseModel)


class ProviderError(Exception):
    """Raised when a provider call fails after retries."""


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    is_mock: bool = False
    parsed: BaseModel | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class ChatMessage:
    role: str  # user | assistant
    content: str


class LLMProvider(Protocol):
    name: str
    is_mock: bool

    def complete(self, *, system: str, messages: list[ChatMessage], model: str | None = None,
                 temperature: float = 0.2, max_tokens: int = 800,
                 mock: Callable[[], str] | None = None) -> LLMResult: ...

    def structured(self, *, system: str, prompt: str, schema: type[T], model: str | None = None,
                   temperature: float = 0.2, max_tokens: int = 2500,
                   mock: Callable[[], T] | None = None) -> LLMResult: ...


class EmbeddingProvider(Protocol):
    name: str
    model: str
    is_mock: bool

    def embed(self, texts: list[str]) -> tuple[list[list[float]], int]: ...


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def with_retries(fn: Callable[[], LLMResult], *, retries: int, provider: str, retryable: tuple[type[Exception], ...]):
    delay = 1.0
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except retryable as exc:  # transient errors: rate limits, timeouts, 5xx
            last = exc
            log.warning("llm_retry", extra={"provider": provider, "attempt": attempt + 1, "error": str(exc)[:300]})
            if attempt < retries:
                time.sleep(delay)
                delay *= 2
    raise ProviderError(f"{provider} request failed after {retries + 1} attempts: {last}") from last
