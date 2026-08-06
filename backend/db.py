from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, create_engine, func
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
    analysis_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    timeline: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    matches: Mapped[list["CaseMatch"]] = relationship(back_populates="case", cascade="all, delete-orphan")


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
    matches: Mapped[list["CaseMatch"]] = relationship(back_populates="organization")
    account: Mapped["NGOAccount | None"] = relationship(back_populates="organization", uselist=False, cascade="all, delete-orphan")
    commissions: Mapped[list["CommissionRecord"]] = relationship(back_populates="organization", cascade="all, delete-orphan")


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


Index("ix_evidence_case_incident_date", Evidence.case_id, Evidence.incident_date)
UniqueConstraint(CaseMatch.case_id, CaseMatch.organization_id)
Index("ix_commission_records_ngo_status", CommissionRecord.ngo_id, CommissionRecord.status)

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
