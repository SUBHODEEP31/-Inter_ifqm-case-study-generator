"""Dual-engine inference layer for the IFQM Case Study Generator.

Asymmetric routing to respect Groq's tokens-per-minute ceiling:
  * Role.BULK      -> Gemini 1.5 Flash : high-volume reading, chunk cleaning,
                       Stage-3 contextual enrichment (huge free context window).
  * Role.REASONING -> Groq Llama 3.3 70B : JSON brief extraction, narrative
                       chapters, adversarial critic/judge.
  * Role.UTILITY   -> Groq Llama 3.1 8B : fast small tasks; also the Groq-side
                       fallback when Gemini is unavailable.

Both providers are wrapped in a tenacity retry that intercepts HTTP 429 and,
when the provider supplies a `retry-after` (or `retry_delay`), waits exactly
that long before resubmitting; otherwise it backs off exponentially.

If only one provider's key is configured, routing gracefully falls back to it.
If neither is configured, construction raises LLMClientError.
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
from tenacity import retry, retry_if_exception_type, stop_after_attempt

from src.logger import get_logger

log = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")

T = TypeVar("T", bound=BaseModel)

# Optional Gemini SDK - import guarded so the module loads even if absent.
try:
    import google.generativeai as genai
    from google.api_core import exceptions as g_exc

    _GEMINI_SDK = True
except Exception:  # pragma: no cover
    genai = None
    g_exc = None
    _GEMINI_SDK = False


class Engine(str, Enum):
    GROQ = "groq"
    GEMINI = "gemini"


class Role(str, Enum):
    REASONING = "reasoning"  # Groq 70B
    BULK = "bulk"            # Gemini Flash
    UTILITY = "utility"      # Groq 8B


class LLMClientError(RuntimeError):
    """Raised for configuration problems (e.g. no provider key)."""


# --- retry plumbing -------------------------------------------------------- #
_GROQ_RETRYABLE = (
    groq.APIConnectionError,
    groq.APITimeoutError,
    groq.InternalServerError,
    groq.RateLimitError,
)
_GEMINI_RETRYABLE = (
    (g_exc.ResourceExhausted, g_exc.ServiceUnavailable, g_exc.DeadlineExceeded)
    if g_exc
    else tuple()
)
_RETRYABLE = _GROQ_RETRYABLE + _GEMINI_RETRYABLE


def _retry_after_seconds(exc) -> float | None:
    """Extract a server-suggested wait (seconds) from a rate-limit error."""
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            ra = resp.headers.get("retry-after")
            if ra:
                return float(ra)
        except Exception:
            pass
    delay = getattr(exc, "retry_delay", None)  # Gemini ResourceExhausted
    secs = getattr(delay, "seconds", None)
    if secs:
        return float(secs)
    return None


def _wait(retry_state) -> float:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if exc is not None:
        ra = _retry_after_seconds(exc)
        if ra is not None:
            log.warning(f"Rate-limited; honoring retry-after={ra:.1f}s")
            return min(ra, 60.0)
    return min(2.0 ** retry_state.attempt_number, 30.0)


_retry_policy = retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=_wait,
    retry=retry_if_exception_type(_RETRYABLE),
)


class LLMClient:
    """Routes completions to Groq or Gemini and validates structured output."""

    def __init__(self) -> None:
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

        self.primary_model = os.getenv("PRIMARY_MODEL", "llama-3.3-70b-versatile")
        self.utility_model = os.getenv("UTILITY_MODEL", "llama-3.1-8b-instant")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

        self._groq = groq.Groq(api_key=groq_key) if groq_key else None
        self._structured = instructor.from_groq(self._groq) if self._groq else None

        self._gemini_on = False
        if gemini_key and _GEMINI_SDK:
            genai.configure(api_key=gemini_key)
            self._gemini_on = True
        elif gemini_key and not _GEMINI_SDK:
            log.warning("GEMINI_API_KEY set but google-generativeai not importable.")

        if not self._groq and not self._gemini_on:
            raise LLMClientError(
                "No usable LLM provider. Set GROQ_API_KEY and/or GEMINI_API_KEY in "
                "D:\\ifqm-case-generator\\.env."
            )

        self._encoder = tiktoken.get_encoding("cl100k_base")
        log.info(
            f"LLMClient ready (groq={'on' if self._groq else 'off'}, "
            f"gemini={'on' if self._gemini_on else 'off'})"
        )

    # -- routing ----------------------------------------------------------- #
    def _route(self, role: Role) -> tuple[Engine, str]:
        if role == Role.BULK:
            if self._gemini_on:
                return Engine.GEMINI, self.gemini_model
            if self._groq:
                return Engine.GROQ, self.utility_model
        elif role == Role.UTILITY:
            if self._groq:
                return Engine.GROQ, self.utility_model
            if self._gemini_on:
                return Engine.GEMINI, self.gemini_model
        else:  # REASONING
            if self._groq:
                return Engine.GROQ, self.primary_model
            if self._gemini_on:
                return Engine.GEMINI, self.gemini_model
        # exhaustive fallback
        if self._groq:
            return Engine.GROQ, self.primary_model
        return Engine.GEMINI, self.gemini_model

    def count_tokens(self, text: str) -> int:
        return len(self._encoder.encode(text or ""))

    # -- provider calls ---------------------------------------------------- #
    @_retry_policy
    def _groq_complete(self, model: str, messages: list[dict], temperature: float, max_tokens: int) -> str:
        resp = self._groq.chat.completions.create(
            model=model, messages=messages, temperature=temperature, max_tokens=max_tokens
        )
        return (resp.choices[0].message.content or "").strip()

    @_retry_policy
    def _gemini_complete(self, model_name: str, prompt: str, system: str | None, temperature: float, max_tokens: int) -> str:
        model = genai.GenerativeModel(model_name, system_instruction=system or None)
        resp = model.generate_content(
            prompt,
            generation_config={"temperature": temperature, "max_output_tokens": max_tokens},
        )
        try:
            return (resp.text or "").strip()
        except Exception:
            # blocked / no candidates
            return ""

    def complete(
        self,
        prompt: str,
        *,
        role: Role = Role.REASONING,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> str:
        """Plain-text completion, routed by role."""
        engine, model = self._route(role)
        log.debug(f"complete() role={role.value} -> {engine.value}:{model}")
        if engine == Engine.GEMINI:
            return self._gemini_complete(model, prompt, system, temperature, max_tokens)
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self._groq_complete(model, messages, temperature, max_tokens)

    @_retry_policy
    def structured(
        self,
        prompt: str,
        response_model: Type[T],
        *,
        system: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        max_retries: int = 3,
    ) -> T:
        """Schema-validated structured output. Routes to Groq (per spec)."""
        if not self._structured:
            raise LLMClientError(
                "Structured extraction requires GROQ_API_KEY (JSON briefs route to "
                "Groq Llama 3.3 70B)."
            )
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self._structured.chat.completions.create(
            model=self.primary_model,
            messages=messages,
            response_model=response_model,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=max_retries,
        )

    def test_connection(self) -> dict[str, object]:
        """Ping each configured engine. ok=True iff every configured engine replies."""
        result: dict[str, object] = {"ok": False, "groq": None, "gemini": None, "error": None}
        errors: list[str] = []

        if self._groq:
            try:
                result["groq"] = self.complete(
                    "Reply with the single word: OK", role=Role.REASONING, max_tokens=5
                )
            except Exception as exc:
                errors.append(f"groq:{type(exc).__name__}:{exc}")
        if self._gemini_on:
            try:
                result["gemini"] = self.complete(
                    "Reply with the single word: OK", role=Role.BULK, max_tokens=5
                )
            except Exception as exc:
                errors.append(f"gemini:{type(exc).__name__}:{exc}")

        configured = [bool(self._groq), bool(self._gemini_on)]
        got = [result["groq"], result["gemini"]]
        result["ok"] = any(got) and all((not cfg) or bool(val) for cfg, val in zip(configured, got))
        if errors:
            result["error"] = "; ".join(errors)
        log.info(f"test_connection ok={result['ok']} groq={result['groq']!r} gemini={result['gemini']!r}")
        return result


_SINGLETON: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = LLMClient()
    return _SINGLETON
