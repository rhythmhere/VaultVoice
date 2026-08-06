"""Payment-blind case-to-organization matching.

This module deliberately imports only case and matching-domain models. Billing,
subscriptions, and commissions must never become inputs to survivor matching.
"""
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Case, CaseMatch, Organization


def match_case(session: Session, case: Case) -> list[dict[str, Any]]:
    organizations = [item for item in session.scalars(select(Organization)).all() if getattr(item, "verification_status", "approved") == "approved"]
    selected = select_best_match(organizations, case)
    existing = {item.organization_id for item in case.matches}
    for organization in selected:
        if organization.id not in existing:
            session.add(CaseMatch(
                case_id=case.case_id,
                organization_id=organization.id,
                match_reason=match_reason(case),
            ))
    session.commit()
    return [organization_json(organization, match_reason(case)) for organization in selected]


def select_best_match(organizations: list[Organization], case: Case) -> list[Organization]:
    """Return all relevant matches without consulting any billing data."""
    needs = {
        "domestic_violence": {"domestic_violence", "shelter", "medical", "counselling"},
        "harassment": {"harassment", "counselling", "legal_aid"},
        "stalking": {"stalking", "shelter", "counselling", "legal_aid"},
        "workplace": {"workplace", "legal_aid", "counselling"},
        "other": {"other", "counselling"},
    }.get(case.category, {case.category})
    def tier(organization: Organization) -> int | None:
        categories = set(organization.categories)
        district_match = case.district in organization.districts
        specialization_match = bool(categories & needs)
        if specialization_match and district_match:
            return 0
        if specialization_match:
            return 1
        if "legal_aid" in categories and district_match:
            return 2
        if "legal_aid" in categories:
            return 3
        return None

    eligible = [(tier(organization), organization) for organization in organizations]
    eligible = [(rank, organization) for rank, organization in eligible if rank is not None]
    if not eligible:
        return []
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    eligible.sort(key=lambda item: (item[0], getattr(item[1], "created_at", None) or epoch, item[1].id))
    return [organization for _, organization in eligible]


def match_reason(case: Case) -> str:
    return f"Matches {case.category.replace('_', ' ')} support and {case.district} coverage."


def organization_json(organization: Organization, reason: str) -> dict[str, Any]:
    return {
        "id": organization.id,
        "name": organization.name,
        "categories": organization.categories or [],
        "contact_phone": organization.contact_phone,
        "contact_email": organization.contact_email,
        "website": organization.website,
        "description": organization.description,
        "districts": organization.districts,
        "match_reason": reason,
    }
