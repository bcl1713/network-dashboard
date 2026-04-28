from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Filter(Base):
    __tablename__ = "filters"
    __table_args__ = (
        CheckConstraint("source_host IS NULL OR source_subnet IS NULL"),
        CheckConstraint("destination IS NULL OR destination_subnet IS NULL"),
        CheckConstraint("action IN ('tag','hide','allow')"),
        CheckConstraint("match_mode IN ('exact','contains','regex')"),
        Index("ix_filters_enabled_retired", "enabled", "retired"),
        Index("ix_filters_sid", "sid"),
        Index("ix_filters_host_sid", "source_host", "sid"),
        Index("ix_filters_subnet_sid", "source_subnet", "sid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    retired: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    action: Mapped[str] = mapped_column(String, nullable=False)

    source_host: Mapped[str | None] = mapped_column(String, nullable=True)
    source_subnet: Mapped[str | None] = mapped_column(String, nullable=True)
    sid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    destination: Mapped[str | None] = mapped_column(String, nullable=True)
    destination_subnet: Mapped[str | None] = mapped_column(String, nullable=True)
    destination_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    protocol: Mapped[str | None] = mapped_column(String, nullable=True)
    message_match: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_mode: Mapped[str] = mapped_column(String, nullable=False, default="exact")

    tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.datetime("now")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.datetime("now")
    )
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_matched_event_id: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    audit_rows: Mapped[list["FilterAudit"]] = relationship(
        "FilterAudit", back_populates="filter", cascade="all, delete-orphan", lazy="noload"
    )


class FilterAudit(Base):
    __tablename__ = "filter_audit"
    __table_args__ = (
        CheckConstraint("decision IN ('tag','hide','allow')"),
        Index("ix_filter_audit_filter_id", "filter_id"),
        Index("ix_filter_audit_matched_at", "matched_at"),
        Index("ix_filter_audit_event_id", "event_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filter_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("filters.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[str] = mapped_column(String, nullable=False)
    matched_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.datetime("now")
    )
    decision: Mapped[str] = mapped_column(String, nullable=False)
    matched_fields: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    filter: Mapped[Filter] = relationship("Filter", back_populates="audit_rows")
