from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import date, datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .ai_service import AIServiceError, OpenRouterAIService
from .config import get_settings
from .db import Base, Case, CaseMatch, Evidence, Organization, SessionLocal, engine
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
    message: str = Field(min_length=1, max_length=10000)


class StatusUpdate(BaseModel):
    status: str = Field(pattern="^(open|ngo_contacted|resolved)$")


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
    existing = {item.organization_id: item for item in case.matches}
    for score, organization in selected:
        if organization.id not in existing:
            session.add(CaseMatch(case_id=case.case_id, organization_id=organization.id, match_reason=f"Matches {case.category.replace('_', ' ')} support and {case.district} coverage."))
    session.commit()
    return [organization_json(organization, f"Matches {case.category.replace('_', ' ')} support and {case.district} coverage.") for _, organization in selected]


def organization_json(organization: Organization, reason: str) -> dict[str, Any]:
    return {"id": organization.id, "name": organization.name, "contact_phone": organization.contact_phone, "contact_email": organization.contact_email, "website": organization.website, "description": organization.description, "districts": organization.districts, "match_reason": reason}


def evidence_json(item: Evidence) -> dict[str, Any]:
    return {"id": item.id, "name": item.original_name, "type": item.file_type, "size": item.size, "description": item.description, "incident_date": item.incident_date.isoformat() if item.incident_date else None, "uploaded_at": item.uploaded_at.isoformat() if item.uploaded_at else None, "integrity_hash": item.integrity_hash}


def serialize_case(session: Session, case: Case) -> dict[str, Any]:
    return {"case_id": case.case_id, "category": case.category, "district": case.district, "initial_report": case.initial_report, "clarifying_qa": case.clarifying_qa or [], "ai_legal_summary": case.ai_legal_summary, "severity": case.severity, "status": case.status, "created_at": case.created_at.isoformat() if case.created_at else None, "updated_at": case.updated_at.isoformat() if case.updated_at else None, "timeline": case.timeline or [], "evidence": [evidence_json(item) for item in case.evidence], "matches": match_case(session, case)}


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
    try:
        return await service.analyze_report(payload.category, payload.initial_report, payload.clarifying_qa)
    except AIServiceError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/api/cases")
@limiter.limit("10/hour")
async def create_case(request: Request, payload: CaseCreate, session: Session = Depends(get_db), service: OpenRouterAIService = Depends(ai_service)) -> dict[str, Any]:
    try:
        analysis = await service.analyze_report(payload.category, payload.initial_report, payload.clarifying_qa)
    except AIServiceError as exc:
        raise HTTPException(503, str(exc)) from exc
    case = Case(case_id=make_case_id(session), category=payload.category, district=payload.district, initial_report=payload.initial_report, clarifying_qa=payload.clarifying_qa, ai_legal_summary=analysis["legal_summary"], severity=analysis["severity"], status="open", timeline=[])
    session.add(case)
    session.commit()
    session.refresh(case)
    return serialize_case(session, case)


@app.get("/api/cases/{identifier}")
def get_case(identifier: str, session: Session = Depends(get_db)) -> dict[str, Any]:
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
    qa.append({"answer": payload.message})
    try:
        analysis = await service.analyze_report(case.category, case.initial_report, qa)
    except AIServiceError as exc:
        raise HTTPException(503, str(exc)) from exc
    case.clarifying_qa = qa
    case.ai_legal_summary = analysis["legal_summary"]
    case.severity = analysis["severity"]
    case.updated_at = now()
    session.commit()
    return {"message": "Thank you for sharing that. You can take this one step at a time.", "next_questions": analysis.get("clarifying_questions", []), "clarifying_qa": qa, "ai_legal_summary": case.ai_legal_summary, "severity": case.severity}


@app.post("/api/cases/{identifier}/evidence")
@limiter.limit("30/hour")
async def upload_evidence(request: Request, identifier: str, file: UploadFile = File(...), description: str = Form(default=""), incident_date: date | None = Form(default=None), session: Session = Depends(get_db), service: OpenRouterAIService = Depends(ai_service), storage: ObjectStorage = Depends(storage_service)) -> dict[str, Any]:
    case = session.get(Case, identifier.upper())
    if not case:
        raise HTTPException(404, "Case not found")
    if not file.content_type or file.content_type not in {"image/jpeg", "image/png", "image/webp", "application/pdf", "audio/mpeg", "audio/wav", "audio/ogg", "text/plain"}:
        raise HTTPException(415, "Unsupported evidence type")
    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(413, f"Maximum file size is {settings.max_upload_bytes // (1024 * 1024)}MB")
    object_key = f"{case.case_id}/{uuid.uuid4().hex}"
    try:
        storage.put_encrypted(object_key, content, file.content_type)
    except Exception as exc:
        raise HTTPException(503, "Evidence storage is unavailable") from exc
    item = Evidence(case_id=case.case_id, object_key=object_key, original_name=file.filename or "evidence", file_type=file.content_type, size=len(content), integrity_hash=hashlib.sha256(content).hexdigest(), description=description.strip() or None, incident_date=incident_date)
    session.add(item)
    session.flush()
    metadata = [evidence_json(existing) for existing in [*case.evidence, item]]
    try:
        generated = await service.build_timeline(metadata)
    except AIServiceError as exc:
        raise HTTPException(503, str(exc)) from exc
    case.timeline = generated["timeline"]
    case.updated_at = now()
    session.commit()
    return {"evidence": evidence_json(item), "timeline": case.timeline, "timeline_summary": generated["summary"]}


@app.get("/api/cases/{identifier}/evidence/{evidence_id}")
def download_evidence(identifier: str, evidence_id: int, session: Session = Depends(get_db), storage: ObjectStorage = Depends(storage_service)) -> StreamingResponse:
    item = session.scalar(select(Evidence).where(Evidence.case_id == identifier.upper(), Evidence.id == evidence_id))
    if not item:
        raise HTTPException(404, "Evidence not found")
    try:
        content = storage.get_decrypted(item.object_key)
    except Exception as exc:
        raise HTTPException(404, "Evidence file is unavailable") from exc
    return StreamingResponse(iter([content]), media_type=item.file_type, headers={"Content-Disposition": f'attachment; filename="{item.original_name}"', "X-Content-SHA256": item.integrity_hash})


@app.get("/api/cases/{identifier}/evidence/{evidence_id}/url")
def evidence_url(identifier: str, evidence_id: int, session: Session = Depends(get_db), storage: ObjectStorage = Depends(storage_service)) -> dict[str, Any]:
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
def get_matches(identifier: str, session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    case = session.get(Case, identifier.upper())
    if not case:
        raise HTTPException(404, "Case not found")
    return match_case(session, case)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=int(settings.model_dump().get("port", 8000)), reload=False)
