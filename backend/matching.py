"""Payment-blind case-to-organization matching.

This module deliberately imports only case and matching-domain models. Billing,
subscriptions, and commissions must never become inputs to survivor matching.
"""
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Case, CaseMatch, Organization


def match_case(session: Session, case: Case) -> list[dict[str, Any]]:
    categories = {case.category, "legal_aid"}
    organizations = session.scalars(select(Organization)).all()
    ranked: list[tuple[int, Organization]] = []
    for organization in organizations:
        score = len(categories.intersection(set(organization.categories))) * 2
        if case.district in organization.districts:
            score += 3
        if score:
            ranked.append((score, organization))
    ranked.sort(key=lambda item: item[0], reverse=True)
    selected = ranked[:5]
    existing = {item.organization_id for item in case.matches}
    for _, organization in selected:
        if organization.id not in existing:
            session.add(CaseMatch(
                case_id=case.case_id,
                organization_id=organization.id,
                match_reason=match_reason(case),
            ))
    session.commit()
    return [organization_json(organization, match_reason(case)) for _, organization in selected]


def match_reason(case: Case) -> str:
    return f"Matches {case.category.replace('_', ' ')} support and {case.district} coverage."


def organization_json(organization: Organization, reason: str) -> dict[str, Any]:
    return {
        "id": organization.id,
        "name": organization.name,
        "contact_phone": organization.contact_phone,
        "contact_email": organization.contact_email,
        "website": organization.website,
        "description": organization.description,
        "districts": organization.districts,
        "match_reason": reason,
    }
