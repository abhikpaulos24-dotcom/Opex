"""Database tables. database/01_schema.sql creates the same tables in Supabase (Postgres);
locally, SQLAlchemy creates them in a SQLite file so the app runs with zero setup."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

Json = JSON().with_variant(JSONB(), "postgresql")


def now_utc() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "app_users"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    preferences: Mapped[dict] = mapped_column(Json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    machine_id: Mapped[str] = mapped_column(String(10), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # failure_risk | breakdown | quality | energy | data_health
    severity: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(15), default="open", index=True)
    plant_time: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    acknowledged_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    machine_id: Mapped[str] = mapped_column(String(10), index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(15), default="open", index=True)  # open | resolved
    severity: Mapped[str] = mapped_column(String(10))
    component: Mapped[str | None] = mapped_column(String(20), nullable=True)
    root_cause: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_plant_time: Mapped[str] = mapped_column(String(20))
    resolved_plant_time: Mapped[str | None] = mapped_column(String(20), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    snapshot: Mapped[dict] = mapped_column(Json, default=dict)  # what the AI saw when it opened
    report: Mapped[str | None] = mapped_column(Text, nullable=True)  # investigation write-up


class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    machine_id: Mapped[str] = mapped_column(String(10), index=True)
    plant_time: Mapped[str] = mapped_column(String(20))
    cause_key: Mapped[str] = mapped_column(String(40))
    cause_name: Mapped[str] = mapped_column(String(120))
    component: Mapped[str | None] = mapped_column(String(20), nullable=True)
    preset: Mapped[str] = mapped_column(String(30), default="balanced")
    weights: Mapped[dict] = mapped_column(Json, default=dict)
    options: Mapped[list] = mapped_column(Json, default=list)
    recommended_action: Mapped[str] = mapped_column(String(40))
    summary: Mapped[dict] = mapped_column(Json, default=dict)
    confidence: Mapped[float] = mapped_column(Float)
    agent_trace: Mapped[list] = mapped_column(Json, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    recommendation_id: Mapped[str | None] = mapped_column(ForeignKey("recommendations.id"), nullable=True)
    machine_id: Mapped[str] = mapped_column(String(10), index=True)
    cause_key: Mapped[str] = mapped_column(String(40), index=True)
    recommended_action: Mapped[str | None] = mapped_column(String(40), nullable=True)
    action_key: Mapped[str] = mapped_column(String(40))
    decision: Mapped[str] = mapped_column(String(15))  # approved | rejected | modified
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    plant_minute: Mapped[int] = mapped_column(Integer, default=0)
    plant_time: Mapped[str] = mapped_column(String(20), default="")
    predicted: Mapped[dict] = mapped_column(Json, default=dict)
    before: Mapped[dict] = mapped_column(Json, default=dict)
    after: Mapped[dict] = mapped_column(Json, default=dict)
    outcome_status: Mapped[str] = mapped_column(String(15), default="pending", index=True)
    outcome: Mapped[dict] = mapped_column(Json, default=dict)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="live")  # live | pilot_history


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(30))  # sop | manual | incident_report | note
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(200), default="uploaded")
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    params: Mapped[dict] = mapped_column(Json, default=dict)
    summary: Mapped[dict] = mapped_column(Json, default=dict)
    player: Mapped[dict] = mapped_column(Json, default=dict)
    events: Mapped[list] = mapped_column(Json, default=list)
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    target: Mapped[str | None] = mapped_column(String(120), nullable=True)
    details: Mapped[dict] = mapped_column(Json, default=dict)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(Json, default=dict)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
