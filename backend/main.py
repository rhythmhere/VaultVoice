from __future__ import annotations

import hashlib
import csv
import io
import logging
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .ai_service import AIServiceError, OpenRouterAIService
from .config import get_settings
from .db import Case, CaseMatch, CaseMessage, CaseMessageRead, CaseNote, CaseStatusLog, CommissionAuditLog, CommissionRecord, CrowdfundingCampaign, CrowdfundingDonation, CrowdfundingRequest, Evidence, NGOAccount, NGODocument, NGOVerificationLog, Organization, PlatformDonation, Referral, ReferralAuditLog, Session as CaseSession, SessionLocal
from .matching import backfill_organization_matches, match_case, normalize_categories, normalize_districts
from .seed import seed_organizations
from .storage import ObjectStorage

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s vaultvoice %(message)s")
logger = logging.getLogger("vaultvoice")
case_analysis_cache: dict[tuple[str, str, str], dict[str, Any]] = {}
INTAKE_QUESTIONS = (
    "When did this happen, or when did it begin?",
    "Where did it happen, or where is the person involved now?",
    "Is anyone in immediate danger or do you need urgent support right now?",
    "Have you saved any messages, photos, documents, or other evidence?",
    "What kind of support would feel most helpful as a next step?",
)
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit])
app = FastAPI(title=settings.app_name, version="2.0.0", docs_url="/api/docs")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type", "Authorization"])


class AnalyzeRequest(BaseModel):
    category: str = Field(min_length=1, max_length=50)
    initial_report: str = Field(min_length=1, max_length=20000)
    clarifying_qa: list[dict[str, str]] = Field(default_factory=list)


class CaseCreate(AnalyzeRequest):
    district: str = Field(default="Kathmandu", min_length=1, max_length=100)
    emergency_requested: bool = False


class ClarifyRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    answer: str = Field(min_length=1, max_length=10000)


class StatusUpdate(BaseModel):
    status: str = Field(pattern="^(open|ngo_contacted|resolved)$")


class NGOAccountCreate(BaseModel):
    ngo_id: int
    subscription_tier: str = Field(default="free", pattern="^(free|paid)$")
    billing_status: str = Field(default="active", min_length=1, max_length=30)
    commission_agreement: bool = False


class CommissionCreate(BaseModel):
    case_id: str = Field(min_length=3, max_length=12)
    self_reported_outcome: str = Field(min_length=1, max_length=5000)
    commission_amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class CommissionAdjustment(BaseModel):
    status: str = Field(pattern="^(pending|confirmed|invoiced|paid)$")
    commission_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    note: str = Field(min_length=1, max_length=2000)


class ReferralCreate(BaseModel):
    ngo_id: int
    consent_scope: str = Field(pattern="^(full_case|contact_details_evidence_summary)$")
    submitted_message: str | None = Field(default=None, max_length=5000)
    consent_confirmed: bool
    includes_evidence: bool = False
    evidence_refs: list[int] = Field(default_factory=list, max_length=50)


class ReferralReason(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class ReferralReassign(BaseModel):
    ngo_id: int
    reason: str = Field(min_length=1, max_length=2000)


class SupportUpdate(BaseModel):
    support_status: str = Field(min_length=1, max_length=40)


class CaseStatusUpdate(BaseModel):
    case_status: str = Field(pattern="^(pending|in_progress|resolved|on_hold)$")
    note: str | None = Field(default=None, max_length=2000)


class CaseNoteCreate(BaseModel):
    note: str = Field(min_length=1, max_length=5000)


class NGORegistration(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    categories: list[str] = Field(min_length=1, max_length=20)
    districts: list[str] = Field(min_length=1, max_length=50)
    contact_phone: str = Field(min_length=3, max_length=40)
    contact_email: str | None = Field(default=None, max_length=160)
    website: str | None = Field(default=None, max_length=255)
    description: str = Field(min_length=1, max_length=5000)


class NGOProfileUpdate(BaseModel):
    categories: list[str] | None = Field(default=None, max_length=20)
    districts: list[str] | None = Field(default=None, max_length=50)
    contact_phone: str | None = Field(default=None, min_length=3, max_length=40)
    contact_email: str | None = Field(default=None, max_length=160)
    website: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=5000)


class NGOReview(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class DonationCreate(BaseModel):
    donor_name: str | None = Field(default=None, max_length=200)
    donor_email: str | None = Field(default=None, max_length=160)
    is_anonymous: bool = True
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="NPR", pattern="^[A-Z]{3}$")
    message: str | None = Field(default=None, max_length=2000)


class PaymentCallback(BaseModel):
    payment_status: str = Field(pattern="^(completed|failed|refunded)$")
    payment_reference: str = Field(min_length=1, max_length=255)


class CrowdfundingCreate(BaseModel):
    category: str = Field(pattern="^(medical|legal|shelter|education|relocation|other)$")
    explanation: str = Field(min_length=10, max_length=10000)
    requested_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    target_date: date | None = None
    consent_public_display: bool = False


class CrowdfundingReview(BaseModel):
    description: str | None = Field(default=None, min_length=10, max_length=10000)
    display_name: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=2000)


class MessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    is_internal_note: bool = False


class StatusStageUpdate(BaseModel):
    status: str = Field(pattern="^(pending|in_progress|resolved|on_hold)$")
    note: str | None = Field(default=None, max_length=2000)


class AuthLogin(BaseModel):
    identifier: str = Field(min_length=3, max_length=12)
    ip_address: str | None = Field(default=None, max_length=45)
    user_agent: str | None = Field(default=None, max_length=1000)


def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def now() -> datetime:
    return datetime.now(timezone.utc)


def make_case_id(session: Session) -> str:
    for _ in range(10):
        identifier = "VV-" + secrets.token_hex(4).upper()
        if not session.get(Case, identifier):
            return identifier
    raise HTTPException(503, "Could not allocate a unique Case ID")


def ai_service() -> OpenRouterAIService:
    return OpenRouterAIService(settings)


def storage_service() -> ObjectStorage:
    return ObjectStorage(settings)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authentication required")
    return authorization[7:].strip()


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if not settings.admin_api_token or not x_admin_token or not secrets.compare_digest(token_hash(x_admin_token), token_hash(settings.admin_api_token)):
        raise HTTPException(401, "Admin authentication required")


def current_ngo(x_ngo_token: str | None = Header(default=None), session: Session = Depends(get_db)) -> NGOAccount:
    if not x_ngo_token:
        raise HTTPException(401, "NGO authentication required")
    account = session.scalar(select(NGOAccount).where(NGOAccount.api_token_hash == token_hash(x_ngo_token)))
    if not account or account.billing_status != "active" or getattr(account.organization, "verification_status", "approved") != "approved":
        raise HTTPException(401, "NGO authentication required")
    return account


def current_case(authorization: str | None = Header(default=None), session: Session = Depends(get_db)) -> Case:
    token = bearer_token(authorization)
    record = session.get(CaseSession, token)
    if not record or not record.is_active or record.expires_at <= now():
        raise HTTPException(401, "Invalid or inactive session")
    record.last_accessed = now()
    return record.case


def commission_feature_enabled() -> None:
    if not settings.commission_enabled:
        raise HTTPException(503, "Commission workflow is disabled")


def commission_json(record: CommissionRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "case_id": record.case_id,
        "ngo_id": record.ngo_id,
        "self_reported_outcome": record.self_reported_outcome,
        "commission_amount": str(record.commission_amount),
        "currency": record.currency,
        "status": record.status,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def audit_commission(session: Session, record: CommissionRecord, actor_id: str, from_status: str | None, note: str | None = None) -> None:
    session.add(CommissionAuditLog(commission_id=record.id, actor_id=actor_id, from_status=from_status, to_status=record.status, note=note))


def evidence_json(item: Evidence) -> dict[str, Any]:
    return {"id": item.id, "name": item.original_name, "type": item.file_type, "size": item.size, "description": item.description, "incident_date": item.incident_date.isoformat() if item.incident_date else None, "uploaded_at": item.uploaded_at.isoformat() if item.uploaded_at else None, "integrity_hash": item.integrity_hash}


def message_json(item: CaseMessage, include_internal: bool = False) -> dict[str, Any]:
    result = {"id": item.id, "case_id": item.case_id, "sender_type": item.sender_type, "sender_id": item.sender_id, "message": item.message, "sent_at": item.sent_at.isoformat() if item.sent_at else None}
    if include_internal:
        result["is_internal_note"] = bool(item.is_internal_note)
    return result


def organization_json(organization: Organization, include_token: str | None = None) -> dict[str, Any]:
    result = {
        "id": organization.id,
        "name": organization.name,
        "categories": organization.categories or [],
        "districts": organization.districts or [],
        "contact_phone": organization.contact_phone,
        "contact_email": organization.contact_email,
        "website": organization.website,
        "description": organization.description,
        "verification_status": organization.verification_status,
        "verification_note": organization.verification_note,
        "created_at": organization.created_at.isoformat() if organization.created_at else None,
        "has_account": bool(organization.account),
        "subscription_tier": organization.account.subscription_tier if organization.account else None,
    }
    if include_token:
        result["token"] = include_token
    return result


def note_json(note: CaseNote) -> dict[str, Any]:
    return {"id": note.id, "referral_id": note.referral_id, "ngo_id": note.ngo_id, "note": note.note, "created_at": note.created_at.isoformat() if note.created_at else None}


def referral_json(referral: Referral, include_case: bool = False) -> dict[str, Any]:
    result = {
        "id": referral.id,
        "case_id": referral.case_id,
        "ngo_id": referral.ngo_id,
        "ngo_name": referral.organization.name,
        "severity": referral.case.severity,
        "consent_scope": referral.consent_scope,
        "submitted_message": referral.submitted_message,
        "includes_evidence": bool(getattr(referral, "includes_evidence", False)),
        "evidence_refs": getattr(referral, "evidence_refs", []) or [],
        "status": referral.status,
        "rejection_reason": referral.rejection_reason,
        "support_status": referral.support_status,
        "case_status": getattr(referral, "case_status", "pending"),
        "emergency_requested": bool(getattr(referral.case, "emergency_requested", False)),
        "created_at": referral.created_at.isoformat() if referral.created_at else None,
        "updated_at": referral.updated_at.isoformat() if referral.updated_at else None,
    }
    if include_case:
        case = referral.case
        result["case"] = {
            "case_id": case.case_id,
            "category": case.category,
            "district": case.district,
            "severity": case.severity,
            "emergency_requested": bool(getattr(case, "emergency_requested", False)),
            "initial_report": case.initial_report if referral.consent_scope == "full_case" else None,
            "clarifying_qa": case.clarifying_qa or [] if referral.consent_scope == "full_case" else [],
            "legal_summary": case.ai_legal_summary if referral.consent_scope == "full_case" else None,
            "timeline": case.timeline or [] if referral.consent_scope == "full_case" else [],
            "evidence": [evidence_json(item) for item in case.evidence if bool(getattr(referral, "includes_evidence", False)) and (not getattr(referral, "evidence_refs", None) or item.id in referral.evidence_refs)],
        }
    return result


def audit_referral(session: Session, referral: Referral, actor_id: str, action: str, from_status: str | None, note: str | None = None) -> None:
    session.add(ReferralAuditLog(referral_id=referral.id, actor_id=actor_id, action=action, from_status=from_status, to_status=referral.status, note=note))


def transition(referral: Referral, target: str, actor_id: str, action: str, session: Session, note: str | None = None) -> None:
    allowed = {
        "draft": {"requested"}, "requested": {"admin_review"}, "admin_review": {"forwarded"},
        "forwarded": {"acknowledged", "closed"}, "acknowledged": {"closed"}, "closed": set(),
    }
    if target not in allowed.get(referral.status, set()):
        raise HTTPException(409, f"Invalid referral transition: {referral.status} to {target}")
    previous = referral.status
    referral.status = target
    referral.updated_at = now()
    audit_referral(session, referral, actor_id, action, previous, note)


ALLOWED_EVIDENCE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
    "audio/mpeg",
    "audio/wav",
    "audio/ogg",
    "text/plain",
}


