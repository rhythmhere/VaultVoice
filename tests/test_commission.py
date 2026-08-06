"""Regression coverage for the payment-blind billing boundary."""
from types import SimpleNamespace

from backend import matching


class Session:
    def __init__(self, organizations):
        self.organizations = organizations
        self.added = []

    def scalars(self, _query):
        return SimpleNamespace(all=lambda: self.organizations)

    def add(self, item):
        self.added.append(item)

    def commit(self):
        pass


def test_matching_output_does_not_change_with_billing_data():
    organizations = [SimpleNamespace(id=1, name="Support", categories=["harassment"], districts=["Kathmandu"], contact_phone="100", contact_email=None, website=None, description="Help")]
    case = SimpleNamespace(case_id="VV-TEST", category="harassment", district="Kathmandu", matches=[])
    first = matching.match_case(Session(organizations), case)
    # Billing fields are intentionally not present on the matcher inputs. They
    # belong to NGOAccount and CommissionRecord in the API layer.
    organizations[0].subscription_tier = "free"
    organizations[0].commission_agreement = False
    second = matching.match_case(Session(organizations), case)
    assert first == second


def test_matcher_has_no_billing_model_imports():
    source = open(matching.__file__, encoding="utf-8").read()
    assert "NGOAccount" not in source
    assert "CommissionRecord" not in source
    assert "CommissionAuditLog" not in source
