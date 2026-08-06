from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
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
from .db import Case, CaseMatch, CommissionAuditLog, CommissionRecord, Evidence, NGOAccount, Organization, SessionLocal
from .matching import match_case
from .seed import seed_organizations
from .storage import ObjectStorage

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s vaultvoice %(message)s")
logger = logging.getLogger("vaultvoice")
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


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if not settings.admin_api_token or not x_admin_token or not secrets.compare_digest(token_hash(x_admin_token), token_hash(settings.admin_api_token)):
        raise HTTPException(401, "Admin authentication required")


def current_ngo(x_ngo_token: str | None = Header(default=None), session: Session = Depends(get_db)) -> NGOAccount:
    if not x_ngo_token:
        raise HTTPException(401, "NGO authentication required")
    account = session.scalar(select(NGOAccount).where(NGOAccount.api_token_hash == token_hash(x_ngo_token)))
    if not account or account.billing_status != "active":
        raise HTTPException(401, "NGO authentication required")
    return account


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
    return {"case_id": case.case_id, "category": case.category, "district": case.district, "initial_report": case.initial_report, "clarifying_qa": case.clarifying_qa or [], "ai_legal_summary": case.ai_legal_summary, "severity": case.severity, "analysis_status": case.analysis_status, "status": case.status, "created_at": case.created_at.isoformat() if case.created_at else None, "updated_at": case.updated_at.isoformat() if case.updated_at else None, "timeline": case.timeline or [], "evidence": [evidence_json(item) for item in case.evidence], "matches": match_case(session, case)}


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
    case = Case(case_id=make_case_id(session), category=payload.category, district=payload.district, initial_report=payload.initial_report, clarifying_qa=payload.clarifying_qa, ai_legal_summary=None, severity=None, analysis_status="pending", status="open", timeline=[])
    session.add(case)
    session.commit()
    session.refresh(case)
    logger.info("OpenRouter call path=create_case case_id=%s qa_count=%d", case.case_id, len(payload.clarifying_qa))
    try:
        analysis = await service.analyze_report(payload.category, payload.initial_report, payload.clarifying_qa)
    except AIServiceError as exc:
        logger.warning("Case analysis failed case_id=%s error=%r", case.case_id, exc)
        case.analysis_status = "failed"
        session.commit()
        return serialize_case(session, case) | {"clarifying_questions": []}
    case.ai_legal_summary = analysis["legal_summary"]
    case.severity = analysis["severity"]
    case.analysis_status = "complete"
    session.commit()
    session.refresh(case)
    result = serialize_case(session, case)
    result["clarifying_questions"] = analysis.get("clarifying_questions", [])
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
        return serialize_case(session, case) | {"clarifying_questions": []}
    case.ai_legal_summary = analysis["legal_summary"]
    case.severity = analysis["severity"]
    case.analysis_status = "complete"
    case.updated_at = now()
    session.commit()
    session.refresh(case)
    return serialize_case(session, case) | {"clarifying_questions": analysis.get("clarifying_questions", [])}


@app.get("/api/cases/{identifier}")
@limiter.limit("30/hour")
def get_case(request: Request, identifier: str, session: Session = Depends(get_db)) -> dict[str, Any]:
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
    qa.append({"question": payload.question.strip(), "answer": payload.answer.strip(), "answered_at": now().isoformat()})
    try:
        analysis = await service.analyze_report(case.category, case.initial_report, qa)
    except AIServiceError as exc:
        logger.warning("Clarification analysis failed case_id=%s error=%r", case.case_id, exc)
        case.clarifying_qa = qa
        case.analysis_status = "failed"
        session.commit()
        return {"message": "Your answer was saved. Legal analysis is temporarily unavailable.", "next_questions": [], "clarifying_qa": qa, "ai_legal_summary": case.ai_legal_summary, "severity": case.severity, "analysis_status": case.analysis_status}
    case.clarifying_qa = qa
    case.ai_legal_summary = analysis["legal_summary"]
    case.severity = analysis["severity"]
    case.analysis_status = "complete"
    case.updated_at = now()
    session.commit()
    return {"message": "Thank you for sharing that. You can take this one step at a time.", "next_questions": analysis.get("clarifying_questions", []), "clarifying_qa": qa, "ai_legal_summary": case.ai_legal_summary, "severity": case.severity}


@app.post("/api/cases/{identifier}/evidence")
@limiter.limit("30/hour")
async def upload_evidence(request: Request, identifier: str, file: UploadFile = File(...), description: str = Form(default=""), incident_date: date | None = Form(default=None), session: Session = Depends(get_db), service: OpenRouterAIService = Depends(ai_service), storage: ObjectStorage = Depends(storage_service)) -> dict[str, Any]:
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
    metadata = [evidence_json(existing) for existing in [*case.evidence, item]]
    try:
        generated = await service.build_timeline(metadata)
    except AIServiceError as exc:
        logger.warning("Evidence timeline generation failed case_id=%s error=%r", case.case_id, exc)
        case.updated_at = now()
        session.commit()
        return {"evidence": evidence_json(item), "timeline": case.timeline or [], "timeline_summary": "", "analysis_status": "unavailable"}
    case.timeline = generated["timeline"]
    case.updated_at = now()
    session.commit()
    return {"evidence": evidence_json(item), "timeline": case.timeline, "timeline_summary": generated["summary"]}


@app.get("/api/cases/{identifier}/evidence/{evidence_id}")
@limiter.limit("30/hour")
def download_evidence(request: Request, identifier: str, evidence_id: int, session: Session = Depends(get_db), storage: ObjectStorage = Depends(storage_service)) -> StreamingResponse:
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
def get_matches(request: Request, identifier: str, session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    case = session.get(Case, identifier.upper())
    if not case:
        raise HTTPException(404, "Case not found")
    return match_case(session, case)


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


@app.get("/api/ngo/dashboard")
def ngo_dashboard(account: NGOAccount = Depends(current_ngo), session: Session = Depends(get_db)) -> dict[str, Any]:
    if account.subscription_tier != "paid":
        raise HTTPException(403, "A paid subscription is required for the NGO dashboard")
    total = session.scalar(select(func.count(CaseMatch.case_id)).where(CaseMatch.organization_id == account.ngo_id)) or 0
    categories = session.execute(select(Case.category, func.count(Case.case_id)).join(CaseMatch, Case.case_id == CaseMatch.case_id).where(CaseMatch.organization_id == account.ngo_id).group_by(Case.category)).all()
    districts = session.execute(select(Case.district, func.count(Case.case_id)).join(CaseMatch, Case.case_id == CaseMatch.case_id).where(CaseMatch.organization_id == account.ngo_id).group_by(Case.district)).all()
    matched_cases = session.scalars(select(Case).join(CaseMatch, Case.case_id == CaseMatch.case_id).where(CaseMatch.organization_id == account.ngo_id)).all()
    response_hours = [max(0.0, (item.updated_at - item.created_at).total_seconds() / 3600) for item in matched_cases if item.created_at and item.updated_at]
    commissions = session.scalars(select(CommissionRecord).where(CommissionRecord.ngo_id == account.ngo_id).order_by(CommissionRecord.created_at.desc())).all()
    return {"ngo_id": account.ngo_id, "subscription_tier": account.subscription_tier, "metrics": {"matched_cases": total, "category_breakdown": {key: count for key, count in categories}, "district_breakdown": {key: count for key, count in districts}, "average_response_time_hours": round(sum(response_hours) / len(response_hours), 2) if response_hours else None}, "commissions": [commission_json(item) for item in commissions]}


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
