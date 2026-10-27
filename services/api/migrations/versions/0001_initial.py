"""Initial schema: config versions, signals, decisions, escalations, API keys,
and the append-only, hash-chained audit log.

Revision ID: 0001
Revises:
Create Date: 2026-10-25

Audit chain (computed by the database, not the application):

    payload_hash = sha256(payload)                      -- canonical JSON text
    entry_hash   = sha256(prev_hash | seq | created_at_us | event_type | ref
                          | actor | payload_hash)

An advisory lock taken inside the trigger serialises writers until commit,
so sequence order equals chain order. UPDATE, DELETE and TRUNCATE are rejected
by trigger. Deployments should also REVOKE those privileges from the
application role; a superuser can still disable triggers, which is what
``antos_api.audit.verify_chain`` and the planned signed daily anchor detect.
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

AUDIT_LOCK_KEY = 726287650001  # pg_advisory_xact_lock key for audit writers

UPGRADE = f"""
CREATE TABLE config_versions (
    config_hash       varchar(64) PRIMARY KEY,
    profile           jsonb       NOT NULL,
    profile_canonical text        NOT NULL,
    source_docs       jsonb       NOT NULL,
    rationale         text        NOT NULL CHECK (length(trim(rationale)) > 0),
    created_by        text        NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now(),
    active            boolean     NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX one_active_config ON config_versions (active) WHERE active;

CREATE TABLE signals (
    signal_id   varchar(32) PRIMARY KEY,
    nation_id   varchar(8)  NOT NULL,
    sector      text        NOT NULL,
    signal_type text        NOT NULL,
    source_id   text        NOT NULL,
    source_type text        NOT NULL,
    payload     jsonb       NOT NULL,
    observed_at timestamptz,
    received_at timestamptz NOT NULL,
    raw_hash    text,
    ingested_by text        NOT NULL
);
CREATE INDEX signals_lookup ON signals (nation_id, sector, signal_type, observed_at);

CREATE SEQUENCE audit_log_seq;
CREATE TABLE audit_log (
    seq          bigint      PRIMARY KEY,
    event_type   text        NOT NULL,
    ref          text        NOT NULL,
    actor        text        NOT NULL,
    payload      text        NOT NULL,
    payload_hash varchar(64) NOT NULL,
    prev_hash    varchar(64) NOT NULL,
    entry_hash   varchar(64) NOT NULL UNIQUE,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_log_ref ON audit_log (ref);

CREATE TABLE decisions (
    audit_ref                 varchar(32) PRIMARY KEY,
    decision_id               varchar(32) NOT NULL,
    audit_seq                 bigint      NOT NULL REFERENCES audit_log (seq),
    nation_id                 varchar(8)  NOT NULL,
    sector                    text        NOT NULL,
    validation_state          text        NOT NULL,
    action                    text        NOT NULL,
    allowed_for_action        boolean     NOT NULL,
    human_escalation_required boolean     NOT NULL,
    config_hash               varchar(64) NOT NULL REFERENCES config_versions (config_hash),
    decision                  jsonb       NOT NULL,
    created_by                text        NOT NULL,
    created_at                timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX decisions_decision_id ON decisions (decision_id);

CREATE TABLE escalations (
    escalation_id   varchar(32) PRIMARY KEY,
    decision_id     varchar(32),
    audit_ref       varchar(32),
    nation_id       varchar(8)  NOT NULL,
    sector          text        NOT NULL,
    objective       text        NOT NULL,
    priority        text        NOT NULL CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    assigned_role   text        NOT NULL,
    sla_minutes     integer     NOT NULL CHECK (sla_minutes > 0),
    due_at          timestamptz NOT NULL,
    reasons         jsonb       NOT NULL,
    status          text        NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'acknowledged', 'resolved')),
    breached_at     timestamptz,
    acknowledged_by text,
    acknowledged_at timestamptz,
    resolved_by     text,
    resolved_at     timestamptz,
    resolution      text,
    created_by      text        NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX escalations_queue ON escalations (status, assigned_role, due_at);

CREATE TABLE api_keys (
    key_id      varchar(32) PRIMARY KEY,
    secret_hash varchar(64) NOT NULL,
    name        text        NOT NULL,
    roles       text[]      NOT NULL,
    nation_id   varchar(8),
    created_by  text        NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    revoked_at  timestamptz
);

-- ── Audit hash chain ────────────────────────────────────────

CREATE FUNCTION audit_log_chain() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    last_hash text;
BEGIN
    PERFORM pg_advisory_xact_lock({AUDIT_LOCK_KEY});
    SELECT entry_hash INTO last_hash FROM audit_log ORDER BY seq DESC LIMIT 1;
    NEW.seq          := nextval('audit_log_seq');
    NEW.created_at   := now();
    NEW.prev_hash    := coalesce(last_hash, repeat('0', 64));
    NEW.payload_hash := encode(sha256(convert_to(NEW.payload, 'UTF8')), 'hex');
    NEW.entry_hash   := encode(sha256(convert_to(concat_ws('|',
        NEW.prev_hash,
        NEW.seq::text,
        ((extract(epoch FROM NEW.created_at) * 1000000)::bigint)::text,
        NEW.event_type,
        NEW.ref,
        NEW.actor,
        NEW.payload_hash), 'UTF8')), 'hex');
    RETURN NEW;
END $$;

CREATE TRIGGER audit_log_chain BEFORE INSERT ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_chain();

-- ── Append-only enforcement ─────────────────────────────────

CREATE FUNCTION reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: % rejected', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END $$;

CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION reject_mutation();
CREATE TRIGGER decisions_append_only BEFORE UPDATE OR DELETE ON decisions
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE TRIGGER decisions_no_truncate BEFORE TRUNCATE ON decisions
    FOR EACH STATEMENT EXECUTE FUNCTION reject_mutation();
CREATE TRIGGER signals_append_only BEFORE UPDATE OR DELETE ON signals
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();

-- A config version is immutable except for which one is active.
CREATE FUNCTION config_versions_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' OR (NEW.config_hash, NEW.profile_canonical, NEW.rationale,
                            NEW.created_by, NEW.created_at)
        IS DISTINCT FROM (OLD.config_hash, OLD.profile_canonical, OLD.rationale,
                          OLD.created_by, OLD.created_at) THEN
        RAISE EXCEPTION 'config_versions are immutable: % rejected', TG_OP
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER config_versions_guard BEFORE UPDATE OR DELETE ON config_versions
    FOR EACH ROW EXECUTE FUNCTION config_versions_guard();
"""

DOWNGRADE = """
DROP TABLE IF EXISTS api_keys, escalations, decisions, audit_log, signals, config_versions;
DROP SEQUENCE IF EXISTS audit_log_seq;
DROP FUNCTION IF EXISTS audit_log_chain, reject_mutation, config_versions_guard;
"""


def statements(script: str) -> list[str]:
    """Split on ';' at line ends, outside $$-quoted function bodies. asyncpg
    prepares each statement, so a script cannot be sent in one call."""
    out, current, in_body = [], [], False
    for line in script.splitlines():
        current.append(line)
        in_body ^= line.count("$$") % 2 == 1
        if not in_body and line.rstrip().endswith(";"):
            stmt = "\n".join(current).strip()
            if stmt and not all(ln.strip().startswith("--") for ln in stmt.splitlines()):
                out.append(stmt)
            current = []
    return out


def upgrade() -> None:
    for stmt in statements(UPGRADE):
        op.execute(stmt)


def downgrade() -> None:
    for stmt in statements(DOWNGRADE):
        op.execute(stmt)
