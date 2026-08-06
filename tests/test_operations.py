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


def test_matching_normalizes_registered_specializations_and_districts():
    organization = SimpleNamespace(
        id=7, name="New support", categories=["Domestic Voilence"], districts=[" kathmandu "],
        contact_phone="100", contact_email=None, website=None, description="Support", verification_status="approved",
    )
    case = SimpleNamespace(case_id="VV-TEST", category="domestic_violence", district="Kathmandu", matches=[])

    class Session:
        def scalars(self, _query):
            return SimpleNamespace(all=lambda: [organization])

        def add(self, _item):
            pass

        def commit(self):
            pass

    assert [item["id"] for item in matching.match_case(Session(), case)] == [7]


def test_approval_backfills_existing_cases_once():
    organization = SimpleNamespace(
        id=8, categories=["harassment"], districts=["Kathmandu"], verification_status="approved",
    )
    case = SimpleNamespace(case_id="VV-EXISTING", category="harassment", district="Kathmandu", matches=[])

    class Session:
        def __init__(self):
            self.added = []

        def add(self, item):
            self.added.append(item)

    session = Session()
    assert matching.backfill_organization_matches(session, organization, [case]) == 1
    assert matching.backfill_organization_matches(session, organization, [case]) == 0
    assert [(item.case_id, item.organization_id) for item in session.added] == [("VV-EXISTING", 8)]


def test_registration_normalizes_supported_values_and_rejects_unknown_specializations():
    assert matching.normalize_categories(["Domestic Violence", "legal aid"]) == ["domestic_violence", "legal_aid"]
    assert matching.normalize_districts([" kathmandu ", "KATHMANDU"]) == ["Kathmandu"]
    try:
        matching.normalize_categories(["not-a-real-service"])
    except ValueError:
        pass
    else:
        raise AssertionError("Unknown specializations must not be silently stored")


def test_referral_payload_contains_standard_case_status_and_emergency_flag():
    case = SimpleNamespace(case_id="VV-TEST", severity="urgent", emergency_requested=True, initial_report="private", clarifying_qa=[], ai_legal_summary=None, timeline=[], evidence=[])
    organization = SimpleNamespace(id=7, name="Safe NGO")
    item = SimpleNamespace(id="ref-1", case_id="VV-TEST", ngo_id=7, organization=organization, case=case, consent_scope="contact_details_evidence_summary", submitted_message=None, status="forwarded", rejection_reason=None, support_status=None, case_status="pending", created_at=None, updated_at=None)
    result = main.referral_json(item)
    assert result["case_status"] == "pending"
    assert result["emergency_requested"] is True
    assert result["severity"] == "urgent"
