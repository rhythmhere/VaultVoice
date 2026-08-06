import asyncio
import json
import logging
import time
from collections import deque
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Any

import httpx

from .config import Settings

LEGAL_CONTEXT = """Domestic Violence (Offence and Punishment) Act 2066 recognizes physical, mental, sexual and economic harm within a domestic relationship. Nepal's criminal law includes provisions relevant to harassment, threats and stalking. Workplace harassment may be raised through an employer process and legal aid. A person can seek support from a legal-aid organization, Nepal Police at 100 in immediate danger, or the National Women Commission Khabar Garaun helpline at 1145. This reference is general information, not formal legal advice."""


class AIServiceError(RuntimeError):
    pass


class AIRateLimitError(AIServiceError):
    def __init__(self, retry_after: float | None = None):
        super().__init__("OpenRouter rate limit exceeded")
        self.retry_after = retry_after


class OpenRouterRequestBudget:
    def __init__(self, logger: logging.Logger | None = None):
        self.calls: deque[float] = deque()
        self.logger = logger or logging.getLogger("vaultvoice.ai")
        self.warning_windows: set[str] = set()

    def record(self, now: float | None = None) -> tuple[int, int]:
        current = time.monotonic() if now is None else now
        self.calls.append(current)
        while self.calls and self.calls[0] <= current - 86400:
            self.calls.popleft()
        minute_count = sum(timestamp > current - 60 for timestamp in self.calls)
        day_count = len(self.calls)
        for window, count, threshold in (("minute", minute_count, 15), ("day", day_count, 150)):
            if count >= threshold and window not in self.warning_windows:
                self.logger.warning("OpenRouter request budget nearing limit: %d calls in %s window", count, window)
                self.warning_windows.add(window)
            elif count < threshold:
                self.warning_windows.discard(window)
        return minute_count, day_count

    def snapshot(self, now: float | None = None) -> tuple[int, int]:
        current = time.monotonic() if now is None else now
        while self.calls and self.calls[0] <= current - 86400:
            self.calls.popleft()
        return sum(timestamp > current - 60 for timestamp in self.calls), len(self.calls)


request_budget = OpenRouterRequestBudget()


class OpenRouterAIService:
    timeline_retry_delay = 3.0
    timeline_retry_cap = 60.0
    request_timeout = httpx.Timeout(20.0, connect=5.0)

    def __init__(self, settings: Settings):
        self.settings = settings

    async def _complete(self, system: str, user: str) -> str:
        if not self.settings.openrouter_api_key:
            raise AIServiceError("OPENROUTER_API_KEY is not configured")
        minute_count, day_count = request_budget.record()
        logging.getLogger("vaultvoice.ai").info("OpenRouter request count minute=%d day=%d", minute_count, day_count)
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.settings.openrouter_site_url,
            "X-Title": self.settings.openrouter_app_name,
        }
        body = {"model": self.settings.openrouter_model, "temperature": 0.2, "max_tokens": 500, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        try:
            async with httpx.AsyncClient(timeout=self.request_timeout) as client:
                response = await client.post(f"{self.settings.openrouter_base_url}/chat/completions", headers=headers, json=body)
                # Provider errors contain only structural diagnostics here; never log prompts.
                if response.status_code == 429:
                    raise AIRateLimitError(self._retry_after(response))
                if response.status_code >= 400:
                    logging.getLogger("vaultvoice.ai").error(
                        "OpenRouter response status=%s body=%s",
                        response.status_code,
                        response.text[:4000],
                    )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]
        except AIRateLimitError:
            raise
        except (httpx.HTTPError, KeyError, IndexError, TypeError) as exc:
            logging.getLogger("vaultvoice.ai").exception("OpenRouter request/response failure: %r", exc)
            raise AIServiceError("OpenRouter request failed") from exc

    @classmethod
    def _retry_after(cls, response: httpx.Response) -> float | None:
        value = response.headers.get("retry-after")
        if not value:
            return None
        try:
            return max(0.0, min(float(value), cls.timeline_retry_cap))
        except ValueError:
            try:
                reset_at = parsedate_to_datetime(value)
                if reset_at.tzinfo is None:
                    reset_at = reset_at.replace(tzinfo=timezone.utc)
                return max(0.0, min((reset_at - datetime.now(timezone.utc)).total_seconds(), cls.timeline_retry_cap))
            except (TypeError, ValueError, OverflowError):
                return None

    async def analyze_report(self, category: str, report: str, qa: list[dict[str, Any]]) -> dict[str, Any]:
        system = """You are VaultVoice, a supportive legal-information assistant for survivors in Nepal. You are not a lawyer. Ground all legal claims only in the reference context. Be calm, non-judgmental, and support English, Nepali, and code-switched input. Return valid JSON only with keys: clarifying_questions (array of at most 3 short questions), legal_summary (string), severity (one of low, moderate, urgent). Ask questions only when the report is not yet sufficiently clear; otherwise return an empty array. Never invent laws, contacts, or facts."""
        user = f"REFERENCE CONTEXT:\n{LEGAL_CONTEXT}\n\nCATEGORY: {category}\nREPORT:\n{report}\nPRIOR QUESTIONS/ANSWERS:\n{json.dumps(qa, ensure_ascii=False)}"
        raw = await self._complete(system, user)
        try:
            result = json.loads(raw)
            if result.get("severity") not in {"low", "moderate", "urgent"}:
                raise ValueError
            return result
        except (json.JSONDecodeError, ValueError, AttributeError) as exc:
            raise AIServiceError("OpenRouter returned invalid report analysis") from exc

    async def build_timeline(self, evidence: list[dict[str, Any]]) -> dict[str, Any]:
        system = "Return valid JSON only with keys timeline (array of objects with date, summary, evidence_ids, type) and summary (string). Organize only the supplied evidence chronologically. Do not speculate or invent dates."
        user = f"Evidence metadata:\n{json.dumps(evidence, ensure_ascii=False, default=str)}"
        try:
            raw = await self._complete(system, user)
        except AIRateLimitError as exc:
            delay = exc.retry_after if exc.retry_after is not None else self.timeline_retry_delay
            logging.getLogger("vaultvoice.ai").warning("Timeline rate limited; retrying in %.1fs", delay)
            await asyncio.sleep(delay)
            raw = await self._complete(system, user)
        try:
            result = json.loads(raw)
            return {"timeline": result["timeline"], "summary": result.get("summary", "")}
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise AIServiceError("OpenRouter returned invalid timeline JSON") from exc
