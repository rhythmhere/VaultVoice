"""One-time demo reset.

This script is intentionally never imported by the application. It requires
--confirm-reset and takes a database backup before deleting case data.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select, text

from backend.config import get_settings
from backend.db import NGOAccount, NGODocument, NGOVerificationLog, Organization, SessionLocal
from backend.main import token_hash


DEMO_NGOS = [
    {"name": "Himalayan Legal Aid Collective", "categories": ["legal_aid", "harassment", "workplace"], "districts": ["Kathmandu", "Lalitpur"], "phone": "9800001001", "email": "demo-legal@vaultvoice.test", "description": "Demo legal information and survivor advocacy service."},
    {"name": "Sajilo Health Response", "categories": ["medical", "domestic_violence"], "districts": ["Kathmandu", "Pokhara"], "phone": "9800001002", "email": "demo-medical@vaultvoice.test", "description": "Demo trauma-informed medical referral and health support."},
    {"name": "Aashraya Safe Shelter", "categories": ["shelter", "domestic_violence", "stalking"], "districts": ["Lalitpur", "Bhaktapur"], "phone": "9800001003", "email": "demo-shelter@vaultvoice.test", "description": "Demo emergency shelter, relocation, and safety planning."},
    {"name": "Ujyalo Counselling Centre", "categories": ["counselling", "harassment", "domestic_violence"], "districts": ["Pokhara", "Kathmandu"], "phone": "9800001004", "email": "demo-care@vaultvoice.test", "description": "Demo confidential psychosocial counselling and support."},
    {"name": "Bal Suraksha Nepal", "categories": ["child_protection", "shelter", "counselling"], "districts": ["Bhaktapur", "Pokhara"], "phone": "9800001005", "email": "demo-child@vaultvoice.test", "description": "Demo child protection, safe accommodation, and referrals."},
]

CASE_TABLES = [
    "case_message_reads", "case_messages", "case_status_logs", "case_notes",
    "referral_audit_log", "referrals", "commission_audit_log", "commission_records",
    "case_matches", "evidence", "sessions", "crowdfunding_donations",
    "crowdfunding_campaigns", "crowdfunding_requests", "platform_donations", "cases",
]


def backup_database(output: Path) -> None:
    database_url = get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")
    result = subprocess.run(["pg_dump", "--format=custom", "--file", str(output), "--dbname", database_url], check=False, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"pg_dump failed: {result.stderr.strip()} Install PostgreSQL client tools or run the script where pg_dump is available.")


def reset() -> dict[str, str]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = Path("backups") / f"demo-reset-{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup_database(backup_dir / "vaultvoice.dump")
    session = SessionLocal()
    tokens: dict[str, str] = {}
    try:
        for table in CASE_TABLES:
            session.execute(text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE'))
        session.execute(delete(NGOVerificationLog))
        session.execute(delete(NGODocument))
        session.execute(delete(Organization).where(Organization.name.not_in([item["name"] for item in DEMO_NGOS])))
        session.commit()
        for item in DEMO_NGOS:
            organization = session.scalar(select(Organization).where(Organization.name == item["name"]))
            if not organization:
                organization = Organization(name=item["name"], categories=item["categories"], districts=item["districts"], contact_phone=item["phone"], contact_email=item["email"], description=item["description"], verification_status="approved", verification_note="Demo organization")
                session.add(organization)
                session.flush()
            else:
                organization.categories, organization.districts = item["categories"], item["districts"]
                organization.contact_phone, organization.contact_email = item["phone"], item["email"]
                organization.description, organization.verification_status = item["description"], "approved"
            token = f"demo-{item['name'].lower().replace(' ', '-')}-token"
            account = organization.account
            if not account:
                account = NGOAccount(ngo_id=organization.id, subscription_tier="free", billing_status="active", commission_agreement=False, api_token_hash=token_hash(token))
                session.add(account)
            else:
                account.api_token_hash = token_hash(token)
                account.billing_status = "active"
            tokens[item["name"]] = token
            doc_dir = Path("demo_documents")
            doc_dir.mkdir(exist_ok=True)
            doc_path = doc_dir / f"{organization.id}-registration.txt"
            doc_path.write_text(f"Placeholder demo registration document for {item['name']}.\n", encoding="ascii")
            session.add(NGODocument(ngo_id=organization.id, object_key=str(doc_path), original_name=doc_path.name, doc_type="registration", status="approved"))
        session.commit()
    finally:
        session.close()
    (backup_dir / "demo-ngo-tokens.json").write_text(json.dumps(tokens, indent=2), encoding="ascii")
    return {"backup": str(backup_dir), **tokens}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-reset", action="store_true")
    args = parser.parse_args()
    if not args.confirm_reset:
        parser.error("This is destructive. Re-run with --confirm-reset after reviewing the script.")
    print(json.dumps(reset(), indent=2))