def has_valid_file_signature(content: bytes, content_type: str) -> bool:
    """Perform a small, conservative content check before object storage."""
    if not content:
        return False
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    if content_type == "application/pdf":
        return content.startswith(b"%PDF-")
    if content_type == "audio/mpeg":
        return content.startswith(b"ID3") or (len(content) >= 2 and content[0] == 0xFF and content[1] & 0xE0 == 0xE0)
    if content_type == "audio/wav":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WAVE"
    if content_type == "audio/ogg":
        return content.startswith(b"OggS")
    if content_type == "text/plain":
        return b"\x00" not in content
    return False


def serialize_case(session: Session, case: Case) -> dict[str, Any]:
    return {"case_id": case.case_id, "category": case.category, "district": case.district, "initial_report": case.initial_report, "clarifying_qa": case.clarifying_qa or [], "ai_legal_summary": case.ai_legal_summary, "severity": case.severity, "emergency_requested": bool(case.emergency_requested), "priority": "emergency" if case.emergency_requested or case.severity == "urgent" else "standard", "analysis_status": case.analysis_status, "status": case.status, "created_at": case.created_at.isoformat() if case.created_at else None, "updated_at": case.updated_at.isoformat() if case.updated_at else None, "timeline": case.timeline or [], "evidence": [evidence_json(item) for item in case.evidence], "matches": match_case(session, case)}


def intake_questions(qa: list[dict[str, Any]]) -> list[str]:
    """Keep the guided intake consistent even when the AI provider is unavailable."""
    return [INTAKE_QUESTIONS[len(qa)]] if len(qa) < len(INTAKE_QUESTIONS) else []


@app.middleware("http")
async def request_logging(request: Request, call_next):
    started = datetime.now(timezone.utc)
    response = await call_next(request)
    elapsed = (datetime.now(timezone.utc) - started).total_seconds() * 1000
    logger.info("%s %s %s %.1fms", request.method, request.url.path, response.status_code, elapsed)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.on_event("startup")
def startup() -> None:
    logger.info("OPENROUTER_API_KEY configured=%s", bool(settings.openrouter_api_key.strip()))
    with SessionLocal() as session:
        seed_organizations(session)
    try:
        storage_service().ensure_bucket()
    except Exception:
        logger.warning("MinIO is unavailable during startup; health will report degraded", exc_info=True)


@app.get("/health")
@app.get("/api/health")
def health(session: Session = Depends(get_db)) -> JSONResponse:
    checks = {"database": "ok", "storage": "ok"}
    try:
        session.execute(text("SELECT 1"))
    except Exception:
        checks["database"] = "unavailable"
    try:
        storage_service().ensure_bucket()
    except Exception:
        checks["storage"] = "unavailable"
    healthy = all(value == "ok" for value in checks.values())
    return JSONResponse(status_code=200 if healthy else 503, content={"status": "ok" if healthy else "degraded", "service": "vaultvoice-api", "checks": checks})


@app.post("/api/auth/login")
@limiter.limit("20/hour")
def login(request: Request, payload: AuthLogin, session: Session = Depends(get_db)) -> dict[str, Any]:
    case = session.get(Case, payload.identifier.strip().upper())
    if not case:
        raise HTTPException(404, "Case not found")
    token = secrets.token_urlsafe(48)
    record = CaseSession(session_token=token, case_id=case.case_id, expires_at=now() + timedelta(hours=1), ip_address=payload.ip_address, user_agent=payload.user_agent, is_active=True)
    session.add(record)
    session.commit()
    return {"session_token": token, "expires_at": record.expires_at.isoformat()}


@app.post("/api/auth/logout")
def logout(authorization: str | None = Header(default=None), session: Session = Depends(get_db)) -> dict[str, str]:
    token = bearer_token(authorization)
    record = session.get(CaseSession, token)
    if record:
        record.is_active = False
        session.commit()
    return {"message": "Logged out"}


@app.post("/api/ai/analyze")
@limiter.limit("20/minute")
async def analyze(request: Request, payload: AnalyzeRequest, service: OpenRouterAIService = Depends(ai_service)):
    logger.info("OpenRouter call path=standalone_analyze category=%s qa_count=%d", payload.category, len(payload.clarifying_qa))
    try:
        return await service.analyze_report(payload.category, payload.initial_report, payload.clarifying_qa)
    except AIServiceError as exc:
        logger.warning("Standalone AI analysis unavailable: %r", exc)
        return {"analysis_status": "failed", "clarifying_questions": [], "legal_summary": None, "severity": None}


@app.post("/api/cases")
@limiter.limit("10/hour")
async def create_case(request: Request, payload: CaseCreate, session: Session = Depends(get_db), service: OpenRouterAIService = Depends(ai_service)) -> dict[str, Any]:
    case = Case(case_id=make_case_id(session), category=payload.category, district=payload.district, initial_report=payload.initial_report, clarifying_qa=payload.clarifying_qa, ai_legal_summary=None, severity=None, emergency_requested=payload.emergency_requested, analysis_status="pending", status="open", timeline=[])
    session.add(case)
    session.commit()
    session.refresh(case)
    # Anonymous case creation is followed by a short-lived Case ID session.
    session_token = secrets.token_urlsafe(48)
    case_session = CaseSession(session_token=session_token, case_id=case.case_id, expires_at=now() + timedelta(hours=1), ip_address=get_remote_address(request), user_agent=request.headers.get("user-agent"), is_active=True)
    session.add(case_session)
    session.commit()
    logger.info("OpenRouter call path=create_case case_id=%s qa_count=%d", case.case_id, len(payload.clarifying_qa))
    try:
        analysis = await service.analyze_report(payload.category, payload.initial_report, payload.clarifying_qa)
    except AIServiceError as exc:
        logger.warning("Case analysis failed case_id=%s error=%r", case.case_id, exc)
        case.analysis_status = "failed"
        session.commit()
        return serialize_case(session, case) | {"clarifying_questions": intake_questions(case.clarifying_qa or []), "session_token": session_token, "session_expires_at": case_session.expires_at.isoformat()}
    case.ai_legal_summary = analysis["legal_summary"]
    case.severity = analysis["severity"]
    case.analysis_status = "complete"
    session.commit()
    session.refresh(case)
    result = serialize_case(session, case)
    result["clarifying_questions"] = intake_questions(case.clarifying_qa or [])
    result["session_token"] = session_token
    result["session_expires_at"] = case_session.expires_at.isoformat()
    return result


@app.post("/api/cases/{identifier}/analyze")
async def retry_case_analysis(identifier: str, session: Session = Depends(get_db), service: OpenRouterAIService = Depends(ai_service)) -> dict[str, Any]:
    case = session.get(Case, identifier.upper())
    if not case:
        raise HTTPException(404, "Case not found")
    case.analysis_status = "pending"
    session.commit()
    try:
        analysis = await service.analyze_report(case.category, case.initial_report, case.clarifying_qa or [])
    except AIServiceError as exc:
        logger.warning("Case analysis retry failed case_id=%s error=%r", case.case_id, exc)
        case.analysis_status = "failed"
        session.commit()
        return serialize_case(session, case) | {"clarifying_questions": intake_questions(case.clarifying_qa or [])}
    case.ai_legal_summary = analysis["legal_summary"]
    case.severity = analysis["severity"]
    case.analysis_status = "complete"
    case.updated_at = now()
    session.commit()
    session.refresh(case)
    return serialize_case(session, case) | {"clarifying_questions": intake_questions(case.clarifying_qa or [])}


