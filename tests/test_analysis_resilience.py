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
        if isinstance(case, main.CaseSession):
            self.items[f"session:{case.session_token}"] = case
        else:
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


class CountingClarificationService:
    def __init__(self):
        self.calls = 0

    async def analyze_report(self, *args):
        self.calls += 1
        return {"legal_summary": "General support information.", "severity": "low", "clarifying_questions": ["One more question"]}


class FailingTimelineService:
    async def build_timeline(self, *_args):
        raise AIServiceError("provider unavailable")


@pytest.mark.parametrize("failure", ["timeout", "401", "429", "malformed response"])
def test_case_creation_survives_each_provider_failure(monkeypatch, failure):
    session = MemorySession()
    monkeypatch.setattr(main, "serialize_case", lambda _session, case: {"case_id": case.case_id, "analysis_status": case.analysis_status})
    monkeypatch.setattr(main, "make_case_id", lambda _session: "VV-TEST")
    payload = main.CaseCreate(category="other", district="Kathmandu", initial_report="qwert", clarifying_qa=[])

    response = asyncio.run(main.create_case(request(), payload, session, FailingService()))

    assert response["case_id"] == "VV-TEST", failure
    assert response["analysis_status"] == "failed", failure
    assert response["clarifying_questions"] == [main.INTAKE_QUESTIONS[0]], failure
    assert response["session_token"], failure
    assert session.items["VV-TEST"].initial_report == "qwert"


def test_case_creation_completes_when_provider_works(monkeypatch):
    session = MemorySession()
    monkeypatch.setattr(main, "serialize_case", lambda _session, case: {"case_id": case.case_id, "analysis_status": case.analysis_status, "severity": case.severity})
    monkeypatch.setattr(main, "make_case_id", lambda _session: "VV-TEST")
    payload = main.CaseCreate(category="other", district="Kathmandu", initial_report="qwert", clarifying_qa=[])

    response = asyncio.run(main.create_case(request(), payload, session, WorkingService()))

    assert response["analysis_status"] == "complete"
    assert response["severity"] == "low"
    assert response["clarifying_questions"] == [main.INTAKE_QUESTIONS[0]]


def test_analysis_can_transition_from_failed_to_complete(monkeypatch):
    case = SimpleNamespace(case_id="VV-TEST", category="other", district="Kathmandu", initial_report="qwert", clarifying_qa=[], analysis_status="failed", ai_legal_summary=None, severity=None, updated_at=None)
    session = MemorySession()
    session.items[case.case_id] = case
    monkeypatch.setattr(main, "serialize_case", lambda _session, value: {"case_id": value.case_id, "analysis_status": value.analysis_status, "severity": value.severity})

    response = asyncio.run(main.retry_case_analysis("VV-TEST", session, WorkingService()))

    assert response["analysis_status"] == "complete"
    assert response["severity"] == "low"


def test_duplicate_clarification_submission_uses_cached_analysis(monkeypatch):
    main.case_analysis_cache.clear()
    case = SimpleNamespace(case_id="VV-TEST", category="other", initial_report="qwert", clarifying_qa=[], analysis_status="complete", ai_legal_summary="old", severity="low", updated_at=None)
    session = MemorySession()
    session.items[case.case_id] = case
    service = CountingClarificationService()
    payload = main.ClarifyRequest(question="Are you safe?", answer="Yes")

    first = asyncio.run(main.clarify("VV-TEST", payload, session, service))
    second = asyncio.run(main.clarify("VV-TEST", payload, session, service))

    assert service.calls == 1
    assert first["ai_legal_summary"] == second["ai_legal_summary"]


def test_five_question_intake_advances_independently_of_provider_questions(monkeypatch):
    case = SimpleNamespace(case_id="VV-TEST", category="other", initial_report="qwert", clarifying_qa=[], analysis_status="complete", ai_legal_summary="old", severity="low", updated_at=None)
    session = MemorySession()
    session.items[case.case_id] = case
    service = CountingClarificationService()

    for index, expected_question in enumerate(main.INTAKE_QUESTIONS):
        response = asyncio.run(main.clarify("VV-TEST", main.ClarifyRequest(question=expected_question, answer=f"answer {index}"), session, service))
        expected_next = [main.INTAKE_QUESTIONS[index + 1]] if index + 1 < len(main.INTAKE_QUESTIONS) else []
        assert response["next_questions"] == expected_next


def test_evidence_timeline_has_a_deterministic_fallback_when_ai_is_unavailable():
    evidence = SimpleNamespace(id=4, original_name="photo.png", file_type="image/png", size=1, description=None, incident_date=None, uploaded_at=None, integrity_hash="hash")
    case = SimpleNamespace(case_id="VV-TEST", evidence=[evidence], timeline=[], updated_at=None)
    session = MemorySession()

    response = asyncio.run(main.regenerate_timeline_for_case(case, session, FailingTimelineService()))

    assert response["analysis_status"] == "unavailable"
    assert response["timeline"][0]["evidence_ids"] == [4]
    assert response["timeline"][0]["summary"] == "Evidence added: photo.png"
