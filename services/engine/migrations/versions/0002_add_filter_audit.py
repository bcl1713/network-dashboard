"""add filter_audit

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-27
"""
from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE filter_audit (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            filter_id       INTEGER NOT NULL REFERENCES filters(id) ON DELETE CASCADE,
            event_id        TEXT    NOT NULL,
            matched_at      TEXT    NOT NULL DEFAULT (datetime('now')),
            decision        TEXT    NOT NULL CHECK (decision IN ('tag','hide','allow')),
            matched_fields  TEXT    NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute("CREATE INDEX ix_filter_audit_filter_id  ON filter_audit(filter_id)")
    op.execute("CREATE INDEX ix_filter_audit_matched_at ON filter_audit(matched_at)")
    op.execute("CREATE INDEX ix_filter_audit_event_id   ON filter_audit(event_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_filter_audit_event_id")
    op.execute("DROP INDEX IF EXISTS ix_filter_audit_matched_at")
    op.execute("DROP INDEX IF EXISTS ix_filter_audit_filter_id")
    op.execute("DROP TABLE IF EXISTS filter_audit")
