"""OpenAI and Anthropic implementations of the provider protocol."""

import json
import time

import anthropic
import openai

from app.ai.providers.base import ChatMessage, LLMResult, ProviderError, with_retries
from app.core.config import settings

_OPENAI_RETRYABLE = (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError,
                     openai.InternalServerError)
_ANTHROPIC_RETRYABLE = (anthropic.RateLimitError, anthropic.APITimeoutError, anthropic.APIConnectionError,
                        anthropic.InternalServerError)


class OpenAIProvider:
    name = "openai"
    is_mock = False

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise ProviderError("OPENAI_API_KEY is not configured")
        self.client = openai.OpenAI(api_key=settings.openai_api_key, timeout=settings.ai_request_timeout_seconds,
                                    max_retries=0)
        self.default_model = settings.openai_model

    def complete(self, *, system, messages: list[ChatMessage], model=None, temperature=0.2, max_tokens=800,
                 mock=None) -> LLMResult:
        model = model or self.default_model

        def call() -> LLMResult:
            start = time.perf_counter()
            resp = self.client.chat.completions.create(
                model=model, temperature=temperature, max_tokens=max_tokens,
                messages=[{"role": "system", "content": system}, *[{"role": m.role, "content": m.content} for m in messages]],
            )
            u = resp.usage
            return LLMResult(text=resp.choices[0].message.content or "", provider=self.name, model=model,
                             input_tokens=u.prompt_tokens if u else 0, output_tokens=u.completion_tokens if u else 0,
                             latency_ms=int((time.perf_counter() - start) * 1000))

        try:
            return with_retries(call, retries=settings.ai_max_retries, provider=self.name, retryable=_OPENAI_RETRYABLE)
        except openai.OpenAIError as exc:
            raise ProviderError(f"OpenAI error: {exc}") from exc

    def structured(self, *, system, prompt, schema, model=None, temperature=0.2, max_tokens=2500, mock=None) -> LLMResult:
        model = model or self.default_model

        def call() -> LLMResult:
            start = time.perf_counter()
            resp = self.client.chat.completions.parse(
                model=model, temperature=temperature, max_tokens=max_tokens, response_format=schema,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            )
            msg = resp.choices[0].message
            if msg.parsed is None:
                raise ProviderError(f"OpenAI returned no structured output (refusal={msg.refusal!r})")
            u = resp.usage
            return LLMResult(text=msg.content or "", provider=self.name, model=model, parsed=msg.parsed,
                             input_tokens=u.prompt_tokens if u else 0, output_tokens=u.completion_tokens if u else 0,
                             latency_ms=int((time.perf_counter() - start) * 1000))

        try:
            return with_retries(call, retries=settings.ai_max_retries, provider=self.name, retryable=_OPENAI_RETRYABLE)
        except openai.OpenAIError as exc:
            raise ProviderError(f"OpenAI error: {exc}") from exc


class AnthropicProvider:
    name = "anthropic"
    is_mock = False

    def __init__(self) -> None:
        if not settings.anthropic_api_key:
            raise ProviderError("ANTHROPIC_API_KEY is not configured")
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key,
                                          timeout=settings.ai_request_timeout_seconds, max_retries=0)
        self.default_model = settings.anthropic_model

    def complete(self, *, system, messages: list[ChatMessage], model=None, temperature=0.2, max_tokens=800,
                 mock=None) -> LLMResult:
        model = model or self.default_model

        def call() -> LLMResult:
            start = time.perf_counter()
            resp = self.client.messages.create(
                model=model, system=system, temperature=temperature, max_tokens=max_tokens,
                messages=[{"role": m.role, "content": m.content} for m in messages],
            )
            text = "".join(b.text for b in resp.content if b.type == "text")
            return LLMResult(text=text, provider=self.name, model=model, input_tokens=resp.usage.input_tokens,
                             output_tokens=resp.usage.output_tokens, latency_ms=int((time.perf_counter() - start) * 1000))

        try:
            return with_retries(call, retries=settings.ai_max_retries, provider=self.name,
                                retryable=_ANTHROPIC_RETRYABLE)
        except anthropic.AnthropicError as exc:
            raise ProviderError(f"Anthropic error: {exc}") from exc

    def structured(self, *, system, prompt, schema, model=None, temperature=0.2, max_tokens=2500, mock=None) -> LLMResult:
        """Structured output via a forced tool call whose input schema is the Pydantic model's JSON schema."""
        model = model or self.default_model
        tool = {"name": "submit_result", "description": f"Submit the {schema.__name__} result.",
                "input_schema": schema.model_json_schema()}

        def call() -> LLMResult:
            start = time.perf_counter()
            resp = self.client.messages.create(
                model=model, system=system, temperature=temperature, max_tokens=max_tokens, tools=[tool],
                tool_choice={"type": "tool", "name": "submit_result"},
                messages=[{"role": "user", "content": prompt}],
            )
            block = next((b for b in resp.content if b.type == "tool_use"), None)
            if block is None:
                raise ProviderError("Anthropic returned no tool_use block for structured output")
            parsed = schema.model_validate(block.input)
            return LLMResult(text=json.dumps(block.input), provider=self.name, model=model, parsed=parsed,
                             input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens,
                             latency_ms=int((time.perf_counter() - start) * 1000))

        try:
            return with_retries(call, retries=settings.ai_max_retries, provider=self.name,
                                retryable=_ANTHROPIC_RETRYABLE)
        except anthropic.AnthropicError as exc:
            raise ProviderError(f"Anthropic error: {exc}") from exc


class OpenAIEmbeddingProvider:
    name = "openai"
    is_mock = False

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise ProviderError("OPENAI_API_KEY is not configured for embeddings")
        self.client = openai.OpenAI(api_key=settings.openai_api_key, timeout=settings.ai_request_timeout_seconds)
        self.model = settings.openai_embedding_model

    def embed(self, texts: list[str]) -> tuple[list[list[float]], int]:
        vectors: list[list[float]] = []
        tokens = 0
        for i in range(0, len(texts), 96):
            batch = texts[i: i + 96]
            resp = self.client.embeddings.create(model=self.model, input=batch,
                                                 dimensions=settings.embedding_dimensions)
            vectors.extend(d.embedding for d in resp.data)
            tokens += resp.usage.total_tokens
        return vectors, tokens
