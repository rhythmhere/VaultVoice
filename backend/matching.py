"""Payment-blind case-to-organization matching.

This module deliberately imports only case and matching-domain models. Billing,
subscriptions, and commissions must never become inputs to survivor matching.
"""
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Case, CaseMatch, Organization


# These identifiers are also used by the survivor intake flow.  Registration
# accepts the human-readable spellings below and stores the canonical value so
# a small spelling or formatting difference never hides a suitable NGO.
SUPPORTED_CATEGORIES = frozenset({
    "domestic_violence", "harassment", "stalking", "workplace", "other",
    "shelter", "medical", "counselling", "legal_aid",
})
CATEGORY_ALIASES = {
    "domestic violence": "domestic_violence",
    "domestic-violence": "domestic_violence",
    "domestic voilence": "domestic_violence",
    "legal aid": "legal_aid",
    "legal-aid": "legal_aid",
    "mental health": "counselling",
    "counseling": "counselling",
}


def normalize_category(value: str) -> str:
    """Return the category identifier used by survivor cases and matching."""
    normalized = " ".join(value.strip().lower().replace("_", " ").split())
    normalized = CATEGORY_ALIASES.get(normalized, normalized)
    return normalized.replace(" ", "_")


def normalize_categories(values: list[str]) -> list[str]:
    """Normalize and de-duplicate NGO specializations without silently guessing."""
    normalized = list(dict.fromkeys(normalize_category(value) for value in values if value.strip()))
    invalid = [value for value in normalized if value not in SUPPORTED_CATEGORIES]
    if invalid:
        supported = ", ".join(sorted(SUPPORTED_CATEGORIES))
        raise ValueError(f"Unsupported specialization: {', '.join(invalid)}. Use one of: {supported}.")
    if not normalized:
        raise ValueError("At least one specialization is required.")
    return normalized


def normalize_districts(values: list[str]) -> list[str]:
    """Store districts consistently while retaining the display-friendly name."""
    normalized = list(dict.fromkeys(" ".join(value.strip().split()).title() for value in values if value.strip()))
    if not normalized:
        raise ValueError("At least one district is required.")
    return normalized


def _district_key(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def match_case(session: Session, case: Case) -> list[dict[str, Any]]:
    organizations = [item for item in session.scalars(select(Organization)).all() if getattr(item, "verification_status", "approved") == "approved"]
    selected = select_best_match(organizations, case)
    sync_case_matches(session, case, selected)
    session.commit()
    return [organization_json(organization, match_reason(case)) for organization in selected]


def sync_case_matches(session: Session, case: Case, organizations: list[Organization]) -> int:
    """Persist only missing matches and return the number created."""
    existing = {item.organization_id for item in case.matches}
    created = 0
    for organization in organizations:
        if organization.id not in existing:
            match = CaseMatch(case_id=case.case_id, organization_id=organization.id, match_reason=match_reason(case))
            # Keep an already-loaded relationship in sync too.  This prevents
            # duplicate inserts when a case is reconciled more than once in a
            # single request/session.
            case.matches.append(match)
            session.add(match)
            existing.add(organization.id)
            created += 1
    return created


def backfill_organization_matches(session: Session, organization: Organization, cases: list[Case] | None = None) -> int:
    """Create matches for an approved NGO against pre-existing compatible cases."""
    if getattr(organization, "verification_status", "approved") != "approved":
        return 0
    cases = cases if cases is not None else session.scalars(select(Case)).all()
    created = 0
    for case in cases:
        if organization in select_best_match([organization], case):
            created += sync_case_matches(session, case, [organization])
    return created


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
        categories = {normalize_category(category) for category in organization.categories}
        district_match = _district_key(case.district) in {_district_key(district) for district in organization.districts}
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
