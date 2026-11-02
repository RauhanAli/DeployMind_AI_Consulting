"""Deterministic mock providers for demo mode (no paid API keys).

The mock chat provider never invents content: each caller supplies a deterministic builder (`mock=`)
that derives the output from the agent's inputs (templates, extractive answers). Outputs are always
flagged `is_mock=True` and the UI shows a "Mock AI mode" banner.

The mock embedding provider is a feature-hashing bag-of-words model (unigrams + bigrams, signed hashing,
L2-normalised). It is genuinely useful for lexical-semantic retrieval in demos and fully reproducible.
"""

import hashlib
import math
import re
import time

from app.ai.providers.base import ChatMessage, LLMResult, estimate_tokens
from app.core.config import settings

_WORD = re.compile(r"[a-z0-9]+")
STOPWORDS = set(
    "a an the and or of to in on for with by is are was were be been it its this that these those as at from "
    "what which who whom how when where why do does did can could should would will shall may might our your "
    "their we you they i me my us them he she his her not no yes if then than so such into about over".split()
)


def tokenize(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in STOPWORDS]


def _stem(w: str) -> str:
    for suf in ("ing", "ies", "es", "ed", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


class MockLLMProvider:
    name = "mock"
    is_mock = True
    default_model = "mock-deterministic-1"

    def complete(self, *, system, messages: list[ChatMessage], model=None, temperature=0.2, max_tokens=800,
                 mock=None) -> LLMResult:
        start = time.perf_counter()
        if mock is None:
            raise ValueError("Mock provider requires a deterministic builder for this call")
        text = mock()
        prompt = system + "\n".join(m.content for m in messages)
        return LLMResult(text=text, provider=self.name, model=model or self.default_model,
                         input_tokens=estimate_tokens(prompt), output_tokens=estimate_tokens(text),
                         latency_ms=int((time.perf_counter() - start) * 1000), is_mock=True)

    def structured(self, *, system, prompt, schema, model=None, temperature=0.2, max_tokens=2500,
                   mock=None) -> LLMResult:
        start = time.perf_counter()
        if mock is None:
            raise ValueError("Mock provider requires a deterministic builder for this call")
        out = mock()
        parsed = schema.model_validate(out if isinstance(out, dict) else out.model_dump())
        text = parsed.model_dump_json()
        return LLMResult(text=text, provider=self.name, model=model or self.default_model,
                         input_tokens=estimate_tokens(system + prompt), output_tokens=estimate_tokens(text),
                         latency_ms=int((time.perf_counter() - start) * 1000), is_mock=True, parsed=parsed)


class HashingEmbeddingProvider:
    name = "mock"
    model = "hashing-bow-v1"
    is_mock = True

    def __init__(self, dims: int | None = None):
        self.dims = dims or settings.embedding_dimensions

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dims
        toks = [_stem(t) for t in tokenize(text)]
        feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False)]
        for f in feats:
            h = hashlib.blake2b(f.encode(), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "little") % self.dims
            sign = 1.0 if h[4] & 1 else -1.0
            v[idx] += sign * (0.5 if "_" in f else 1.0)
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed(self, texts: list[str]) -> tuple[list[list[float]], int]:
        return [self._vec(t) for t in texts], sum(estimate_tokens(t) for t in texts)
