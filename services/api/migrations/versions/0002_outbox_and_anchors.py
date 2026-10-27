"""Notification outbox and signed audit anchors.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-26

The outbox is written in the same transaction as the event it reports, so a
notification is never lost and never sent for a change that rolled back.

An anchor is a signed statement "on node N, the audit chain had entry_hash H at
sequence S". The chain alone cannot catch an insider who rewrites every entry
and recomputes every hash; a signed anchor (with copies held outside this
database) can, because the rewritten chain no longer reaches H at S.
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE notification_outbox (
    id              bigserial   PRIMARY KEY,
    event           text        NOT NULL,
    ref             text        NOT NULL,
    payload         jsonb       NOT NULL,
    status          text        NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'delivered', 'failed')),
    attempts        integer     NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    last_error      text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    delivered_at    timestamptz
);
CREATE INDEX notification_outbox_due ON notification_outbox (status, next_attempt_at);

CREATE TABLE audit_anchors (
    anchor_id   varchar(32) PRIMARY KEY,
    node_id     text        NOT NULL,
    up_to_seq   bigint      NOT NULL UNIQUE,
    head_hash   varchar(64) NOT NULL,
    entries     bigint      NOT NULL,
    anchored_at timestamptz NOT NULL,
    key_id      varchar(32) NOT NULL,
    statement   text        NOT NULL,
    signature   text        NOT NULL
);

CREATE TRIGGER audit_anchors_append_only BEFORE UPDATE OR DELETE ON audit_anchors
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE TRIGGER audit_anchors_no_truncate BEFORE TRUNCATE ON audit_anchors
    FOR EACH STATEMENT EXECUTE FUNCTION reject_mutation();
"""

DOWNGRADE = """
DROP TABLE IF EXISTS audit_anchors, notification_outbox;
"""


def _statements(script: str) -> list[str]:
    # No function bodies in this migration, so a plain split is safe.
    return [s.strip() for s in script.split(";") if s.strip()]


def upgrade() -> None:
    for stmt in _statements(UPGRADE):
        op.execute(stmt)


def downgrade() -> None:
    for stmt in _statements(DOWNGRADE):
        op.execute(stmt)
