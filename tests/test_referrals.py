"""Direct API-handler coverage for consent and referral isolation."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend import main


def referral(status="forwarded", scope="full_case", ngo_id=7):
    evidence = [SimpleNamespace(id=3, original_name="proof.txt", file_type="text/plain", size=4, description="proof", incident_date=None, uploaded_at=None, integrity_hash="hash")]
    case = SimpleNamespace(case_id="VV-TEST", category="harassment", district="Kathmandu", severity="high", initial_report="private report", clarifying_qa=[{"answer": "secret"}], ai_legal_summary="private legal summary", timeline=[{"summary": "private timeline"}], evidence=evidence)
    organization = SimpleNamespace(id=ngo_id, name="Safe NGO")
    return SimpleNamespace(id="ref-1", case_id=case.case_id, ngo_id=ngo_id, organization=organization, case=case, consent_scope=scope, submitted_message="Please help", status=status, rejection_reason=None, support_status=None, created_at=None, updated_at=None, audit_log=[])


class Session:
    def __init__(self, item=None):
        self.item = item
        self.logs = []

    def get(self, model, identifier):
        return self.item if identifier == getattr(self.item, "id", None) else None

    def scalar(self, query):
        return self.item

    def add(self, item):
        self.logs.append(item)

    def commit(self):
        pass


def account(ngo_id=7, tier="free"):
    return SimpleNamespace(ngo_id=ngo_id, subscription_tier=tier, billing_status="active")


def test_restricted_ngo_api_payload_has_no_full_case_or_evidence():
    item = referral(scope="contact_details_evidence_summary")
    response = main.get_ngo_referral("ref-1", account(), Session(item))
    assert response["case"]["initial_report"] is None
    assert response["case"]["clarifying_qa"] == []
    assert response["case"]["evidence"] == []


def test_restricted_ngo_evidence_endpoint_is_denied_directly():
    item = referral(scope="contact_details_evidence_summary")
    with pytest.raises(HTTPException) as error:
        main.download_ngo_evidence("ref-1", 3, account(), Session(item), SimpleNamespace())
    assert error.value.status_code == 403


def test_ngo_cannot_see_a_referral_owned_by_another_ngo():
    item = referral(ngo_id=8)
    with pytest.raises(HTTPException) as error:
        main.get_ngo_referral("ref-1", account(ngo_id=7), Session(item))
    assert error.value.status_code == 404


def test_free_tier_can_acknowledge_forwarded_referral():
    item = referral(status="forwarded")
    response = main.acknowledge_referral("ref-1", account(tier="free"), Session(item))
    assert response["status"] == "acknowledged"


def test_acknowledge_before_admin_forwarding_is_rejected():
    item = referral(status="requested")
    with pytest.raises(HTTPException) as error:
        main.acknowledge_referral("ref-1", account(), Session(item))
    assert error.value.status_code == 409


def test_free_tier_can_refuse_and_update_acknowledged_referral():
    refused = referral(status="forwarded")
    response = main.refuse_referral("ref-1", main.ReferralReason(reason="Outside current capacity"), account(tier="free"), Session(refused))
    assert response["status"] == "closed"
    assert response["rejection_reason"] == "Outside current capacity"

    acknowledged = referral(status="acknowledged")
    response = main.update_referral_support("ref-1", main.SupportUpdate(support_status="intake scheduled"), account(tier="free"), Session(acknowledged))
    assert response["support_status"] == "intake scheduled"


def test_forwarding_requires_admin_transition_and_records_every_transition():
    item = referral(status="requested")
    session = Session(item)
    response = main.approve_referral("ref-1", session)
    assert response["status"] == "forwarded"
    assert [(log.from_status, log.to_status, log.action) for log in session.logs] == [
        ("requested", "admin_review", "review_started"),
        ("admin_review", "forwarded", "approved_and_forwarded"),
    ]


def test_referral_cannot_skip_admin_review():
    item = referral(status="requested")
    with pytest.raises(HTTPException):
        main.transition(item, "forwarded", "survivor", "send", Session(item))


def test_full_audit_history_is_returned():
    item = referral()
    item.audit_log = [SimpleNamespace(id=1, actor_id="survivor", action="consent_requested", from_status="draft", to_status="requested", note=None, changed_at=datetime.now(timezone.utc))]
    response = main.get_admin_referral("ref-1", Session(item))
    assert response["audit"][0]["actor_id"] == "survivor"
