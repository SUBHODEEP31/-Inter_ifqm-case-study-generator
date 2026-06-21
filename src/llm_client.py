"""Unified Groq inference layer for the IFQM Case Study Generator.

Responsibilities:
  * Dual-model routing - PRIMARY (llama-3.3-70b-versatile) for reasoning/generation,
    UTILITY (llama-3.1-8b-instant) for cheap high-volume tasks.
  * Exponential-backoff retries on transient Groq errors via tenacity.
  * Plain-text completion (`complete`) and Pydantic-structured output (`structured`)
    using instructor.
  * Approximate token counting via tiktoken.
  * `test_connection` smoke check used by Stage 1.

Groq is the only inference provider in v1 (no Ollama fallback). A missing
GROQ_API_KEY raises a clear error rather than failing deep in a call.
"""
from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Type, TypeVar

import groq
import instructor
import tiktoken
from dotenv import load_dotenv
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.logger import get_logger

log = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")

T = TypeVar("T", bound=BaseModel)

# Transient errors worth retrying. Auth/validation errors are NOT retried.
_RETRYABLE = (
    groq.APIConnectionError,
    groq.APITimeoutError,
    groq.InternalServerError,
    groq.RateLimitError,
)

_retry_policy = retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(_RETRYABLE),
)


class ModelRole(str, Enum):
    """Logical model roles mapped to concrete Groq model IDs via env."""

    PRIMARY = "primary"
    UTILITY = "utility"


class LLMClientError(RuntimeError):
    """Raised for configuration problems (e.g. missing API key)."""


class LLMClient:
    """Thin, retry-wrapped wrapper around the Groq + instructor clients."""

    def __init__(self) -> None:
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            raise LLMClientError(
                "GROQ_API_KEY is not set. Add it to D:\\ifqm-case-generator\\.env "
                "(free key at https://console.groq.com)."
            )

        self.primary_model = os.getenv("PRIMARY_MODEL", "llama-3.3-70b-versatile")
        self.utility_model = os.getenv("UTILITY_MODEL", "llama-3.1-8b-instant")

        self._client = groq.Groq(api_key=api_key)
        # instructor wraps the same client for schema-validated structured output.
        self._structured = instructor.from_groq(self._client)
        # tiktoken has no Llama vocab; cl100k_base is a close-enough approximation.
        self._encoder = tiktoken.get_encoding("cl100k_base")
        log.info(
            f"LLMClient ready (primary={self.primary_model}, utility={self.utility_model})"
        )

    def _model_for(self, role: ModelRole) -> str:
        return self.primary_model if role == ModelRole.PRIMARY else self.utility_model

    def count_tokens(self, text: str) -> int:
        """Approximate token count for budgeting/truncation."""
        return len(self._encoder.encode(text or ""))

    @_retry_policy
    def complete(
        self,
        prompt: str,
        *,
        role: ModelRole = ModelRole.PRIMARY,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> str:
        """Return a plain-text completion."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        model = self._model_for(role)
        log.debug(f"complete() role={role.value} model={model} tokens_in~{self.count_tokens(prompt)}")
        resp = self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    @_retry_policy
    def structured(
        self,
        prompt: str,
        response_model: Type[T],
        *,
        role: ModelRole = ModelRole.PRIMARY,
        system: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        max_retries: int = 3,
    ) -> T:
        """Return an instance of `response_model`, validated by instructor."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        model = self._model_for(role)
        log.debug(f"structured() role={role.value} model={model} -> {response_model.__name__}")
        return self._structured.chat.completions.create(
            model=model,
            messages=messages,
            response_model=response_model,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=max_retries,
        )

    def test_connection(self) -> dict[str, object]:
        """Ping both models with a trivial prompt. Returns a status dict."""
        result: dict[str, object] = {"ok": False, "primary": None, "utility": None, "error": None}
        try:
            primary = self.complete("Reply with the single word: OK", role=ModelRole.PRIMARY, max_tokens=5)
            utility = self.complete("Reply with the single word: OK", role=ModelRole.UTILITY, max_tokens=5)
            result["primary"] = primary
            result["utility"] = utility
            result["ok"] = bool(primary) and bool(utility)
            log.info(f"test_connection PASS (primary={primary!r}, utility={utility!r})")
        except Exception as exc:  # surfaced to caller / UI
            result["error"] = f"{type(exc).__name__}: {exc}"
            log.error(f"test_connection FAIL: {result['error']}")
        return result


_SINGLETON: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Lazily build and cache a single LLMClient instance."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = LLMClient()
    return _SINGLETON
