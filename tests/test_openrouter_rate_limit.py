import asyncio
from types import SimpleNamespace

import httpx

from backend.ai_service import AIRateLimitError, OpenRouterAIService, OpenRouterRequestBudget


def service():
    return OpenRouterAIService(SimpleNamespace(
        openrouter_api_key="test-key",
        openrouter_model="test-model",
        openrouter_base_url="https://openrouter.test/v1",
        openrouter_site_url="http://localhost",
        openrouter_app_name="VaultVoice",
    ))


def test_timeline_429_respects_retry_after_and_retries_once(monkeypatch):
    ai = service()
    calls = 0
    delays = []

    async def complete(_system, _user):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise AIRateLimitError(4)
        return '{"timeline": [], "summary": "ready"}'

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(ai, "_complete", complete)
    monkeypatch.setattr("backend.ai_service.asyncio.sleep", sleep)

    result = asyncio.run(ai.build_timeline([]))

    assert result == {"timeline": [], "summary": "ready"}
    assert calls == 2
    assert delays == [4]


def test_timeline_rate_limit_without_header_uses_default_backoff(monkeypatch):
    ai = service()
    delays = []

    async def complete(_system, _user):
        raise AIRateLimitError()

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(ai, "_complete", complete)
    monkeypatch.setattr("backend.ai_service.asyncio.sleep", sleep)

    try:
        asyncio.run(ai.build_timeline([]))
    except AIRateLimitError:
        pass
    else:
        raise AssertionError("second rate-limit failure should be surfaced")

    assert delays == [3.0]


def test_retry_after_header_is_parsed_and_one_normal_timeline_uses_one_call():
    response = httpx.Response(429, headers={"retry-after": "7"})
    assert OpenRouterAIService._retry_after(response) == 7

    ai = service()
    calls = 0

    async def complete(_system, _user):
        nonlocal calls
        calls += 1
        return '{"timeline": [], "summary": "ready"}'

    ai._complete = complete
    assert asyncio.run(ai.build_timeline([]))["summary"] == "ready"
    assert calls == 1


def test_request_budget_warns_at_conservative_thresholds(caplog):
    budget = OpenRouterRequestBudget()
    with caplog.at_level("WARNING", logger="vaultvoice.ai"):
        for index in range(15):
            budget.record(now=float(index))
        for index in range(15, 150):
            budget.record(now=1000 + index)

    assert budget.snapshot(now=1149) == (60, 150)
    assert "15 calls in minute window" in caplog.text
    assert "150 calls in day window" in caplog.text
