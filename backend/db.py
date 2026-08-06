from datetime import datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, create_engine, func
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
    clarifying_qa: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list)
    ai_legal_summary: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), index=True)
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


class CaseMatch(Base):
    __tablename__ = "case_matches"
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    match_reason: Mapped[str] = mapped_column(Text)
    case: Mapped[Case] = relationship(back_populates="matches")
    organization: Mapped[Organization] = relationship(back_populates="matches")


Index("ix_evidence_case_incident_date", Evidence.case_id, Evidence.incident_date)
UniqueConstraint(CaseMatch.case_id, CaseMatch.organization_id)

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
