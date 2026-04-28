"""init filters

Revision ID: 0001
Revises:
Create Date: 2026-04-27
"""
from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE filters (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            name                  TEXT    NOT NULL,
            description           TEXT,
            enabled               INTEGER NOT NULL DEFAULT 1,
            retired               INTEGER NOT NULL DEFAULT 0,
            action                TEXT    NOT NULL CHECK (action IN ('tag','hide','allow')),
            source_host           TEXT,
            source_subnet         TEXT,
            sid                   INTEGER,
            generator_id          INTEGER,
            destination           TEXT,
            destination_subnet    TEXT,
            destination_port      INTEGER,
            protocol              TEXT,
            message_match         TEXT,
            match_mode            TEXT    NOT NULL DEFAULT 'exact'
                                  CHECK (match_mode IN ('exact','contains','regex')),
            tags                  TEXT,
            created_at            TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at            TEXT    NOT NULL DEFAULT (datetime('now')),
            created_by            TEXT,
            expires_at            TEXT,
            hit_count             INTEGER NOT NULL DEFAULT 0,
            last_seen_at          TEXT,
            last_matched_event_id TEXT,
            notes                 TEXT,
            CHECK (source_host IS NULL OR source_subnet IS NULL),
            CHECK (destination IS NULL OR destination_subnet IS NULL)
        )
        """
    )
    op.execute("CREATE INDEX ix_filters_enabled_retired ON filters(enabled, retired)")
    op.execute("CREATE INDEX ix_filters_sid              ON filters(sid)")
    op.execute("CREATE INDEX ix_filters_host_sid         ON filters(source_host, sid)")
    op.execute("CREATE INDEX ix_filters_subnet_sid       ON filters(source_subnet, sid)")

    op.execute(
        """
        CREATE TRIGGER trg_filters_updated_at
        AFTER UPDATE ON filters FOR EACH ROW
        BEGIN
            UPDATE filters SET updated_at = datetime('now') WHERE id = OLD.id;
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_filters_updated_at")
    op.execute("DROP INDEX IF EXISTS ix_filters_subnet_sid")
    op.execute("DROP INDEX IF EXISTS ix_filters_host_sid")
    op.execute("DROP INDEX IF EXISTS ix_filters_sid")
    op.execute("DROP INDEX IF EXISTS ix_filters_enabled_retired")
    op.execute("DROP TABLE IF EXISTS filters")
