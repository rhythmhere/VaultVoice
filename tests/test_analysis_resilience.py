"""Cases must remain usable when the optional AI provider is unavailable."""

import asyncio
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from backend import main
from backend.ai_service import AIServiceError


def request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": [], "query_string": b"", "client": ("test", 1), "server": ("test", 80), "scheme": "http"})


class MemorySession:
    def __init__(self):
        self.items = {}

    def get(self, model, identifier):
        return self.items.get(identifier)

    def add(self, case):
        self.items[case.case_id] = case

    def commit(self):
        pass

    def refresh(self, case):
        pass


class FailingService:
    async def analyze_report(self, *args):
        raise AIServiceError("provider unavailable")


class WorkingService:
    async def analyze_report(self, *args):
        return {"legal_summary": "General support information.", "severity": "low", "clarifying_questions": []}


@pytest.mark.parametrize("failure", ["timeout", "401", "429", "malformed response"])
def test_case_creation_survives_each_provider_failure(monkeypatch, failure):
    session = MemorySession()
    monkeypatch.setattr(main, "serialize_case", lambda _session, case: {"case_id": case.case_id, "analysis_status": case.analysis_status})
    monkeypatch.setattr(main, "make_case_id", lambda _session: "VV-TEST")
    payload = main.CaseCreate(category="other", district="Kathmandu", initial_report="qwert", clarifying_qa=[])

    response = asyncio.run(main.create_case(request(), payload, session, FailingService()))

    assert response == {"case_id": "VV-TEST", "analysis_status": "failed", "clarifying_questions": []}, failure
    assert session.items["VV-TEST"].initial_report == "qwert"


def test_case_creation_completes_when_provider_works(monkeypatch):
    session = MemorySession()
    monkeypatch.setattr(main, "serialize_case", lambda _session, case: {"case_id": case.case_id, "analysis_status": case.analysis_status, "severity": case.severity})
    monkeypatch.setattr(main, "make_case_id", lambda _session: "VV-TEST")
    payload = main.CaseCreate(category="other", district="Kathmandu", initial_report="qwert", clarifying_qa=[])

    response = asyncio.run(main.create_case(request(), payload, session, WorkingService()))

    assert response["analysis_status"] == "complete"
    assert response["severity"] == "low"


def test_analysis_can_transition_from_failed_to_complete(monkeypatch):
    case = SimpleNamespace(case_id="VV-TEST", category="other", district="Kathmandu", initial_report="qwert", clarifying_qa=[], analysis_status="failed", ai_legal_summary=None, severity=None, updated_at=None)
    session = MemorySession()
    session.items[case.case_id] = case
    monkeypatch.setattr(main, "serialize_case", lambda _session, value: {"case_id": value.case_id, "analysis_status": value.analysis_status, "severity": value.severity})

    response = asyncio.run(main.retry_case_analysis("VV-TEST", session, WorkingService()))

    assert response["analysis_status"] == "complete"
    assert response["severity"] == "low"