@app.get("/api/cases/{identifier}")
@limiter.limit("30/hour")
def get_case(request: Request, identifier: str, session: Session = Depends(get_db)) -> dict[str, Any]:
    token = bearer_token(request.headers.get("authorization"))
    survivor_session = session.get(CaseSession, token)
    if not survivor_session or not survivor_session.is_active or survivor_session.expires_at <= now() or survivor_session.case_id != identifier.upper():
        raise HTTPException(401, "Invalid or inactive session")
    case = session.get(Case, identifier.upper())
    if not case:
        raise HTTPException(404, "Case not found")
    return serialize_case(session, case)


@app.post("/api/cases/{identifier}/clarify")
async def clarify(identifier: str, payload: ClarifyRequest, session: Session = Depends(get_db), service: OpenRouterAIService = Depends(ai_service)):
    case = session.get(Case, identifier.upper())
    if not case:
        raise HTTPException(404, "Case not found")
    qa = list(case.clarifying_qa or [])
    if len(qa) >= len(INTAKE_QUESTIONS):
        raise HTTPException(409, "The five-question intake is complete")
    qa.append({"question": payload.question.strip(), "answer": payload.answer.strip(), "answered_at": now().isoformat()})
    cache_key = (case.case_id, payload.question.strip(), payload.answer.strip())
    analysis = case_analysis_cache.get(cache_key)
    if analysis is None:
        try:
            analysis = await service.analyze_report(case.category, case.initial_report, qa)
        except AIServiceError as exc:
            logger.warning("Clarification analysis failed case_id=%s error=%r", case.case_id, exc)
            case.clarifying_qa = qa
            case.analysis_status = "failed"
            session.commit()
            return {"message": "Your answer was saved. Legal analysis is temporarily unavailable.", "next_questions": intake_questions(qa), "clarifying_qa": qa, "ai_legal_summary": case.ai_legal_summary, "severity": case.severity, "analysis_status": case.analysis_status}
        case_analysis_cache[cache_key] = analysis
    case.clarifying_qa = qa
    case.ai_legal_summary = analysis["legal_summary"]
    case.severity = analysis["severity"]
    case.analysis_status = "complete"
    case.updated_at = now()
    session.commit()
    return {"message": "Thank you for sharing that. You can take this one step at a time.", "next_questions": intake_questions(qa), "clarifying_qa": qa, "ai_legal_summary": case.ai_legal_summary, "severity": case.severity}


@app.post("/api/cases/{identifier}/evidence")
@limiter.limit("30/hour")
async def upload_evidence(request: Request, identifier: str, file: UploadFile = File(...), description: str = Form(default=""), incident_date: date | None = Form(default=None), session: Session = Depends(get_db), service: OpenRouterAIService = Depends(ai_service), storage: ObjectStorage = Depends(storage_service), regenerate_timeline: bool = Query(default=True)) -> dict[str, Any]:
    case = session.get(Case, identifier.upper())
    if not case:
        raise HTTPException(404, "Case not found")
    if not file.content_type or file.content_type not in ALLOWED_EVIDENCE_TYPES:
        raise HTTPException(415, "Unsupported evidence type")
    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(413, f"Maximum file size is {settings.max_upload_bytes // (1024 * 1024)}MB")
    if not has_valid_file_signature(content, file.content_type):
        raise HTTPException(415, "Evidence content does not match its declared file type")
    object_key = f"{case.case_id}/{uuid.uuid4().hex}"
    try:
        storage.put_encrypted(object_key, content, file.content_type)
    except Exception as exc:
        raise HTTPException(503, "Evidence storage is unavailable") from exc
    item = Evidence(case_id=case.case_id, object_key=object_key, original_name=file.filename or "evidence", file_type=file.content_type, size=len(content), integrity_hash=hashlib.sha256(content).hexdigest(), description=description.strip() or None, incident_date=incident_date)
    session.add(item)
    session.flush()
    # Persist the evidence independently of optional timeline generation.
    session.commit()
    result = {"evidence": evidence_json(item), "timeline": case.timeline or [], "timeline_summary": ""}
    if regenerate_timeline:
        result |= await regenerate_timeline_for_case(case, session, service)
    return result


async def regenerate_timeline_for_case(case: Case, session: Session, service: OpenRouterAIService) -> dict[str, Any]:
    metadata = [evidence_json(existing) for existing in case.evidence]
    try:
        generated = await service.build_timeline(metadata)
    except AIServiceError as exc:
        logger.warning("Evidence timeline generation failed case_id=%s error=%r", case.case_id, exc)
        # Evidence must still appear in the vault when optional AI enrichment is down.
        case.timeline = [
            {
                "date": (item.incident_date or item.uploaded_at or now()).isoformat(),
                "summary": item.description or f"Evidence added: {item.original_name}",
                "evidence_ids": [item.id],
                "type": "Evidence",
            }
            for item in case.evidence
        ]
        case.updated_at = now()
        session.commit()
        return {"timeline": case.timeline, "timeline_summary": "", "analysis_status": "unavailable"}
    case.timeline = generated["timeline"]
    case.updated_at = now()
    session.commit()
    return {"timeline": case.timeline, "timeline_summary": generated["summary"], "analysis_status": "complete"}


@app.post("/api/cases/{identifier}/timeline")
@limiter.limit("30/hour")
async def regenerate_timeline(request: Request, identifier: str, session: Session = Depends(get_db), service: OpenRouterAIService = Depends(ai_service)) -> dict[str, Any]:
    case = session.get(Case, identifier.upper())
    if not case:
        raise HTTPException(404, "Case not found")
    return await regenerate_timeline_for_case(case, session, service)


def require_survivor_case(request: Request, identifier: str, session: Session) -> Case:
    authorization = request.headers.get("authorization")
    if not authorization:
        if not session.get(Case, identifier.upper()):
            raise HTTPException(404, "Evidence not found")
        raise HTTPException(401, "Authentication required")
    token = bearer_token(authorization)
    record = session.get(CaseSession, token)
    if not record or not record.is_active or record.expires_at <= now() or record.case_id != identifier.upper():
        raise HTTPException(401, "Invalid or inactive session")
    return record.case


@app.get("/api/cases/{identifier}/evidence/{evidence_id}")
@limiter.limit("30/hour")
def download_evidence(request: Request, identifier: str, evidence_id: int, session: Session = Depends(get_db), storage: ObjectStorage = Depends(storage_service)) -> StreamingResponse:
    require_survivor_case(request, identifier, session)
    item = session.scalar(select(Evidence).where(Evidence.case_id == identifier.upper(), Evidence.id == evidence_id))
    if not item:
        raise HTTPException(404, "Evidence not found")
    try:
        content = storage.get_decrypted(item.object_key)
    except Exception as exc:
        raise HTTPException(404, "Evidence file is unavailable") from exc
    return StreamingResponse(iter([content]), media_type=item.file_type, headers={"Content-Disposition": f'attachment; filename="{item.original_name}"', "X-Content-SHA256": item.integrity_hash})


@app.get("/api/cases/{identifier}/evidence/{evidence_id}/url")
@limiter.limit("30/hour")
def evidence_url(request: Request, identifier: str, evidence_id: int, session: Session = Depends(get_db), storage: ObjectStorage = Depends(storage_service)) -> dict[str, Any]:
    require_survivor_case(request, identifier, session)
    item = session.scalar(select(Evidence).where(Evidence.case_id == identifier.upper(), Evidence.id == evidence_id))
    if not item:
        raise HTTPException(404, "Evidence not found")
    try:
        url = storage.presigned_url(item.object_key)
    except Exception as exc:
        raise HTTPException(503, "Evidence storage is unavailable") from exc
    return {"url": url, "expires_in": 300, "encrypted": True, "download_endpoint": f"/api/cases/{identifier.upper()}/evidence/{evidence_id}"}


@app.patch("/api/cases/{identifier}/status")
def update_status(identifier: str, payload: StatusUpdate, session: Session = Depends(get_db)) -> dict[str, str]:
    case = session.get(Case, identifier.upper())
    if not case:
        raise HTTPException(404, "Case not found")
    case.status = payload.status
    case.updated_at = now()
    session.commit()
    return {"case_id": case.case_id, "status": case.status}


