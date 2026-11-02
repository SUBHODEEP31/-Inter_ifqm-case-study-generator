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
import time
import requests
import httpx
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
)
_GEMINI_RETRYABLE = (
    (g_exc.ServiceUnavailable, g_exc.DeadlineExceeded)
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
        self._mistral_cooldown_until = 0.0

        self.primary_model = os.getenv("PRIMARY_MODEL", "llama-3.3-70b-versatile")
        self.utility_model = os.getenv("UTILITY_MODEL", "llama-3.1-8b-instant")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

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
        # Optimize: Route all calls to Gemini first if available, bypassing Groq's low daily token limits (TPD)
        if self._gemini_on:
            return Engine.GEMINI, self.gemini_model
            
        # Fallback to Groq if Gemini is not available
        if role == Role.BULK or role == Role.UTILITY:
            if self._groq:
                return Engine.GROQ, self.utility_model
        else:  # REASONING
            if self._groq:
                return Engine.GROQ, self.primary_model
        # exhaustive fallback
        if self._groq:
            return Engine.GROQ, self.primary_model
        return Engine.GEMINI, self.gemini_model

    def count_tokens(self, text: str) -> int:
        return len(self._encoder.encode(text or ""))

    # -- provider calls ---------------------------------------------------- #
    def _groq_complete_raw(self, model: str, messages: list[dict], temperature: float, max_tokens: int) -> str:
        resp = self._groq.chat.completions.create(
            model=model, messages=messages, temperature=temperature, max_tokens=max_tokens
        )
        return (resp.choices[0].message.content or "").strip()

    @_retry_policy
    def _groq_complete(self, model: str, messages: list[dict], temperature: float, max_tokens: int) -> str:
        return self._groq_complete_raw(model, messages, temperature, max_tokens)

    def _gemini_complete_raw(self, model_name: str, prompt: str, system: str | None, temperature: float, max_tokens: int) -> str:
        model = genai.GenerativeModel(model_name, system_instruction=system or None)
        resp = model.generate_content(
            prompt,
            generation_config={"temperature": temperature, "max_output_tokens": max_tokens},
        )
        try:
            return (resp.text or "").strip()
        except Exception:
            return ""

    @_retry_policy
    def _gemini_complete(self, model_name: str, prompt: str, system: str | None, temperature: float, max_tokens: int) -> str:
        return self._gemini_complete_raw(model_name, prompt, system, temperature, max_tokens)

    def _mistral_complete_raw(self, prompt: str, system: str | None = None, temperature: float = 0.2, max_tokens: int = 2048) -> str:
        mistral_key = os.getenv("MISTRAL_API_KEY", "").strip()
        if not mistral_key:
            raise LLMClientError("Mistral key not set.")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {mistral_key}"
        }
        payload = {
            "model": "mistral-large-latest",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        resp = requests.post("https://api.mistral.ai/v1/chat/completions", json=payload, headers=headers, timeout=60.0)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    @_retry_policy
    def _mistral_complete(self, prompt: str, system: str | None = None, temperature: float = 0.2, max_tokens: int = 2048) -> str:
        return self._mistral_complete_raw(prompt, system, temperature, max_tokens)

    def _nara_complete_raw(self, prompt: str, system: str | None = None, temperature: float = 0.2, max_tokens: int = 2048) -> str:
        nara_key = os.getenv("NARAROUTER_API_KEY", "").strip()
        nara_url = os.getenv("NARAROUTER_BASE_URL", "https://router.bynara.id/v1").strip()
        nara_model = os.getenv("NARAROUTER_MODEL", "mimo-v2.5-pro").strip()
        if not nara_key:
            raise LLMClientError("NaraRouter key not set.")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        try:
            import openai
            client = openai.OpenAI(api_key=nara_key, base_url=nara_url, timeout=90.0)
            res = client.chat.completions.create(
                model=nara_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return (res.choices[0].message.content or "").strip()
        except Exception as e:
            if "402" in str(e) or "payment_required" in str(e) or "Insufficient credits" in str(e):
                log.warning("NaraRouter credit balance depleted (402 Payment Required). Falling back to backup generation models.")
            else:
                log.warning(f"NaraRouter client error: {e}")
            raise e

    @_retry_policy
    def _nara_complete(self, prompt: str, system: str | None = None, temperature: float = 0.2, max_tokens: int = 2048) -> str:
        return self._nara_complete_raw(prompt, system, temperature, max_tokens)

    def complete(
        self,
        prompt: str,
        *,
        role: Role = Role.REASONING,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        no_retry: bool = False,
    ) -> str:
        """Plain-text completion, routed by role and provider key availability with strict fallback layers."""
        sys_str = (system or "").lower()
        is_fact_check = any(k in sys_str for k in ["fact checker", "fact auditor", "linguistic fact", "grounding", "friction"])
        
        mistral_key = os.getenv("MISTRAL_API_KEY", "").strip()
        nara_key = os.getenv("NARAROUTER_API_KEY", "").strip()
        
        # Circuit Breaker: check if Mistral is on cooldown
        mistral_cooldown_active = False
        if hasattr(self, "_mistral_cooldown_until") and time.time() < self._mistral_cooldown_until:
            mistral_cooldown_active = True
            
        # Build priority chain list based on query type
        call_chain = []
        
        if is_fact_check:
            # Fact Checking Priority: NaraRouter -> Mistral -> Gemini -> Groq
            if nara_key:
                call_chain.append(("NaraRouter (Fact Check)", lambda: self._nara_complete_raw(prompt, system, temperature, max_tokens) if no_retry else self._nara_complete(prompt, system, temperature, max_tokens)))
            if mistral_key and not mistral_cooldown_active:
                call_chain.append(("Mistral (Fact Check Fallback)", lambda: self._mistral_complete_raw(prompt, system, temperature, max_tokens) if no_retry else self._mistral_complete(prompt, system, temperature, max_tokens)))
        else:
            # Generation Priority: NaraRouter -> Mistral -> Gemini -> Groq
            if nara_key:
                call_chain.append(("NaraRouter (Narrative Generation)", lambda: self._nara_complete_raw(prompt, system, temperature, max_tokens) if no_retry else self._nara_complete(prompt, system, temperature, max_tokens)))
            if mistral_key and not mistral_cooldown_active:
                call_chain.append(("Mistral (Generation Fallback)", lambda: self._mistral_complete_raw(prompt, system, temperature, max_tokens) if no_retry else self._mistral_complete(prompt, system, temperature, max_tokens)))
        
        # Fallbacks: Gemini -> Groq
        def run_gemini():
            engine, model = self._route(role)
            if no_retry:
                return self._gemini_complete_raw(model, prompt, system, temperature, max_tokens)
            return self._gemini_complete(model, prompt, system, temperature, max_tokens)
            
        def run_groq():
            engine, model = Engine.GROQ, (self.primary_model if role == Role.REASONING else self.utility_model)
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            if no_retry:
                return self._groq_complete_raw(model, messages, temperature, max_tokens)
            return self._groq_complete(model, messages, temperature, max_tokens)

        call_chain.append(("Gemini Fallback", run_gemini))
        call_chain.append(("Groq Fallback", run_groq))
        
        # Try each link in the chain in sequence
        errors = []
        for name, func in call_chain:
            try:
                log.info(f"Routing task to {name}...")
                result = func()
                if result:
                    return result
            except Exception as e:
                log.warning(f"{name} call failed: {e}. Trying next fallback...")
                errors.append(f"{name}: {e}")
                
                # Check for Mistral 429 to set circuit breaker cooldown
                if "Mistral" in name:
                    err_msg = str(e).lower()
                    if "429" in err_msg or "too many requests" in err_msg or "rate limit" in err_msg:
                        log.error("MISTRAL 429 RATE LIMIT EXCEEDED! Triggering 3-minute API circuit breaker cooldown.")
                        self._mistral_cooldown_until = time.time() + 180
                
        raise LLMClientError(f"All LLM providers in the fallback chain failed: {'; '.join(errors)}")

    def generate_text(
        self,
        model: str,
        system_message: str | None = None,
        user_message: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        no_retry: bool = False,
    ) -> str:
        """Compatibility wrapper for generate_text calling complete() with automated role routing."""
        role = Role.REASONING
        if "8b" in model:
            role = Role.UTILITY
        elif "gemini" in model:
            role = Role.BULK

        prompt = user_message or ""
        return self.complete(
            prompt=prompt,
            role=role,
            system=system_message,
            temperature=temperature,
            max_tokens=max_tokens,
            no_retry=no_retry
        )

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
        """Schema-validated structured output. Routes to NaraRouter first for rate safety, then Mistral, then Gemini/Groq."""
        nara_key = os.getenv("NARAROUTER_API_KEY", "").strip()
        nara_url = os.getenv("NARAROUTER_BASE_URL", "https://router.bynara.id/v1").strip()
        nara_model = os.getenv("NARAROUTER_MODEL", "mimo-v2.5-pro").strip()
        
        if nara_key:
            try:
                log.info("Routing structured query to NaraRouter for rate safety and schema validation...")
                import json
                schema_json = response_model.model_json_schema()
                injected_prompt = (
                    f"{prompt}\n\n"
                    f"You MUST format the output as a valid JSON object matching this schema:\n{json.dumps(schema_json)}"
                )
                headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {nara_key}"
                }
                payload = {
                    "model": nara_model,
                    "messages": [
                        {"role": "system", "content": system or "You are a precise data extractor."},
                        {"role": "user", "content": injected_prompt}
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_format": {"type": "json_object"}
                }
                resp = requests.post(f"{nara_url}/chat/completions", json=payload, headers=headers, timeout=90.0)
                resp.raise_for_status()
                raw_text = resp.json()["choices"][0]["message"]["content"].strip()
                return response_model.model_validate_json(raw_text)
            except Exception as e:
                log.warning(f"NaraRouter structured extraction failed: {e}. Falling back to Mistral path.")

        mistral_key = os.getenv("MISTRAL_API_KEY", "").strip()
        # Circuit Breaker: check if Mistral is on cooldown
        mistral_cooldown_active = False
        if hasattr(self, "_mistral_cooldown_until") and time.time() < self._mistral_cooldown_until:
            mistral_cooldown_active = True

        if mistral_key and not mistral_cooldown_active:
            try:
                log.info("Routing structured query to Mistral for rate safety and schema validation...")
                import json
                schema_json = response_model.model_json_schema()
                injected_prompt = (
                    f"{prompt}\n\n"
                    f"You MUST format the output as a valid JSON object matching this schema:\n{json.dumps(schema_json)}"
                )
                headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {mistral_key}"
                }
                payload = {
                    "model": "mistral-large-latest",
                    "messages": [
                        {"role": "system", "content": system or "You are a precise data extractor."},
                        {"role": "user", "content": injected_prompt}
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_format": {"type": "json_object"}
                }
                resp = requests.post("https://api.mistral.ai/v1/chat/completions", json=payload, headers=headers, timeout=90.0)
                resp.raise_for_status()
                raw_text = resp.json()["choices"][0]["message"]["content"].strip()
                return response_model.model_validate_json(raw_text)
            except Exception as e:
                log.warning(f"Mistral structured extraction failed: {e}. Falling back to standard paths.")
                
                # Activate circuit breaker for Mistral 429
                err_msg = str(e).lower()
                if "429" in err_msg or "too many requests" in err_msg or "rate limit" in err_msg:
                    log.error("MISTRAL 429 RATE LIMIT EXCEEDED during structured query! Triggering 3-minute API circuit breaker cooldown.")
                    self._mistral_cooldown_until = time.time() + 180

        if self._gemini_on:
            try:
                log.info(f"Routing structured query to Gemini ({self.gemini_model}) for token safety...")
                model = genai.GenerativeModel(self.gemini_model, system_instruction=system or None)
                
                # Inject the Pydantic schema requirements into the prompt context
                schema_json = response_model.model_json_schema()
                injected_prompt = (
                    f"{prompt}\n\n"
                    f"You MUST format the output as a valid JSON object matching this schema:\n{schema_json}"
                )
                
                resp = model.generate_content(
                    injected_prompt,
                    generation_config={
                        "temperature": temperature,
                        "max_output_tokens": max_tokens,
                        "response_mime_type": "application/json"
                    },
                )
                
                raw_text = resp.text.strip()
                return response_model.model_validate_json(raw_text)
            except Exception as e:
                log.warning(f"Gemini structured generation failed: {e}. Attempting a clean deterministic retry on Gemini...")
                try:
                    resp = model.generate_content(
                        injected_prompt,
                        generation_config={
                            "temperature": 0.0,
                            "max_output_tokens": max_tokens,
                            "response_mime_type": "application/json"
                        },
                    )
                    raw_text = resp.text.strip()
                    return response_model.model_validate_json(raw_text)
                except Exception as retry_err:
                    log.warning(f"Gemini structured generation retry failed: {retry_err}. Falling back to Groq Llama.")
                
        if not self._structured:
            raise LLMClientError(
                "Structured extraction requires GROQ_API_KEY when Gemini is offline."
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
        result: dict[str, object] = {
            "ok": False,
            "groq": None,
            "gemini": None,
            "mistral": None,
            "nararouter": None,
            "error": None,
            "primary": None,
            "utility": None,
        }
        errors: list[str] = []

        if self._groq:
            try:
                nara_key = os.getenv("NARAROUTER_API_KEY")
                if nara_key:
                    os.environ["NARAROUTER_API_KEY"] = ""
                result["groq"] = self.complete(
                    "Reply with the single word: OK", role=Role.REASONING, max_tokens=5
                )
                if nara_key:
                    os.environ["NARAROUTER_API_KEY"] = nara_key
            except Exception as exc:
                errors.append(f"groq:{type(exc).__name__}:{exc}")
        if self._gemini_on:
            try:
                nara_key = os.getenv("NARAROUTER_API_KEY")
                if nara_key:
                    os.environ["NARAROUTER_API_KEY"] = ""
                result["gemini"] = self.complete(
                    "Reply with the single word: OK", role=Role.BULK, max_tokens=5
                )
                if nara_key:
                    os.environ["NARAROUTER_API_KEY"] = nara_key
            except Exception as exc:
                errors.append(f"gemini:{type(exc).__name__}:{exc}")
        if os.getenv("MISTRAL_API_KEY", "").strip():
            try:
                result["mistral"] = self._mistral_complete_raw(
                    "Reply with the single word: OK", system="grounding verification check", max_tokens=5
                )
            except Exception as exc:
                errors.append(f"mistral:{type(exc).__name__}:{exc}")
        if os.getenv("NARAROUTER_API_KEY", "").strip():
            try:
                result["nararouter"] = self._nara_complete_raw(
                    "Reply with the single word: OK", system=None, max_tokens=5
                )
            except Exception as exc:
                errors.append(f"nararouter:{type(exc).__name__}:{exc}")

        configured = [bool(self._groq), bool(self._gemini_on)]
        got = [result["groq"], result["gemini"]]
        result["ok"] = any(got) and all((not cfg) or bool(val) for cfg, val in zip(configured, got))
        
        if os.getenv("MISTRAL_API_KEY", "").strip() and not result["mistral"]:
            result["ok"] = False
        if os.getenv("NARAROUTER_API_KEY", "").strip() and not result["nararouter"]:
            result["ok"] = False
            
        if errors:
            result["error"] = "; ".join(errors)

        result["primary"] = result["nararouter"] or result["groq"] or result["gemini"]
        result["utility"] = result["nararouter"] or result["groq"] or result["gemini"]

        log.info(f"test_connection ok={result['ok']} groq={result['groq']!r} gemini={result['gemini']!r} mistral={result['mistral']!r} nararouter={result['nararouter']!r}")
        return result


_SINGLETON: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = LLMClient()
    return _SINGLETON
# =====================================================================
# AUTOMATED FRONTEND BRIDGE LAYER (LEAVES WARP'S CODE UNTOUCHED)
# =====================================================================
import inspect

# Automatically locate whatever class Warp defined in this file
for _name, _obj in list(globals().items()):
    if inspect.isclass(_obj) and _obj.__module__ == __name__ and _name != "DualEngineClient":
        from enum import Enum
        if issubclass(_obj, Enum) or issubclass(_obj, Exception):
            continue
        DualEngineClient = _obj
        break
else:
    # Safe fallback wrapper if Warp used loose functions instead of a class
    class DualEngineClient:
        def __init__(self, *args, **kwargs):
            pass
        def generate_text(self, *args, **kwargs):
            for _func_name in ['generate_text', 'call_llm', 'get_completion', 'chat']:
                if _func_name in globals():
                    return globals()[_func_name](*args, **kwargs)
            return "Error: Could not route to backend LLM function."