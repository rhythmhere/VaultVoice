from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, create_engine, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


class Case(Base):
    __tablename__ = "cases"
    case_id: Mapped[str] = mapped_column(String(12), primary_key=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    district: Mapped[str] = mapped_column(String(100), index=True)
    initial_report: Mapped[str] = mapped_column(Text)
    clarifying_qa: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    ai_legal_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    emergency_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    analysis_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    timeline: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    matches: Mapped[list["CaseMatch"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    referrals: Mapped[list["Referral"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    sos_alerts: Mapped[list["SOSAlert"]] = relationship(back_populates="case")


class SOSAlert(Base):
    __tablename__ = "sos_alerts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.case_id", ondelete="SET NULL"), nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location_status: Mapped[str] = mapped_column(String(40), default="not_requested", nullable=False, index=True)
    location_source: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    location_sharing_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    access_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="triggered", nullable=False, index=True)
    assigned_ngo_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    police_escalation_status: Mapped[str] = mapped_column(String(30), default="not_requested", nullable=False, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    case: Mapped[Case | None] = relationship(back_populates="sos_alerts")
    assigned_ngo: Mapped["Organization | None"] = relationship()
    audit_log: Mapped[list["SOSAuditLog"]] = relationship(back_populates="alert", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("status IN ('triggered', 'acknowledged', 'assigned', 'responder_en_route', 'survivor_contacted', 'resolved', 'cancelled')", name="ck_sos_alerts_status"),
        CheckConstraint("police_escalation_status IN ('not_requested', 'review_requested', 'contacted', 'not_needed')", name="ck_sos_alerts_police_escalation_status"),
    )


class SOSAuditLog(Base):
    __tablename__ = "sos_audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sos_id: Mapped[str] = mapped_column(ForeignKey("sos_alerts.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    alert: Mapped[SOSAlert] = relationship(back_populates="audit_log")


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), index=True)
    object_key: Mapped[str] = mapped_column(String(255), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(Integer)
    integrity_hash: Mapped[str] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    incident_date: Mapped[Any | None] = mapped_column(Date, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    case: Mapped[Case] = relationship(back_populates="evidence")


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    categories: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    districts: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    contact_phone: Mapped[str] = mapped_column(String(40))
    contact_email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    verification_status: Mapped[str] = mapped_column(String(20), default="approved", nullable=False, index=True)
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    matches: Mapped[list["CaseMatch"]] = relationship(back_populates="organization")
    account: Mapped["NGOAccount | None"] = relationship(back_populates="organization", uselist=False, cascade="all, delete-orphan")
    commissions: Mapped[list["CommissionRecord"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    referrals: Mapped[list["Referral"]] = relationship(back_populates="organization")


class CaseMatch(Base):
    __tablename__ = "case_matches"
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    match_reason: Mapped[str] = mapped_column(Text)
    case: Mapped[Case] = relationship(back_populates="matches")
    organization: Mapped[Organization] = relationship(back_populates="matches")


class NGOAccount(Base):
    __tablename__ = "ngo_accounts"
    ngo_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    subscription_tier: Mapped[str] = mapped_column(String(10), default="free", nullable=False)
    billing_status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    commission_agreement: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    api_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    organization: Mapped[Organization] = relationship(back_populates="account")

    __table_args__ = (
        CheckConstraint("subscription_tier IN ('free', 'paid')", name="ck_ngo_accounts_subscription_tier"),
    )


class CommissionRecord(Base):
    __tablename__ = "commission_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), index=True)
    ngo_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    self_reported_outcome: Mapped[str] = mapped_column(Text)
    commission_amount: Mapped[Any] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="NPR", nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    organization: Mapped[Organization] = relationship(back_populates="commissions")
    audit_log: Mapped[list["CommissionAuditLog"]] = relationship(back_populates="commission", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("currency = 'NPR'", name="ck_commission_records_currency"),
        CheckConstraint("status IN ('pending', 'confirmed', 'invoiced', 'paid')", name="ck_commission_records_status"),
    )


class CommissionAuditLog(Base):
    __tablename__ = "commission_audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    commission_id: Mapped[str] = mapped_column(ForeignKey("commission_records.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[str] = mapped_column(String(100))
    from_status: Mapped[str | None] = mapped_column(String(12), nullable=True)
    to_status: Mapped[str] = mapped_column(String(12))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    commission: Mapped[CommissionRecord] = relationship(back_populates="audit_log")


class Referral(Base):
    __tablename__ = "referrals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), index=True)
    ngo_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"), index=True)
    consent_scope: Mapped[str] = mapped_column(String(40), nullable=False)
    submitted_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    consent_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    includes_evidence: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evidence_refs: Mapped[list[int]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    support_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    case_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    case: Mapped[Case] = relationship(back_populates="referrals")
    organization: Mapped[Organization] = relationship(back_populates="referrals")
    audit_log: Mapped[list["ReferralAuditLog"]] = relationship(back_populates="referral", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("consent_scope IN ('full_case', 'contact_details_evidence_summary')", name="ck_referrals_consent_scope"),
        CheckConstraint("status IN ('draft', 'requested', 'admin_review', 'forwarded', 'acknowledged', 'closed')", name="ck_referrals_status"),
        CheckConstraint("case_status IN ('pending', 'in_progress', 'resolved', 'on_hold')", name="ck_referrals_case_status"),
    )


class ReferralAuditLog(Base):
    __tablename__ = "referral_audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referral_id: Mapped[str] = mapped_column(ForeignKey("referrals.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    referral: Mapped[Referral] = relationship(back_populates="audit_log")


class CaseNote(Base):
    __tablename__ = "case_notes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referral_id: Mapped[str] = mapped_column(ForeignKey("referrals.id", ondelete="CASCADE"), index=True)
    ngo_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    referral: Mapped[Referral] = relationship()
    organization: Mapped[Organization] = relationship()


class NGOVerificationLog(Base):
    __tablename__ = "ngo_verification_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ngo_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class NGODocument(Base):
    __tablename__ = "ngo_documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ngo_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    object_key: Mapped[str] = mapped_column(String(255), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    doc_type: Mapped[str] = mapped_column(String(80), default="registration")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PlatformDonation(Base):
    __tablename__ = "platform_donations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    donor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    donor_email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    amount: Mapped[Any] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="NPR", nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    payment_reference: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CrowdfundingRequest(Base):
    __tablename__ = "crowdfunding_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    requested_amount: Mapped[Any] = mapped_column(Numeric(12, 2), nullable=False)
    target_date: Mapped[Any | None] = mapped_column(Date, nullable=True)
    consent_public_display: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(25), default="pending_review", index=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    case: Mapped[Case] = relationship()


class CrowdfundingCampaign(Base):
    __tablename__ = "crowdfunding_campaigns"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), index=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requested_amount: Mapped[Any] = mapped_column(Numeric(12, 2), nullable=False)
    amount_raised: Mapped[Any] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CrowdfundingDonation(Base):
    __tablename__ = "crowdfunding_donations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("crowdfunding_campaigns.id", ondelete="CASCADE"), index=True)
    donor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    amount: Mapped[Any] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="NPR", nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    payment_reference: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CaseMessage(Base):
    __tablename__ = "case_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), index=True)
    ngo_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=True)
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sender_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal_note: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CaseMessageRead(Base):
    __tablename__ = "case_message_reads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("case_messages.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), index=True)
    participant_type: Mapped[str] = mapped_column(String(20), nullable=False)
    participant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (UniqueConstraint("message_id", "participant_type", "participant_id", name="uq_case_message_read_participant"),)


class CaseStatusLog(Base):
    __tablename__ = "case_status_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referral_id: Mapped[str] = mapped_column(ForeignKey("referrals.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


Index("ix_evidence_case_incident_date", Evidence.case_id, Evidence.incident_date)
UniqueConstraint(CaseMatch.case_id, CaseMatch.organization_id)
Index("ix_commission_records_ngo_status", CommissionRecord.ngo_id, CommissionRecord.status)
Index("ix_referrals_ngo_status", Referral.ngo_id, Referral.status)
class Session(Base):
    __tablename__ = "sessions"
    session_token: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_accessed: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    case: Mapped[Case] = relationship()

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
