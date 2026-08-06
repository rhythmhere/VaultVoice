"""Coverage for emergency triage and NGO operational boundaries."""
from types import SimpleNamespace

from backend import main, matching


def test_case_serialization_exposes_emergency_priority():
    case = SimpleNamespace(
        case_id="VV-URGENT",
        category="harassment",
        district="Kathmandu",
        initial_report="report",
        clarifying_qa=[],
        ai_legal_summary=None,
        severity="low",
        emergency_requested=True,
        analysis_status="complete",
        status="open",
        created_at=None,
        updated_at=None,
        timeline=[],
        evidence=[],
        matches=[],
    )
    class Session:
        def scalars(self, _query):
            return SimpleNamespace(all=lambda: [])

        def commit(self):
            pass

    result = main.serialize_case(Session(), case)
    assert result["emergency_requested"] is True
    assert result["priority"] == "emergency"


def test_matching_excludes_unverified_organizations():
    pending = SimpleNamespace(id=1, name="Pending", categories=["harassment"], districts=["Kathmandu"], contact_phone="100", contact_email=None, website=None, description="Pending", verification_status="pending")
    approved = SimpleNamespace(id=2, name="Approved", categories=["harassment"], districts=["Kathmandu"], contact_phone="101", contact_email=None, website=None, description="Approved", verification_status="approved")
    case = SimpleNamespace(case_id="VV-TEST", category="harassment", district="Kathmandu", matches=[])

    class Session:
        def scalars(self, _query):
            return SimpleNamespace(all=lambda: [pending, approved])

        def add(self, _item):
            pass

        def commit(self):
            pass

    assert [item["id"] for item in matching.match_case(Session(), case)] == [2]


def test_referral_payload_contains_standard_case_status_and_emergency_flag():
    case = SimpleNamespace(case_id="VV-TEST", severity="urgent", emergency_requested=True, initial_report="private", clarifying_qa=[], ai_legal_summary=None, timeline=[], evidence=[])
    organization = SimpleNamespace(id=7, name="Safe NGO")
    item = SimpleNamespace(id="ref-1", case_id="VV-TEST", ngo_id=7, organization=organization, case=case, consent_scope="contact_details_evidence_summary", submitted_message=None, status="forwarded", rejection_reason=None, support_status=None, case_status="pending", created_at=None, updated_at=None)
    result = main.referral_json(item)
    assert result["case_status"] == "pending"
    assert result["emergency_requested"] is True
    assert result["severity"] == "urgent"