@app.get("/api/cases/{identifier}/matches")
@limiter.limit("30/hour")
def get_matches(request: Request, identifier: str, case: Case = Depends(current_case), session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    if case.case_id != identifier.upper():
        raise HTTPException(403, "Case session does not match this case")
    return match_case(session, case)


@app.post("/api/cases/{identifier}/referrals")
def create_referral(identifier: str, payload: ReferralCreate, case: Case = Depends(current_case), session: Session = Depends(get_db)) -> dict[str, Any]:
    if case.case_id != identifier.upper():
        raise HTTPException(403, "Case session does not match this case")
    if not payload.consent_confirmed:
        raise HTTPException(400, "Explicit consent confirmation is required")
    organization = session.get(Organization, payload.ngo_id)
    if not organization or not session.scalar(select(CaseMatch).where(CaseMatch.case_id == case.case_id, CaseMatch.organization_id == payload.ngo_id)):
        raise HTTPException(404, "NGO is not a relevant match for this case")
    evidence_ids = {item.id for item in case.evidence}
    if payload.includes_evidence and any(item not in evidence_ids for item in payload.evidence_refs):
        raise HTTPException(400, "Evidence reference does not belong to this case")
    referral = Referral(id=str(uuid.uuid4()), case_id=case.case_id, ngo_id=organization.id, consent_scope=payload.consent_scope, submitted_message=(payload.submitted_message or "").strip() or None, consent_confirmed=True, includes_evidence=payload.includes_evidence, evidence_refs=payload.evidence_refs if payload.includes_evidence else [], status="draft")
    session.add(referral)
    session.flush()
    transition(referral, "requested", "survivor", "consent_requested", session)
    session.commit()
    return referral_json(referral)


@app.get("/api/cases/{identifier}/referrals")
def list_case_referrals(identifier: str, case: Case = Depends(current_case), session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    if case.case_id != identifier.upper():
        raise HTTPException(403, "Case session does not match this case")
    return [referral_json(item) for item in session.scalars(select(Referral).where(Referral.case_id == case.case_id).order_by(Referral.created_at.desc())).all()]


@app.get("/api/cases/{identifier}/referrals/{referral_id}")
def get_case_referral(identifier: str, referral_id: str, case: Case = Depends(current_case), session: Session = Depends(get_db)) -> dict[str, Any]:
    if case.case_id != identifier.upper():
        raise HTTPException(403, "Case session does not match this case")
    referral = session.scalar(select(Referral).where(Referral.id == referral_id, Referral.case_id == case.case_id))
    if not referral:
        raise HTTPException(404, "Referral not found")
    return referral_json(referral)


@app.post("/api/admin/ngo-accounts", dependencies=[Depends(require_admin)])
def create_ngo_account(payload: NGOAccountCreate, session: Session = Depends(get_db)) -> dict[str, Any]:
    organization = session.get(Organization, payload.ngo_id)
    if not organization:
        raise HTTPException(404, "NGO not found")
    if organization.account:
        raise HTTPException(409, "NGO account already exists")
    token = secrets.token_urlsafe(32)
    account = NGOAccount(ngo_id=organization.id, subscription_tier=payload.subscription_tier, billing_status=payload.billing_status, commission_agreement=payload.commission_agreement, api_token_hash=token_hash(token))
    session.add(account)
    session.commit()
    return {"ngo_id": account.ngo_id, "subscription_tier": account.subscription_tier, "billing_status": account.billing_status, "commission_agreement": account.commission_agreement, "token": token}


@app.post("/api/ngo/registrations")
def register_ngo(payload: NGORegistration, session: Session = Depends(get_db)) -> dict[str, Any]:
    existing = session.scalar(select(Organization).where(func.lower(Organization.name) == payload.name.strip().lower()))
    if existing:
        raise HTTPException(409, "An NGO with this name already exists")
    try:
        categories = normalize_categories(payload.categories)
        districts = normalize_districts(payload.districts)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    token = secrets.token_urlsafe(32)
    organization = Organization(name=payload.name.strip(), categories=categories, districts=districts, contact_phone=payload.contact_phone.strip(), contact_email=payload.contact_email, website=payload.website, description=payload.description.strip(), verification_status="pending")
    session.add(organization)
    session.commit()
    session.refresh(organization)
    session.add(NGOAccount(ngo_id=organization.id, subscription_tier="free", billing_status="active", commission_agreement=False, api_token_hash=token_hash(token)))
    session.add(NGOVerificationLog(ngo_id=organization.id, actor_id="ngo applicant", action="submitted", note="Application submitted"))
    session.commit()
    return organization_json(organization, token) | {"token_status": "pending_approval"}


@app.post("/api/ngo/registrations/upload")
async def register_ngo_with_document(
    name: str = Form(...), categories: str = Form(...), districts: str = Form(...), contact_phone: str = Form(...),
    contact_email: str | None = Form(default=None), description: str = Form(...), document: UploadFile = File(...),
    session: Session = Depends(get_db), storage: ObjectStorage = Depends(storage_service),
) -> dict[str, Any]:
    payload = NGORegistration(name=name, categories=[item.strip() for item in categories.split(",") if item.strip()], districts=[item.strip() for item in districts.split(",") if item.strip()], contact_phone=contact_phone, contact_email=contact_email, description=description)
    result = register_ngo(payload, session)
    content = await document.read()
    if len(content) > settings.max_upload_bytes or not has_valid_file_signature(content, document.content_type or ""):
        raise HTTPException(400, "Unsupported or invalid verification document")
    key = f"ngo-documents/{result['id']}/{uuid.uuid4()}"
    storage.put_encrypted(key, content, document.content_type or "application/octet-stream")
    session.add(NGODocument(ngo_id=result["id"], object_key=key, original_name=document.filename or "document", doc_type="registration", status="pending"))
    session.commit()
    return result | {"document_uploaded": True, "token_status": "pending_approval"}


@app.get("/api/admin/ngos", dependencies=[Depends(require_admin)])
def list_admin_ngos(status: str | None = Query(default=None), session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    query = select(Organization).order_by(
        (Organization.verification_status == "pending").desc(),
        Organization.created_at.desc(),
        Organization.name.asc(),
    )
    if status:
        query = query.where(Organization.verification_status == status)
    return [organization_json(item) for item in session.scalars(query).all()]


@app.post("/api/admin/ngos/{ngo_id}/approve", dependencies=[Depends(require_admin)])
def approve_ngo(ngo_id: int, payload: NGOReview, session: Session = Depends(get_db)) -> dict[str, Any]:
    organization = session.get(Organization, ngo_id)
    if not organization:
        raise HTTPException(404, "NGO not found")
    organization.verification_status = "approved"
    organization.verification_note = payload.note
    session.add(NGOVerificationLog(ngo_id=ngo_id, actor_id="admin", action="approved", note=payload.note))
    token = None
    if not organization.account:
        token = secrets.token_urlsafe(32)
        session.add(NGOAccount(ngo_id=organization.id, subscription_tier="free", billing_status="active", commission_agreement=False, api_token_hash=token_hash(token)))
    backfill_organization_matches(session, organization)
    session.commit()
    session.refresh(organization)
    result = organization_json(organization, token)
    result["token_status"] = "active"
    result["token_notice"] = "This access token is active now. Store it securely; it cannot be recovered later."
    return result


@app.post("/api/admin/ngos/{ngo_id}/reject", dependencies=[Depends(require_admin)])
def reject_ngo(ngo_id: int, payload: NGOReview, session: Session = Depends(get_db)) -> dict[str, Any]:
    organization = session.get(Organization, ngo_id)
    if not organization:
        raise HTTPException(404, "NGO not found")
    organization.verification_status = "rejected"
    organization.verification_note = payload.note
    session.add(NGOVerificationLog(ngo_id=ngo_id, actor_id="admin", action="declined", note=payload.note))
    session.commit()
    return organization_json(organization)


@app.post("/api/admin/ngos/{ngo_id}/resend", dependencies=[Depends(require_admin)])
def request_ngo_resend(ngo_id: int, payload: NGOReview, session: Session = Depends(get_db)) -> dict[str, Any]:
    organization = session.get(Organization, ngo_id)
    if not organization:
        raise HTTPException(404, "NGO not found")
    organization.verification_status = "resend_requested"
    organization.verification_note = payload.note
    session.add(NGOVerificationLog(ngo_id=ngo_id, actor_id="admin", action="resend_requested", note=payload.note))
    session.commit()
    return organization_json(organization)


@app.get("/api/admin/ngos/{ngo_id}/verification-log", dependencies=[Depends(require_admin)])
def ngo_verification_log(ngo_id: int, session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [{"id": item.id, "actor_id": item.actor_id, "action": item.action, "note": item.note, "created_at": item.created_at.isoformat() if item.created_at else None} for item in session.scalars(select(NGOVerificationLog).where(NGOVerificationLog.ngo_id == ngo_id).order_by(NGOVerificationLog.created_at.asc())).all()]


@app.get("/api/admin/overview", dependencies=[Depends(require_admin)])
def admin_overview(session: Session = Depends(get_db)) -> dict[str, Any]:
    cases = session.scalars(select(Case)).all()
    referrals = session.scalars(select(Referral)).all()
    ngos_pending = session.scalar(select(func.count(Organization.id)).where(Organization.verification_status.in_(["pending", "resend_requested"]))) or 0
    crowdfunding_pending = session.scalar(select(func.count(CrowdfundingRequest.id)).where(CrowdfundingRequest.status == "pending_review")) or 0
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    donations = session.scalars(select(PlatformDonation).where(PlatformDonation.payment_status == "completed", PlatformDonation.created_at >= month_start)).all()
    return {"open_cases": sum(1 for item in cases if item.status != "resolved"), "urgent_unassigned": sum(1 for item in cases if (item.emergency_requested or item.severity == "urgent") and not any(ref.case_id == item.case_id and ref.status in {"forwarded", "acknowledged"} for ref in referrals)), "pending_ngo_applications": int(ngos_pending), "pending_crowdfunding_requests": int(crowdfunding_pending), "pending_referrals": sum(1 for item in referrals if item.status in {"requested", "admin_review"}), "donations_this_month": str(sum((item.amount for item in donations), Decimal("0"))), "recent_activity": [{"case_id": item.case_id, "status": item.status, "updated_at": item.updated_at.isoformat() if item.updated_at else None} for item in sorted(cases, key=lambda value: value.updated_at or value.created_at, reverse=True)[:8]]}


@app.get("/api/admin/cases", dependencies=[Depends(require_admin)])
def list_admin_cases(status: str | None = Query(default=None), severity: str | None = Query(default=None), category: str | None = Query(default=None), has_crowdfunding: bool | None = Query(default=None), from_date: date | None = Query(default=None), to_date: date | None = Query(default=None), session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    query = select(Case).order_by(Case.emergency_requested.desc(), (Case.severity == "urgent").desc(), Case.created_at.desc())
    if status:
        query = query.where(Case.status == status)
    if severity:
        query = query.where(Case.severity == severity)
    if category:
        query = query.where(Case.category == category)
    if has_crowdfunding is True:
        query = query.join(CrowdfundingRequest, CrowdfundingRequest.case_id == Case.case_id)
    if has_crowdfunding is False:
        query = query.outerjoin(CrowdfundingRequest, CrowdfundingRequest.case_id == Case.case_id).where(CrowdfundingRequest.id.is_(None))
    if from_date:
        query = query.where(Case.created_at >= datetime.combine(from_date, datetime.min.time(), tzinfo=timezone.utc))
    if to_date:
        query = query.where(Case.created_at < datetime.combine(to_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc))
    return [serialize_case(session, item) for item in session.scalars(query).all()]


@app.get("/api/admin/cases/{identifier}", dependencies=[Depends(require_admin)])
def get_admin_case(identifier: str, session: Session = Depends(get_db)) -> dict[str, Any]:
    case = session.get(Case, identifier.upper())
    if not case:
        raise HTTPException(404, "Case not found")
    referrals = session.scalars(select(Referral).where(Referral.case_id == case.case_id).order_by(Referral.created_at.asc())).all()
    requests = session.scalars(select(CrowdfundingRequest).where(CrowdfundingRequest.case_id == case.case_id)).all()
    campaigns = session.scalars(select(CrowdfundingCampaign).where(CrowdfundingCampaign.case_id == case.case_id)).all()
    return serialize_case(session, case) | {"referrals": [referral_json(item, include_case=True) | {"audit": referral_audit_json(item)} for item in referrals], "crowdfunding_requests": [{"id": item.id, "status": item.status, "requested_amount": str(item.requested_amount), "explanation": item.explanation, "review_note": item.review_note} for item in requests], "campaigns": [campaign_json(item) for item in campaigns]}


@app.patch("/api/admin/cases/{identifier}/status", dependencies=[Depends(require_admin)])
def admin_update_case_status(identifier: str, payload: StatusUpdate, session: Session = Depends(get_db)) -> dict[str, str]:
    case = session.get(Case, identifier.upper())
    if not case:
        raise HTTPException(404, "Case not found")
    case.status = payload.status
    case.updated_at = now()
    session.commit()
    return {"case_id": case.case_id, "status": case.status}


@app.get("/api/admin/ngo-activity", dependencies=[Depends(require_admin)])
def admin_ngo_activity(session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    organizations = session.scalars(select(Organization).order_by(Organization.name.asc())).all()
    result = []
    for organization in organizations:
        referrals = session.scalars(select(Referral).where(Referral.ngo_id == organization.id)).all()
        result.append({"ngo_id": organization.id, "ngo_name": organization.name, "verification_status": organization.verification_status, "total_referrals": len(referrals), "pending": sum(1 for item in referrals if item.case_status == "pending"), "processing": sum(1 for item in referrals if item.case_status == "processing"), "completed": sum(1 for item in referrals if item.case_status == "completed"), "last_activity": max((item.updated_at for item in referrals if item.updated_at), default=None).isoformat() if any(item.updated_at for item in referrals) else None})
    return result


@app.get("/api/admin/settings", dependencies=[Depends(require_admin)])
def admin_settings() -> dict[str, Any]:
    return {"commission_enabled": settings.commission_enabled, "rate_limit": settings.rate_limit, "max_upload_bytes": settings.max_upload_bytes, "allowed_origins": settings.allowed_origins}


@app.get("/api/admin/referrals", dependencies=[Depends(require_admin)])
def list_admin_referrals(session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [referral_json(item, include_case=True) for item in session.scalars(select(Referral).where(Referral.status.in_(["requested", "admin_review"])).order_by(Referral.created_at.asc())).all()]


@app.get("/api/admin/referrals/{referral_id}", dependencies=[Depends(require_admin)])
def get_admin_referral(referral_id: str, session: Session = Depends(get_db)) -> dict[str, Any]:
    referral = session.get(Referral, referral_id)
    if not referral:
        raise HTTPException(404, "Referral not found")
    return referral_json(referral, include_case=True) | {"audit": referral_audit_json(referral)}


def referral_audit_json(referral: Referral) -> list[dict[str, Any]]:
    return [{"id": item.id, "actor_id": item.actor_id, "action": item.action, "from_status": item.from_status, "to_status": item.to_status, "note": item.note, "changed_at": item.changed_at.isoformat() if item.changed_at else None} for item in referral.audit_log]


@app.get("/api/admin/referrals/{referral_id}/audit", dependencies=[Depends(require_admin)])
def get_referral_audit(referral_id: str, session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    referral = session.get(Referral, referral_id)
    if not referral:
        raise HTTPException(404, "Referral not found")
    return referral_audit_json(referral)


@app.post("/api/admin/referrals/{referral_id}/approve", dependencies=[Depends(require_admin)])
def approve_referral(referral_id: str, session: Session = Depends(get_db)) -> dict[str, Any]:
    referral = session.get(Referral, referral_id)
    if not referral:
        raise HTTPException(404, "Referral not found")
    if referral.status == "requested":
        transition(referral, "admin_review", "admin", "review_started", session)
    transition(referral, "forwarded", "admin", "approved_and_forwarded", session)
    referral.case.status = "ngo_contacted"
    referral.case.updated_at = now()
    session.commit()
    return referral_json(referral)


@app.post("/api/admin/referrals/{referral_id}/reject", dependencies=[Depends(require_admin)])
def reject_referral(referral_id: str, payload: ReferralReason, session: Session = Depends(get_db)) -> dict[str, Any]:
    referral = session.get(Referral, referral_id)
    if not referral:
        raise HTTPException(404, "Referral not found")
    if referral.status == "requested":
        transition(referral, "admin_review", "admin", "review_started", session)
    if referral.status != "admin_review":
        raise HTTPException(409, "Referral is not awaiting admin review")
    referral.rejection_reason = payload.reason.strip()
    transition(referral, "closed", "admin", "rejected", session, referral.rejection_reason)
    session.commit()
    return referral_json(referral)


@app.post("/api/admin/referrals/{referral_id}/reassign", dependencies=[Depends(require_admin)])
def reassign_referral(referral_id: str, payload: ReferralReassign, session: Session = Depends(get_db)) -> dict[str, Any]:
    referral = session.get(Referral, referral_id)
    organization = session.get(Organization, payload.ngo_id)
    if not referral or not organization:
        raise HTTPException(404, "Referral or NGO not found")
    if not session.scalar(select(CaseMatch).where(CaseMatch.case_id == referral.case_id, CaseMatch.organization_id == payload.ngo_id)):
        raise HTTPException(404, "NGO is not a relevant match for this case")
    if referral.status == "requested":
        transition(referral, "admin_review", "admin", "review_started", session)
    if referral.status != "admin_review":
        raise HTTPException(409, "Referral is not awaiting admin review")
    referral.ngo_id = payload.ngo_id
    audit_referral(session, referral, "admin", "reassigned", referral.status, payload.reason.strip())
    session.commit()
    return referral_json(referral)


@app.get("/api/ngo/dashboard")
def ngo_dashboard(account: NGOAccount = Depends(current_ngo), session: Session = Depends(get_db)) -> dict[str, Any]:
    # Safety referral handling is payment-blind; paid tier only affects analytics.
    referrals = session.scalars(select(Referral).join(Case, Referral.case_id == Case.case_id).where(Referral.ngo_id == account.ngo_id, Referral.status.in_(["forwarded", "acknowledged", "closed"])).order_by(Case.emergency_requested.desc(), (Case.severity == "urgent").desc(), Referral.created_at.desc())).all()
    total = session.scalar(select(func.count(CaseMatch.case_id)).where(CaseMatch.organization_id == account.ngo_id)) or 0
    categories = session.execute(select(Case.category, func.count(Case.case_id)).join(CaseMatch, Case.case_id == CaseMatch.case_id).where(CaseMatch.organization_id == account.ngo_id).group_by(Case.category)).all()
    districts = session.execute(select(Case.district, func.count(Case.case_id)).join(CaseMatch, Case.case_id == CaseMatch.case_id).where(CaseMatch.organization_id == account.ngo_id).group_by(Case.district)).all()
    matched_cases = session.scalars(select(Case).join(CaseMatch, Case.case_id == CaseMatch.case_id).where(CaseMatch.organization_id == account.ngo_id)).all()
    response_hours = [max(0.0, (item.updated_at - item.created_at).total_seconds() / 3600) for item in matched_cases if item.created_at and item.updated_at]
    commissions = session.scalars(select(CommissionRecord).where(CommissionRecord.ngo_id == account.ngo_id).order_by(CommissionRecord.created_at.desc())).all()
    metrics = {"matched_cases": total, "category_breakdown": {key: count for key, count in categories}, "district_breakdown": {key: count for key, count in districts}, "average_response_time_hours": round(sum(response_hours) / len(response_hours), 2) if response_hours else None} if account.subscription_tier == "paid" else None
    return {"ngo_id": account.ngo_id, "organization": organization_json(account.organization), "subscription_tier": account.subscription_tier, "billing_status": account.billing_status, "metrics": metrics, "emergency_count": sum(1 for item in referrals if getattr(item.case, "emergency_requested", False) or item.case.severity == "urgent"), "referrals": [referral_json(item) for item in referrals], "commissions": [commission_json(item) for item in commissions]}


@app.get("/api/ngo/profile")
def get_ngo_profile(account: NGOAccount = Depends(current_ngo)) -> dict[str, Any]:
    return organization_json(account.organization)


@app.get("/api/ngo/documents")
def list_ngo_documents(account: NGOAccount = Depends(current_ngo), session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    documents = session.scalars(select(NGODocument).where(NGODocument.ngo_id == account.ngo_id).order_by(NGODocument.uploaded_at.desc())).all()
    return [{"id": item.id, "name": item.original_name, "type": item.doc_type, "status": item.status, "uploaded_at": item.uploaded_at.isoformat() if item.uploaded_at else None} for item in documents]


@app.get("/api/ngo/conversations")
def list_ngo_conversations(account: NGOAccount = Depends(current_ngo), session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    referrals = session.scalars(select(Referral).where(Referral.ngo_id == account.ngo_id, Referral.status.in_(["forwarded", "acknowledged"]))).all()
    conversations: list[dict[str, Any]] = []
    for referral in referrals:
        messages = visible_case_messages(referral.case_id, "ngo", str(account.ngo_id), account.ngo_id, session)
        last = messages[-1] if messages else None
        unread = 0
        for message in messages:
            if message.sender_type == "ngo":
                continue
            seen = session.scalar(select(CaseMessageRead.id).where(CaseMessageRead.message_id == message.id, CaseMessageRead.participant_type == "ngo", CaseMessageRead.participant_id == str(account.ngo_id)))
            unread += int(seen is None)
        conversations.append({"referral_id": referral.id, "case_id": referral.case_id, "case_status": referral.case_status, "last_message": last.message if last else None, "last_message_at": last.sent_at.isoformat() if last and last.sent_at else None, "last_sender_type": last.sender_type if last else None, "unread_count": unread})
    return sorted(conversations, key=lambda item: item["last_message_at"] or "", reverse=True)


@app.patch("/api/ngo/profile")
def update_ngo_profile(payload: NGOProfileUpdate, account: NGOAccount = Depends(current_ngo), session: Session = Depends(get_db)) -> dict[str, Any]:
    organization = account.organization
    try:
        categories = normalize_categories(payload.categories) if payload.categories is not None else None
        districts = normalize_districts(payload.districts) if payload.districts is not None else None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    for field in ("categories", "districts", "contact_phone", "contact_email", "website", "description"):
        value = getattr(payload, field)
        if field == "categories":
            value = categories
        elif field == "districts":
            value = districts
        if value is not None:
            setattr(organization, field, value)
    backfill_organization_matches(session, organization)
    session.commit()
    session.refresh(organization)
    return organization_json(organization)


@app.get("/api/ngo/referrals")
def list_ngo_referrals(account: NGOAccount = Depends(current_ngo), session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    referrals = session.scalars(select(Referral).join(Case, Referral.case_id == Case.case_id).where(Referral.ngo_id == account.ngo_id, Referral.status.in_(["forwarded", "acknowledged", "closed"])).order_by(Case.emergency_requested.desc(), (Case.severity == "urgent").desc(), Referral.created_at.desc())).all()
    return [referral_json(item) for item in referrals]


@app.get("/api/ngo/referrals/{referral_id}")
def get_ngo_referral(referral_id: str, account: NGOAccount = Depends(current_ngo), session: Session = Depends(get_db)) -> dict[str, Any]:
    referral = session.scalar(select(Referral).where(Referral.id == referral_id, Referral.ngo_id == account.ngo_id, Referral.status.in_(["forwarded", "acknowledged", "closed"])))
    if not referral or referral.ngo_id != account.ngo_id or referral.status not in {"forwarded", "acknowledged", "closed"}:
        raise HTTPException(404, "Forwarded referral not found")
    return referral_json(referral, include_case=True)


@app.get("/api/ngo/referrals/{referral_id}/evidence/{evidence_id}")
def download_ngo_evidence(referral_id: str, evidence_id: int, account: NGOAccount = Depends(current_ngo), session: Session = Depends(get_db), storage: ObjectStorage = Depends(storage_service)) -> StreamingResponse:
    referral = session.scalar(select(Referral).where(Referral.id == referral_id, Referral.ngo_id == account.ngo_id, Referral.status.in_(["forwarded", "acknowledged", "closed"])))
    if not referral or referral.ngo_id != account.ngo_id or referral.status not in {"forwarded", "acknowledged", "closed"}:
        raise HTTPException(404, "Forwarded referral not found")
    if not getattr(referral, "includes_evidence", False) or (referral.evidence_refs and evidence_id not in referral.evidence_refs):
        raise HTTPException(403, "Evidence is outside the granted consent scope")
    item = session.scalar(select(Evidence).where(Evidence.case_id == referral.case_id, Evidence.id == evidence_id))
    if not item:
        raise HTTPException(404, "Evidence not found")
    try:
        content = storage.get_decrypted(item.object_key)
    except Exception as exc:
        raise HTTPException(404, "Evidence file is unavailable") from exc
    return StreamingResponse(iter([content]), media_type=item.file_type, headers={"Content-Disposition": f'attachment; filename="{item.original_name}"', "X-Content-SHA256": item.integrity_hash})


@app.get("/api/admin/cases/{identifier}/evidence/{evidence_id}", dependencies=[Depends(require_admin)])
def download_admin_evidence(identifier: str, evidence_id: int, session: Session = Depends(get_db), storage: ObjectStorage = Depends(storage_service)) -> StreamingResponse:
    item = session.scalar(select(Evidence).where(Evidence.case_id == identifier.upper(), Evidence.id == evidence_id))
    if not item:
        raise HTTPException(404, "Evidence not found")
    try:
        content = storage.get_decrypted(item.object_key)
    except Exception as exc:
        raise HTTPException(404, "Evidence file is unavailable") from exc
    return StreamingResponse(iter([content]), media_type=item.file_type, headers={"Content-Disposition": f'attachment; filename="{item.original_name}"', "X-Content-SHA256": item.integrity_hash})


@app.post("/api/ngo/referrals/{referral_id}/acknowledge")
def acknowledge_referral(referral_id: str, account: NGOAccount = Depends(current_ngo), session: Session = Depends(get_db)) -> dict[str, Any]:
    referral = session.scalar(select(Referral).where(Referral.id == referral_id, Referral.ngo_id == account.ngo_id, Referral.status == "forwarded"))
    if not referral:
        raise HTTPException(404, "Forwarded referral not found")
    transition(referral, "acknowledged", f"ngo:{account.ngo_id}", "acknowledge", session)
    session.commit()
    return referral_json(referral)


@app.post("/api/ngo/referrals/{referral_id}/refuse")
def refuse_referral(referral_id: str, payload: ReferralReason, account: NGOAccount = Depends(current_ngo), session: Session = Depends(get_db)) -> dict[str, Any]:
    referral = session.scalar(select(Referral).where(Referral.id == referral_id, Referral.ngo_id == account.ngo_id, Referral.status == "forwarded"))
    if not referral:
        raise HTTPException(404, "Forwarded referral not found")
    referral.rejection_reason = payload.reason.strip()
    transition(referral, "closed", f"ngo:{account.ngo_id}", "refuse", session, payload.reason.strip())
    session.commit()
    return referral_json(referral)


@app.patch("/api/ngo/referrals/{referral_id}/support-status")
def update_referral_support(referral_id: str, payload: SupportUpdate, account: NGOAccount = Depends(current_ngo), session: Session = Depends(get_db)) -> dict[str, Any]:
    referral = session.scalar(select(Referral).where(Referral.id == referral_id, Referral.ngo_id == account.ngo_id, Referral.status == "acknowledged"))
    if not referral:
        raise HTTPException(404, "Acknowledged referral not found")
    referral.support_status = payload.support_status.strip()
    session.commit()
    return referral_json(referral)


@app.patch("/api/ngo/referrals/{referral_id}/case-status")
def update_referral_case_status(referral_id: str, payload: CaseStatusUpdate, account: NGOAccount = Depends(current_ngo), session: Session = Depends(get_db)) -> dict[str, Any]:
    referral = session.scalar(select(Referral).where(Referral.id == referral_id, Referral.ngo_id == account.ngo_id, Referral.status.in_(["forwarded", "acknowledged"])))
    if not referral:
        raise HTTPException(404, "Active referral not found")
    previous = referral.case_status
    referral.case_status = payload.case_status
    referral.updated_at = now()
    session.add(CaseStatusLog(referral_id=referral.id, status=payload.case_status, actor_id=f"ngo:{account.ngo_id}", note=(payload.note or f"Changed from {previous}").strip()))
    session.commit()
    return referral_json(referral)


@app.get("/api/ngo/referrals/{referral_id}/notes")
def list_referral_notes(referral_id: str, account: NGOAccount = Depends(current_ngo), session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    referral = session.scalar(select(Referral).where(Referral.id == referral_id, Referral.ngo_id == account.ngo_id))
    if not referral:
        raise HTTPException(404, "Referral not found")
    return [note_json(item) for item in session.scalars(select(CaseNote).where(CaseNote.referral_id == referral_id, CaseNote.ngo_id == account.ngo_id).order_by(CaseNote.created_at.desc())).all()]


@app.post("/api/ngo/referrals/{referral_id}/notes")
def add_referral_note(referral_id: str, payload: CaseNoteCreate, account: NGOAccount = Depends(current_ngo), session: Session = Depends(get_db)) -> dict[str, Any]:
    referral = session.scalar(select(Referral).where(Referral.id == referral_id, Referral.ngo_id == account.ngo_id, Referral.status.in_(["forwarded", "acknowledged"])))
    if not referral:
        raise HTTPException(404, "Active referral not found")
    note = CaseNote(referral_id=referral.id, ngo_id=account.ngo_id, note=payload.note.strip())
    session.add(note)
    session.commit()
    session.refresh(note)
    return note_json(note)


@app.post("/api/ngo/commissions")
def create_commission(payload: CommissionCreate, account: NGOAccount = Depends(current_ngo), session: Session = Depends(get_db)) -> dict[str, Any]:
    commission_feature_enabled()
    if not account.commission_agreement:
        raise HTTPException(403, "Commission agreement is not active")
    case = session.get(Case, payload.case_id.upper())
    if not case or not session.scalar(select(CaseMatch).where(CaseMatch.case_id == case.case_id, CaseMatch.organization_id == account.ngo_id)):
        raise HTTPException(404, "Matched case not found")
    record = CommissionRecord(id=str(uuid.uuid4()), case_id=case.case_id, ngo_id=account.ngo_id, self_reported_outcome=payload.self_reported_outcome.strip(), commission_amount=payload.commission_amount, currency="NPR", status="pending")
    session.add(record)
    audit_commission(session, record, f"ngo:{account.ngo_id}", None, "Self-reported outcome submitted")
    session.commit()
    return commission_json(record)


def donation_json(item: PlatformDonation | CrowdfundingDonation) -> dict[str, Any]:
    return {
        "id": item.id, "donor_name": None if item.is_anonymous else item.donor_name,
        "donor_email": None if item.is_anonymous else getattr(item, "donor_email", None),
        "is_anonymous": item.is_anonymous, "amount": str(item.amount), "currency": item.currency,
        "message": item.message, "payment_status": item.payment_status,
        "payment_reference": item.payment_reference, "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def campaign_json(campaign: CrowdfundingCampaign) -> dict[str, Any]:
    return {
        "id": campaign.id, "case_id": campaign.case_id,
        "display_name": campaign.display_name or f"Survivor Case #{campaign.case_id}",
        "category": campaign.category, "description": campaign.description,
        "requested_amount": str(campaign.requested_amount), "amount_raised": str(campaign.amount_raised),
        "status": campaign.status, "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
    }


@app.post("/api/donations/platform")
def create_platform_donation(payload: DonationCreate, session: Session = Depends(get_db)) -> dict[str, Any]:
    item = PlatformDonation(id=str(uuid.uuid4()), donor_name=None if payload.is_anonymous else payload.donor_name, donor_email=None if payload.is_anonymous else payload.donor_email, is_anonymous=payload.is_anonymous, amount=payload.amount, currency=payload.currency, message=payload.message.strip() if payload.message else None, payment_status="pending")
    session.add(item)
    session.commit()
    session.refresh(item)
    return donation_json(item) | {"provider": "stub", "next_step": "Complete payment with the configured provider and call the payment callback."}


@app.post("/api/donations/platform/{donation_id}/callback")
def complete_platform_donation(donation_id: str, payload: PaymentCallback, session: Session = Depends(get_db)) -> dict[str, Any]:
    item = session.get(PlatformDonation, donation_id)
    if not item:
        raise HTTPException(404, "Donation not found")
    item.payment_status = payload.payment_status
    item.payment_reference = payload.payment_reference
    item.updated_at = now()
    session.commit()
    return donation_json(item)


@app.get("/api/crowdfunding")
def list_campaigns(session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [campaign_json(item) for item in session.scalars(select(CrowdfundingCampaign).where(CrowdfundingCampaign.status == "active").order_by(CrowdfundingCampaign.created_at.desc())).all()]


@app.get("/api/crowdfunding/{campaign_id}")
def get_campaign(campaign_id: str, session: Session = Depends(get_db)) -> dict[str, Any]:
    item = session.scalar(select(CrowdfundingCampaign).where(CrowdfundingCampaign.id == campaign_id, CrowdfundingCampaign.status == "active"))
    if not item:
        raise HTTPException(404, "Campaign not found")
    result = campaign_json(item)
    result["progress_percent"] = min(100, round(float(item.amount_raised or 0) / float(item.requested_amount) * 100)) if item.requested_amount else 0
    return result


@app.post("/api/crowdfunding/{campaign_id}/donations")
def create_campaign_donation(campaign_id: str, payload: DonationCreate, session: Session = Depends(get_db)) -> dict[str, Any]:
    campaign = session.scalar(select(CrowdfundingCampaign).where(CrowdfundingCampaign.id == campaign_id, CrowdfundingCampaign.status == "active"))
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    item = CrowdfundingDonation(id=str(uuid.uuid4()), campaign_id=campaign.id, donor_name=None if payload.is_anonymous else payload.donor_name, is_anonymous=payload.is_anonymous, amount=payload.amount, currency=payload.currency, message=payload.message.strip() if payload.message else None, payment_status="pending")
    session.add(item)
    session.commit()
    session.refresh(item)
    return donation_json(item) | {"provider": "stub"}


@app.post("/api/crowdfunding/donations/{donation_id}/callback")
def complete_campaign_donation(donation_id: str, payload: PaymentCallback, session: Session = Depends(get_db)) -> dict[str, Any]:
    item = session.get(CrowdfundingDonation, donation_id)
    if not item:
        raise HTTPException(404, "Donation not found")
    previous = item.payment_status
    item.payment_status = payload.payment_status
    item.payment_reference = payload.payment_reference
    if payload.payment_status == "completed" and previous != "completed":
        campaign = session.get(CrowdfundingCampaign, item.campaign_id)
        campaign.amount_raised = (campaign.amount_raised or 0) + item.amount
        campaign.updated_at = now()
    item.updated_at = now()
    session.commit()
    return donation_json(item)


@app.post("/api/cases/{identifier}/crowdfunding-requests")
def create_crowdfunding_request(identifier: str, payload: CrowdfundingCreate, case: Case = Depends(current_case), session: Session = Depends(get_db)) -> dict[str, Any]:
    if case.case_id != identifier.upper():
        raise HTTPException(403, "Case session does not match this case")
    if case.status not in {"ngo_contacted", "resolved"}:
        raise HTTPException(409, "Crowdfunding is available after NGO contact")
    request = CrowdfundingRequest(id=str(uuid.uuid4()), case_id=case.case_id, category=payload.category, explanation=payload.explanation.strip(), requested_amount=payload.requested_amount, target_date=payload.target_date, consent_public_display=payload.consent_public_display, status="pending_review")
    session.add(request)
    session.commit()
    return {"id": request.id, "case_id": request.case_id, "status": request.status, "consent_public_display": request.consent_public_display}


@app.get("/api/admin/crowdfunding-requests", dependencies=[Depends(require_admin)])
def list_crowdfunding_requests(session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [{"id": item.id, "case_id": item.case_id, "category": item.category, "explanation": item.explanation, "requested_amount": str(item.requested_amount), "target_date": item.target_date.isoformat() if item.target_date else None, "consent_public_display": item.consent_public_display, "status": item.status, "review_note": item.review_note, "severity": item.case.severity, "case_status": item.case.status} for item in session.scalars(select(CrowdfundingRequest).order_by(CrowdfundingRequest.created_at.asc())).all()]


@app.get("/api/admin/crowdfunding-campaigns", dependencies=[Depends(require_admin)])
def list_admin_campaigns(session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [campaign_json(item) for item in session.scalars(select(CrowdfundingCampaign).order_by(CrowdfundingCampaign.created_at.desc())).all()]


@app.post("/api/admin/crowdfunding-requests/{request_id}/approve", dependencies=[Depends(require_admin)])
def approve_crowdfunding(request_id: str, payload: CrowdfundingReview, session: Session = Depends(get_db)) -> dict[str, Any]:
    request = session.get(CrowdfundingRequest, request_id)
    if not request or request.status != "pending_review":
        raise HTTPException(404, "Crowdfunding request is not awaiting review")
    campaign = CrowdfundingCampaign(id=str(uuid.uuid4()), case_id=request.case_id, display_name=payload.display_name.strip() if payload.display_name else f"Survivor Case #{request.case_id}", category=request.category, description=(payload.description or request.explanation).strip(), requested_amount=request.requested_amount, amount_raised=0, status="active", approved_by="admin", approved_at=now())
    request.status = "approved"
    request.review_note = payload.note
    request.updated_at = now()
    session.add(campaign)
    session.commit()
    return campaign_json(campaign)


@app.post("/api/admin/crowdfunding-requests/{request_id}/reject", dependencies=[Depends(require_admin)])
def reject_crowdfunding(request_id: str, payload: CrowdfundingReview, session: Session = Depends(get_db)) -> dict[str, Any]:
    request = session.get(CrowdfundingRequest, request_id)
    if not request:
        raise HTTPException(404, "Crowdfunding request not found")
    request.status = "rejected"
    request.review_note = (payload.note or "Rejected during admin review").strip()
    request.updated_at = now()
    session.commit()
    return {"id": request.id, "status": request.status, "review_note": request.review_note}


@app.post("/api/admin/crowdfunding-requests/{request_id}/more-info", dependencies=[Depends(require_admin)])
def crowdfunding_more_info(request_id: str, payload: CrowdfundingReview, session: Session = Depends(get_db)) -> dict[str, Any]:
    request = session.get(CrowdfundingRequest, request_id)
    if not request:
        raise HTTPException(404, "Crowdfunding request not found")
    request.status = "more_info"
    request.review_note = (payload.note or "Please provide more information.").strip()
    request.updated_at = now()
    session.commit()
    return {"id": request.id, "status": request.status, "review_note": request.review_note}


@app.get("/api/admin/donations/export", dependencies=[Depends(require_admin)])
def export_donations(status: str | None = Query(default=None), donation_type: str | None = Query(default=None, pattern="^(platform|campaign)$"), from_date: date | None = Query(default=None), to_date: date | None = Query(default=None), session: Session = Depends(get_db)) -> StreamingResponse:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "type", "donor_name", "amount", "currency", "payment_status", "campaign_id", "created_at", "payment_reference"])
    for item in combined_donations(status, donation_type, from_date, to_date, session):
        writer.writerow([item["id"], item["type"], item["donor_name"], item["amount"], item["currency"], item["payment_status"], item["campaign_id"] or "platform donation", item["created_at"], item["payment_reference"]])
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=donations.csv"})


@app.get("/api/admin/donations", dependencies=[Depends(require_admin)])
def list_donations(status: str | None = Query(default=None), donation_type: str | None = Query(default=None, pattern="^(platform|campaign)$"), from_date: date | None = Query(default=None), to_date: date | None = Query(default=None), session: Session = Depends(get_db)) -> dict[str, Any]:
    items = combined_donations(status, donation_type, from_date, to_date, session)
    completed = [item for item in items if item["payment_status"] == "completed"]
    return {"items": items, "total_completed": str(sum((Decimal(item["amount"]) for item in completed), Decimal("0"))), "count": len(items)}


def combined_donations(status: str | None, donation_type: str | None, from_date: date | None, to_date: date | None, session: Session) -> list[dict[str, Any]]:
    start = datetime.combine(from_date, datetime.min.time(), tzinfo=timezone.utc) if from_date else None
    end = datetime.combine(to_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc) if to_date else None
    records: list[dict[str, Any]] = []
    if donation_type in (None, "platform"):
        query = select(PlatformDonation)
        if status: query = query.where(PlatformDonation.payment_status == status)
        if start: query = query.where(PlatformDonation.created_at >= start)
        if end: query = query.where(PlatformDonation.created_at < end)
        records.extend(donation_log_json(item, "platform") for item in session.scalars(query).all())
    if donation_type in (None, "campaign"):
        query = select(CrowdfundingDonation)
        if status: query = query.where(CrowdfundingDonation.payment_status == status)
        if start: query = query.where(CrowdfundingDonation.created_at >= start)
        if end: query = query.where(CrowdfundingDonation.created_at < end)
        records.extend(donation_log_json(item, "campaign") for item in session.scalars(query).all())
    return sorted(records, key=lambda item: item["created_at"] or "", reverse=True)


def donation_log_json(item: PlatformDonation | CrowdfundingDonation, donation_type: str) -> dict[str, Any]:
    return donation_json(item) | {
        "type": donation_type,
        "campaign_id": getattr(item, "campaign_id", None),
        "donor_name": "Anonymous" if item.is_anonymous else item.donor_name,
    }


def resolve_message_actor(identifier: str, authorization: str | None, x_ngo_token: str | None, x_admin_token: str | None, session: Session) -> tuple[Case, str, str, int | None]:
    case_id = identifier.upper()
    case = session.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    if x_admin_token and settings.admin_api_token and secrets.compare_digest(token_hash(x_admin_token), token_hash(settings.admin_api_token)):
        return case, "admin", "admin", None
    if x_ngo_token:
        account = session.scalar(select(NGOAccount).where(NGOAccount.api_token_hash == token_hash(x_ngo_token)))
        referral = session.scalar(select(Referral).where(Referral.case_id == case_id, Referral.ngo_id == getattr(account, "ngo_id", None), Referral.status.in_(["forwarded", "acknowledged"]))) if account else None
        if not account or account.billing_status != "active" or not referral:
            raise HTTPException(403, "This case is not assigned to your NGO")
        return case, "ngo", str(account.ngo_id), account.ngo_id
    try:
        token = bearer_token(authorization)
        record = session.get(CaseSession, token)
    except HTTPException:
        record = None
    if not record or not record.is_active or record.expires_at <= now() or record.case_id != case_id:
        raise HTTPException(401, "Authentication required")
    return case, "survivor", case_id, None


def visible_case_messages(case_id: str, sender_type: str, sender_id: str, ngo_id: int | None, session: Session) -> list[CaseMessage]:
    query = select(CaseMessage).where(CaseMessage.case_id == case_id).order_by(CaseMessage.sent_at.asc(), CaseMessage.id.asc())
    if sender_type == "admin":
        return session.scalars(query).all()
    query = query.where(CaseMessage.is_internal_note.is_(False))
    if sender_type == "ngo":
        query = query.where((CaseMessage.sender_type != "ngo") | (CaseMessage.ngo_id == ngo_id))
    return session.scalars(query).all()


def mark_messages_read(messages: list[CaseMessage], case_id: str, sender_type: str, sender_id: str, session: Session) -> None:
    if not messages:
        return
    existing = {(item.message_id, item.participant_type, item.participant_id) for item in session.scalars(select(CaseMessageRead).where(CaseMessageRead.case_id == case_id, CaseMessageRead.participant_type == sender_type, CaseMessageRead.participant_id == sender_id)).all()}
    for item in messages:
        key = (item.id, sender_type, sender_id)
        if key not in existing:
            session.add(CaseMessageRead(message_id=item.id, case_id=case_id, participant_type=sender_type, participant_id=sender_id))


@app.get("/api/cases/{identifier}/messages")
def list_case_messages(identifier: str, authorization: str | None = Header(default=None), x_ngo_token: str | None = Header(default=None), x_admin_token: str | None = Header(default=None), session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    case, sender_type, sender_id, ngo_id = resolve_message_actor(identifier, authorization, x_ngo_token, x_admin_token, session)
    messages = visible_case_messages(case.case_id, sender_type, sender_id, ngo_id, session)
    mark_messages_read(messages, case.case_id, sender_type, sender_id, session)
    session.commit()
    return [message_json(item, sender_type == "admin") for item in messages]


@app.post("/api/cases/{identifier}/messages")
def send_case_message(identifier: str, payload: MessageCreate, authorization: str | None = Header(default=None), x_ngo_token: str | None = Header(default=None), x_admin_token: str | None = Header(default=None), session: Session = Depends(get_db)) -> dict[str, Any]:
    case, sender_type, sender_id, ngo_id = resolve_message_actor(identifier, authorization, x_ngo_token, x_admin_token, session)
    message = payload.message.strip()
    if not message:
        raise HTTPException(422, "Message cannot be empty")
    item = CaseMessage(case_id=case.case_id, ngo_id=ngo_id, sender_type=sender_type, sender_id=sender_id, message=message, is_internal_note=bool(payload.is_internal_note and sender_type == "admin"))
    session.add(item)
    session.commit()
    session.refresh(item)
    return message_json(item, sender_type == "admin")


@app.post("/api/cases/{identifier}/messages/read")
def mark_case_messages_read(identifier: str, authorization: str | None = Header(default=None), x_ngo_token: str | None = Header(default=None), x_admin_token: str | None = Header(default=None), session: Session = Depends(get_db)) -> dict[str, int]:
    case, sender_type, sender_id, ngo_id = resolve_message_actor(identifier, authorization, x_ngo_token, x_admin_token, session)
    messages = visible_case_messages(case.case_id, sender_type, sender_id, ngo_id, session)
    mark_messages_read(messages, case.case_id, sender_type, sender_id, session)
    session.commit()
    return {"marked": len(messages)}


@app.get("/api/ngo/referrals/{referral_id}/messages")
def list_ngo_messages(referral_id: str, account: NGOAccount = Depends(current_ngo), session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    referral = session.scalar(select(Referral).where(Referral.id == referral_id, Referral.ngo_id == account.ngo_id, Referral.status.in_(["forwarded", "acknowledged"])))
    if not referral:
        raise HTTPException(404, "Active referral not found")
    messages = visible_case_messages(referral.case_id, "ngo", str(account.ngo_id), account.ngo_id, session)
    mark_messages_read(messages, referral.case_id, "ngo", str(account.ngo_id), session)
    session.commit()
    return [message_json(item) for item in messages]


@app.post("/api/ngo/referrals/{referral_id}/messages")
def send_ngo_message(referral_id: str, payload: MessageCreate, account: NGOAccount = Depends(current_ngo), session: Session = Depends(get_db)) -> dict[str, Any]:
    referral = session.scalar(select(Referral).where(Referral.id == referral_id, Referral.ngo_id == account.ngo_id, Referral.status.in_(["forwarded", "acknowledged"])))
    if not referral:
        raise HTTPException(404, "Active referral not found")
    item = CaseMessage(case_id=referral.case_id, ngo_id=account.ngo_id, sender_type="ngo", sender_id=str(account.ngo_id), message=payload.message.strip(), is_internal_note=False)
    session.add(item)
    session.commit()
    session.refresh(item)
    return message_json(item)


@app.get("/api/ngo/referrals/{referral_id}/timeline")
def ngo_case_timeline(referral_id: str, account: NGOAccount = Depends(current_ngo), session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    referral = session.scalar(select(Referral).where(Referral.id == referral_id, Referral.ngo_id == account.ngo_id))
    if not referral:
        raise HTTPException(404, "Referral not found")
    return [{"status": item.status, "note": item.note, "actor_id": item.actor_id, "created_at": item.created_at.isoformat() if item.created_at else None} for item in session.scalars(select(CaseStatusLog).where(CaseStatusLog.referral_id == referral_id).order_by(CaseStatusLog.created_at.asc())).all()]


@app.post("/api/ngo/commissions/{commission_id}/confirm")
def confirm_commission(commission_id: str, account: NGOAccount = Depends(current_ngo), session: Session = Depends(get_db)) -> dict[str, Any]:
    commission_feature_enabled()
    record = session.scalar(select(CommissionRecord).where(CommissionRecord.id == commission_id, CommissionRecord.ngo_id == account.ngo_id))
    if not record:
        raise HTTPException(404, "Commission record not found")
    if record.status != "pending":
        raise HTTPException(409, "Only pending commissions can be confirmed")
    previous = record.status
    record.status = "confirmed"
    audit_commission(session, record, f"ngo:{account.ngo_id}", previous, "NGO confirmed outcome")
    session.commit()
    return commission_json(record)


@app.get("/api/admin/commissions", dependencies=[Depends(require_admin)])
def list_commissions(session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    commission_feature_enabled()
    return [commission_json(item) for item in session.scalars(select(CommissionRecord).order_by(CommissionRecord.created_at.desc())).all()]


@app.patch("/api/admin/commissions/{commission_id}", dependencies=[Depends(require_admin)])
def adjust_commission(commission_id: str, payload: CommissionAdjustment, x_admin_token: str = Header(default="admin"), session: Session = Depends(get_db)) -> dict[str, Any]:
    commission_feature_enabled()
    record = session.get(CommissionRecord, commission_id)
    if not record:
        raise HTTPException(404, "Commission record not found")
    previous = record.status
    record.status = payload.status
    if payload.commission_amount is not None:
        record.commission_amount = payload.commission_amount
    audit_commission(session, record, "admin", previous, payload.note)
    session.commit()
    return commission_json(record)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=int(settings.model_dump().get("port", 8000)), reload=False)
