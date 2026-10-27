"""Integration tests against a real PostgreSQL database.

Set ANTOS_TEST_DATABASE_URL to a *disposable* database, e.g.
postgresql+asyncpg://antos@localhost:54329/antos_test. Every test drops and
re-creates the schema (the audit tables cannot be truncated, by design), and
the tamper tests need a superuser connection to disable triggers.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
import yaml
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from antos_api import anchor, audit, notify, service
from antos_api.app import create_app
from antos_api.auth import OidcVerifier, Rbac, new_api_key
from antos_api.gateway import ModelGateway, ModelOutput
from antos_api.ratelimit import MemoryRateLimiter
from antos_api.settings import Settings
from antos_api.tables import ApiKey, AuditEntry, DecisionRow, OutboxRow
from antos_core.contracts import Action, LocalFitInput

DB_URL = os.environ.get("ANTOS_TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[3]
PROFILE_DIR = ROOT / "profiles" / "africa"
NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
ISSUER, AUDIENCE = "https://id.gov.gh/realms/antos", "antos-api"

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(not DB_URL, reason="set ANTOS_TEST_DATABASE_URL to run database tests"),
]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def fresh_db() -> None:
    cfg = Config(str(ROOT / "services" / "api" / "alembic.ini"))
    cfg.attributes["database_url"] = DB_URL
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


@dataclass
class Platform:
    client: httpx.AsyncClient
    rt: service.Runtime
    clock: Clock
    engine: AsyncEngine
    signing_key: rsa.RSAPrivateKey
    app: FastAPI

    def set_limits(self, **limits: int) -> None:
        settings: Settings = self.app.state.settings
        self.app.state.settings = settings.model_copy(update=limits)

    async def headers(self, *roles: str, nation: str | None = "GH") -> dict[str, str]:
        key_id, secret_hash, token = new_api_key()
        async with self.rt.sessions.begin() as session:
            session.add(ApiKey(key_id=key_id, secret_hash=secret_hash, name="test",
                               roles=list(roles), nation_id=nation, created_by="test"))
        return {"X-API-Key": token}

    def bearer(self, *roles: str, nation: str = "GH") -> dict[str, str]:
        now = datetime.now(UTC)
        token = jwt.encode({"sub": "ama", "iss": ISSUER, "aud": AUDIENCE, "iat": now,
                            "exp": now + timedelta(minutes=5), "nation_id": nation,
                            "realm_access": {"roles": list(roles)}},
                           self.signing_key, algorithm="RS256")
        return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def p(fresh_db: None) -> AsyncIterator[Platform]:
    assert DB_URL
    engine = create_async_engine(DB_URL)
    clock = Clock()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signer = Ed25519PrivateKey.generate()
    rt = service.Runtime(sessions=async_sessionmaker(engine, expire_on_commit=False),
                         rbac=Rbac.load(PROFILE_DIR / "roles.yaml"), gateway=ModelGateway(),
                         clock=clock, anchor_signer=signer,
                         anchor_keys={anchor.key_id(signer.public_key()): signer.public_key()})
    app = create_app(Settings(database_url=DB_URL, profile_dir=PROFILE_DIR), runtime=rt,
                     oidc=OidcVerifier(issuer=ISSUER, audience=AUDIENCE, key=key.public_key()),
                     limiter=MemoryRateLimiter())
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://antos") as client:
            yield Platform(client, rt, clock, engine, key, app)
    await engine.dispose()


def bed(rate: float, *, source: str = "korle_bu_emr", minutes_ago: int = 20,
        **extra: Any) -> dict[str, Any]:
    return {"signal_type": "bed_capacity_signal", "source_id": source,
            "source_type": "formal_institution", "sector": "health",
            "observed_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
            "payload": {"occupancy_rate": rate, "source_ref": f"{source}-ICU"},
            "raw_hash": f"sha256:{source}", **extra}


ALL_FIT = dict.fromkeys(LocalFitInput.model_fields, True)


async def resolve(p: Platform, headers: dict[str, str], **body: Any) -> dict[str, Any]:
    base = {"objective": "Assess ICU capacity at Korle Bu", "sector": "health",
            "local_fit": ALL_FIT}
    r = await p.client.post("/v1/decisions/resolve", json={**base, **body}, headers=headers)
    assert r.status_code == 200, r.text
    result: dict[str, Any] = r.json()
    return result


# ── Ingest ───────────────────────────────────────────────────


async def test_ingest_is_idempotent_and_assigns_ids(p: Platform) -> None:
    h = await p.headers("operator")
    first = await p.client.post("/v1/signals/ingest", json=bed(0.85), headers=h)
    again = await p.client.post("/v1/signals/ingest",
                                json=bed(0.85, signal_id="SIG-MINE"), headers=h)
    assert first.status_code == again.status_code == 200
    assert first.json()["duplicate"] is False and again.json()["duplicate"] is True
    assert first.json()["signal_ref"] == again.json()["signal_ref"] != "SIG-MINE"
    # health half-life is 1 h, observed 20 min ago
    assert first.json()["freshness_at_ingest"] == pytest.approx(0.5 ** (1 / 3))


async def test_ingest_rejects_future_and_unknown_sector(p: Platform) -> None:
    h = await p.headers("operator")
    future = bed(0.8, minutes_ago=-60)
    r = await p.client.post("/v1/signals/ingest", json=future, headers=h)
    assert r.status_code == 422 and "future" in r.text
    r = await p.client.post("/v1/signals/bulk-ingest", headers=h, json={
        "signals": [bed(0.8), {**bed(0.8, source="x"), "sector": "mining"}]})
    assert (r.json()["accepted_count"], r.json()["rejected_count"]) == (1, 1)


# ── Decisions, audit, replay ─────────────────────────────────


async def test_resolve_store_and_replay_end_to_end(p: Platform) -> None:
    op, analyst, auditor = (await p.headers("operator"), await p.headers("analyst"),
                            await p.headers("regulator"))
    refs = [(await p.client.post("/v1/signals/ingest", json=s, headers=op)).json()["signal_ref"]
            for s in (bed(0.85), bed(0.86, source="ghs_dhims2"))]
    out = await resolve(p, analyst, signal_refs=refs,
                        hae={"worker_dignity_preserved": False})
    decision = out["decision"]
    assert decision["validation_state"] == "trusted"
    assert decision["human_escalation_required"] and not decision["allowed_for_action"]
    assert out["escalation"]["assigned_role"] == "sovereign_admin"

    by_ref = await p.client.get(f"/v1/decisions/{out['audit_ref']}", headers=analyst)
    by_id = await p.client.get(f"/v1/decisions/{out['decision_id']}", headers=analyst)
    assert by_ref.json()["audit_ref"] == by_id.json()["audit_ref"] == out["audit_ref"]

    replay = (await p.client.post("/v1/audit/replay", json={"audit_ref": out["audit_ref"]},
                                  headers=auditor)).json()
    assert replay["match"] and replay["projection_matches_audit"]
    assert replay["recorded_decision_hash"] == replay["replayed_decision_hash"]

    chain = (await p.client.get("/v1/audit/verify", headers=auditor)).json()
    assert chain["ok"] and chain["chain"]["entries_checked"] >= 5


async def test_resolve_needs_signals(p: Platform) -> None:
    r = await p.client.post("/v1/decisions/resolve", headers=await p.headers("analyst"),
                            json={"objective": "x", "sector": "health"})
    assert r.status_code == 422


async def test_old_decisions_replay_under_the_config_they_ran_under(p: Platform) -> None:
    analyst, admin, regulator = (await p.headers("analyst"), await p.headers("sovereign_admin"),
                                 await p.headers("regulator"))
    before = await resolve(p, analyst, signals=[bed(0.85), bed(0.86, source="ghs_dhims2")])

    docs = {n: yaml.safe_load((PROFILE_DIR / f"{n}.yaml").read_text(encoding="utf-8"))
            for n in ("manifest", "sector_packs")}
    docs["sector_packs"]["packs"]["health"]["validation_thresholds"]["trusted"] = 0.95
    body = {"manifest": docs["manifest"], "sector_packs": docs["sector_packs"],
            "recalibration_rationale": "Tighten health trust threshold after pilot review"}
    assert (await p.client.put("/v1/admin/config", json=body,
                               headers=await p.headers("administrator"))).status_code == 403
    assert (await p.client.put("/v1/admin/config", headers=admin,
                               json={**body, "recalibration_rationale": "short"})
            ).status_code == 422
    put = await p.client.put("/v1/admin/config", json=body, headers=admin)
    assert put.status_code == 200 and put.json()["config_ref"] != before["config_hash"]

    p.clock.now += timedelta(seconds=1)
    after = await resolve(p, analyst, signals=[bed(0.85), bed(0.86, source="ghs_dhims2")])
    assert after["config_hash"] == put.json()["config_ref"]
    assert after["decision"]["validation_state"] == "provisional"

    replay = (await p.client.post("/v1/audit/replay", json={"audit_ref": before["audit_ref"]},
                                  headers=regulator)).json()
    assert replay["match"] and replay["config_hash"] == before["config_hash"]


# ── Audit integrity ──────────────────────────────────────────


@pytest.mark.parametrize("statement", [
    "UPDATE audit_log SET actor = 'mallory'",
    "DELETE FROM audit_log",
    "TRUNCATE audit_log CASCADE",
    "UPDATE decisions SET action = 'proceed'",
    "DELETE FROM decisions",
    "UPDATE signals SET payload = '{}'",
    "UPDATE config_versions SET rationale = 'rewritten'",
    "DELETE FROM config_versions",
])
async def test_audited_tables_reject_mutation(p: Platform, statement: str) -> None:
    # Row triggers only fire on rows that exist, so populate every table first.
    ref = (await p.client.post("/v1/signals/ingest", json=bed(0.85),
                               headers=await p.headers("operator"))).json()["signal_ref"]
    await resolve(p, await p.headers("analyst"), signal_refs=[ref])
    with pytest.raises(DBAPIError, match=r"append-only|immutable"):
        async with p.engine.begin() as conn:
            await conn.execute(text(statement))


async def _tamper(p: Platform, sql: str) -> None:
    async with p.engine.begin() as conn:  # needs a superuser: this is the insider threat
        await conn.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only"))
        await conn.execute(text(sql))
        await conn.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_append_only"))


async def test_payload_tampering_is_detected(p: Platform) -> None:
    out = await resolve(p, await p.headers("analyst"), signals=[bed(0.85)])
    await _tamper(p, "UPDATE audit_log SET payload = replace(payload, '\"defer\"', '\"proceed\"')"
                     " WHERE event_type = 'decision.recorded'")
    regulator = await p.headers("regulator")
    chain = (await p.client.get("/v1/audit/verify", headers=regulator)).json()
    assert not chain["ok"] and "payload" in chain["chain"]["problem"]
    r = await p.client.post("/v1/audit/replay", json={"audit_ref": out["audit_ref"]},
                            headers=regulator)
    assert r.status_code == 422


async def test_rehashed_tampering_is_still_detected(p: Platform) -> None:
    await resolve(p, await p.headers("analyst"), signals=[bed(0.85)])
    await _tamper(p, "UPDATE audit_log SET actor = 'mallory', "
                     "payload_hash = encode(sha256(convert_to(payload, 'UTF8')), 'hex')"
                     " WHERE event_type = 'decision.recorded'")
    chain = (await p.client.get("/v1/audit/verify", headers=await p.headers("regulator"))).json()
    assert not chain["ok"] and "entry_hash" in chain["chain"]["problem"]


async def test_deleted_entry_breaks_the_chain(p: Platform) -> None:
    await resolve(p, await p.headers("analyst"), signals=[bed(0.85)])
    async with p.engine.begin() as conn:
        await conn.execute(text("ALTER TABLE decisions DROP CONSTRAINT decisions_audit_seq_fkey"))
    await _tamper(p, "DELETE FROM audit_log WHERE event_type = 'config.activated'")
    chain = (await p.client.get("/v1/audit/verify", headers=await p.headers("regulator"))).json()
    assert not chain["ok"] and "prev_hash" in chain["chain"]["problem"]


async def test_concurrent_writers_keep_one_chain(p: Platform) -> None:
    async def write(i: int) -> None:
        async with p.rt.sessions.begin() as session:
            await audit.append(session, "test.event", f"T-{i}", "test", {"i": i})

    await asyncio.gather(*(write(i) for i in range(25)))
    async with p.rt.sessions() as session:
        report = await audit.verify_chain(session)
    assert report.ok and report.entries_checked >= 26


# ── Authentication and authorisation ─────────────────────────


async def test_requests_without_valid_credentials_are_rejected(p: Platform) -> None:
    assert (await p.client.get("/v1/escalations")).status_code == 401
    bad = {"X-API-Key": "antos_0000.nope"}
    assert (await p.client.get("/v1/escalations", headers=bad)).status_code == 401


async def test_role_headers_are_ignored(p: Platform) -> None:
    h = {**(await p.headers("operator")), "X-Role": "sovereign_admin",
         "X-User-Role": "sovereign_admin"}
    assert (await p.client.get("/v1/admin/config", headers=h)).status_code == 403


async def test_permissions_follow_roles(p: Platform) -> None:
    analyst = await p.headers("analyst")
    assert (await p.client.post("/v1/signals/ingest", json=bed(0.8),
                                headers=analyst)).status_code == 403
    operator = await p.headers("operator")
    assert (await p.client.post("/v1/audit/replay", json={"audit_ref": "AUD-X"},
                                headers=operator)).status_code == 403


async def test_nation_binding(p: Platform) -> None:
    ghana_op = await p.headers("operator", nation="GH")
    r = await p.client.post("/v1/signals/ingest", json={**bed(0.8), "nation_id": "KE"},
                            headers=ghana_op)
    assert r.status_code == 403


async def test_revoked_key_is_rejected(p: Platform) -> None:
    h = await p.headers("operator")
    key_id = h["X-API-Key"].removeprefix("antos_").split(".")[0]
    async with p.rt.sessions.begin() as session:
        await session.execute(update(ApiKey).where(ApiKey.key_id == key_id)
                              .values(revoked_at=NOW))
    assert (await p.client.post("/v1/signals/ingest", json=bed(0.8),
                                headers=h)).status_code == 401


async def test_oidc_bearer_token(p: Platform) -> None:
    r = await p.client.get("/v1/escalations", headers=p.bearer("sector_lead"))
    assert r.status_code == 200


async def test_api_keys_issued_through_the_api_work(p: Platform) -> None:
    admin = await p.headers("administrator")
    r = await p.client.post("/v1/admin/api-keys", headers=admin,
                            json={"name": "dhims2-adapter", "roles": ["operator"],
                                  "nation_id": "GH"})
    assert r.status_code == 200
    new = {"X-API-Key": r.json()["token"]}
    assert (await p.client.post("/v1/signals/ingest", json=bed(0.8),
                                headers=new)).status_code == 200
    bad = await p.client.post("/v1/admin/api-keys", headers=admin,
                              json={"name": "x", "roles": ["emperor"], "nation_id": "GH"})
    assert bad.status_code == 422


# ── Escalations and SLAs ─────────────────────────────────────


async def test_escalation_lifecycle_and_routing(p: Platform) -> None:
    out = await resolve(p, await p.headers("analyst"), signals=[bed(0.85)],
                        hae={"worker_dignity_preserved": False})
    esc_id = out["escalation"]["escalation_id"]
    lead, sovereign = await p.headers("sector_lead"), await p.headers("sovereign_admin")

    lead_queue = (await p.client.get("/v1/escalations", headers=lead)).json()
    assert esc_id not in [e["escalation_id"] for e in lead_queue]
    assert (await p.client.post(f"/v1/escalations/{esc_id}/acknowledge",
                                headers=lead)).status_code == 403

    queue = (await p.client.get("/v1/escalations?status=open", headers=sovereign)).json()
    assert [e["escalation_id"] for e in queue] == [esc_id]
    ack = await p.client.post(f"/v1/escalations/{esc_id}/acknowledge", headers=sovereign)
    assert ack.json()["status"] == "acknowledged"
    assert (await p.client.post(f"/v1/escalations/{esc_id}/acknowledge",
                                headers=sovereign)).status_code == 409
    assert (await p.client.post(f"/v1/escalations/{esc_id}/resolve", json={},
                                headers=sovereign)).status_code == 422
    done = await p.client.post(f"/v1/escalations/{esc_id}/resolve", headers=sovereign,
                               json={"note": "Spoke with ward leads; staffing restored."})
    assert done.json()["status"] == "resolved"


async def test_regulator_can_review_any_escalation(p: Platform) -> None:
    out = await resolve(p, await p.headers("analyst"), signals=[bed(0.85)],
                        hae={"worker_dignity_preserved": False})
    r = await p.client.post(f"/v1/escalations/{out['escalation']['escalation_id']}/resolve",
                            json={"note": "Override review"}, headers=await p.headers("regulator"))
    assert r.status_code == 200


async def test_sla_breach_is_marked_once(p: Platform) -> None:
    lead = await p.headers("sector_lead")
    r = await p.client.post("/v1/escalations/create", headers=lead, json={
        "objective": "Fertiliser shortfall in Northern Region", "sector": "agriculture",
        "priority": "high", "reason": "Cooperatives report no stock"})
    esc = r.json()
    assert (esc["assigned_role"], esc["sla_minutes"]) == ("sector_lead", 30)

    p.clock.now += timedelta(minutes=29)
    assert await service.sweep_sla(p.rt) == []
    p.clock.now += timedelta(minutes=2)
    assert await service.sweep_sla(p.rt) == [esc["escalation_id"]]
    assert await service.sweep_sla(p.rt) == []

    [row] = (await p.client.get("/v1/escalations", headers=lead)).json()
    assert row["breached_at"] is not None and row["status"] == "open"
    chain = (await p.client.get("/v1/audit/verify", headers=await p.headers("regulator"))).json()
    assert chain["ok"]


# ── Step 14 through the gateway ──────────────────────────────


class FakeModel:
    provider, model = "anthropic", "claude-opus-5-5"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def complete(self, system: str, user: str) -> tuple[ModelOutput, str, str | None]:
        if self.fail:
            raise TimeoutError("upstream timeout")
        out = ModelOutput(action=Action.PROCEED, primary_recommendation="Proceed now.",
                          ubuntu_note="u", hae_note="h", escalation_suggested=False,
                          cited_signal_ids=["SIG-INVENTED"])
        return out, out.model_dump_json(), "end_turn"


def berth(rate: float, source: str) -> dict[str, Any]:
    return {"signal_type": "berth_occupancy", "source_id": source, "sector": "ports",
            "source_type": "formal_institution",
            "observed_at": (NOW - timedelta(minutes=10)).isoformat(),
            "payload": {"occupancy_rate": rate, "source_ref": source}}


async def _audit_payload(p: Platform, audit_ref: str) -> Any:
    async with p.rt.sessions() as session:
        row = await session.get(DecisionRow, audit_ref)
        assert row is not None
        _, payload = await audit.load_payload(session, row.audit_seq)
    return payload


async def test_model_cannot_override_blocked_state_and_exchange_is_audited(p: Platform) -> None:
    p.rt.gateway = ModelGateway(cloud=FakeModel())
    out = await resolve(p, await p.headers("analyst"), sector="ports", objective="Berth plan",
                        signals=[berth(0.10, "gpha"), berth(0.95, "terminal_ops")])
    rec = out["decision"]["recommended_action"]
    assert out["decision"]["validation_state"] == "blocked"
    assert rec["action"] == "block" and rec["cited_signal_ids"] == []
    assert rec["produced_by"] == "llm:anthropic:claude-opus-5-5"

    payload = await _audit_payload(p, out["audit_ref"])
    assert payload["model_exchange"]["response_text"]
    assert payload["model_exchange"]["system"].startswith("You are the step-14")
    replay = (await p.client.post("/v1/audit/replay", json={"audit_ref": out["audit_ref"]},
                                  headers=await p.headers("regulator"))).json()
    assert replay["match"] and replay["produced_by"].startswith("llm:")


async def test_sovereign_sector_does_not_reach_the_cloud_model(p: Platform) -> None:
    p.rt.gateway = ModelGateway(cloud=FakeModel())
    out = await resolve(p, await p.headers("analyst"), signals=[bed(0.85)])
    assert out["decision"]["recommended_action"]["produced_by"] == "rule_based"
    assert (await _audit_payload(p, out["audit_ref"]))["model_exchange"] is None


async def test_model_failure_falls_back_and_is_recorded(p: Platform) -> None:
    p.rt.gateway = ModelGateway(cloud=FakeModel(fail=True))
    out = await resolve(p, await p.headers("analyst"), sector="ports", objective="Berth plan",
                        signals=[berth(0.50, "gpha")])
    rec = out["decision"]["recommended_action"]
    assert rec["produced_by"] == "rule_based" and "TimeoutError" in rec["note"]
    exchange = (await _audit_payload(p, out["audit_ref"]))["model_exchange"]
    assert "upstream timeout" in exchange["error"]


# ── Rate limits ──────────────────────────────────────────────


async def test_caller_rate_limit(p: Platform) -> None:
    p.set_limits(rate_limit_per_minute=3)
    h = await p.headers("sector_lead")
    codes = [(await p.client.get("/v1/escalations", headers=h)).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    r = await p.client.get("/v1/escalations", headers=h)
    assert int(r.headers["Retry-After"]) >= 1
    # Limits are per caller: someone else is unaffected.
    other = await p.headers("sector_lead")
    assert (await p.client.get("/v1/escalations", headers=other)).status_code == 200


async def test_decisions_have_their_own_lower_limit(p: Platform) -> None:
    p.set_limits(rate_limit_decisions_per_minute=1)
    h = await p.headers("analyst")
    await resolve(p, h, signals=[bed(0.85)])
    r = await p.client.post("/v1/decisions/resolve", headers=h, json={
        "objective": "again", "sector": "health", "signals": [bed(0.8)]})
    assert r.status_code == 429


async def test_repeated_auth_failures_lock_out_the_address(p: Platform) -> None:
    p.set_limits(rate_limit_auth_failures_per_minute=3)
    good = await p.headers("sector_lead")
    for _ in range(3):
        bad = await p.client.get("/v1/escalations", headers={"X-API-Key": "antos_x.guess"})
        assert bad.status_code == 401
    # Even a valid key is refused from that address until the window passes.
    assert (await p.client.get("/v1/escalations", headers=good)).status_code == 429


# ── Notifications ────────────────────────────────────────────


class Inbox:
    def __init__(self, fail: bool = False) -> None:
        self.fail, self.sent = fail, []

    async def send(self, event: str, ref: str, payload: dict[str, Any]) -> None:
        if self.fail:
            raise ConnectionError("gateway down")
        self.sent.append((event, ref, payload))


async def test_escalations_notify_on_open_and_breach(p: Platform) -> None:
    out = await resolve(p, await p.headers("analyst"), signals=[bed(0.85)],
                        hae={"worker_dignity_preserved": False})
    esc_id = out["escalation"]["escalation_id"]
    inbox = Inbox()
    report = await notify.deliver_pending(p.rt.sessions, inbox, p.clock.now)
    assert report.delivered == 1
    [(event, ref, payload)] = inbox.sent
    assert (event, ref, payload["assigned_role"]) == ("escalation.opened", esc_id,
                                                      "sovereign_admin")
    assert "occupancy_rate" not in str(payload)  # no signal data leaves in notifications

    p.clock.now += timedelta(minutes=16)
    await service.sweep_sla(p.rt)
    await notify.deliver_pending(p.rt.sessions, inbox, p.clock.now)
    assert [e for e, _, _ in inbox.sent] == ["escalation.opened", "escalation.sla_breached"]
    # Delivered notifications are not sent twice.
    assert (await notify.deliver_pending(p.rt.sessions, inbox, p.clock.now)).delivered == 0


async def test_failed_notifications_retry_with_backoff_then_give_up(p: Platform) -> None:
    await resolve(p, await p.headers("analyst"), signals=[bed(0.85)],
                  hae={"worker_dignity_preserved": False})
    down = Inbox(fail=True)
    first = await notify.deliver_pending(p.rt.sessions, down, p.clock.now)
    assert first.retrying == 1
    # Not due again yet.
    assert (await notify.deliver_pending(p.rt.sessions, down, p.clock.now)).retrying == 0
    for _ in range(notify.MAX_ATTEMPTS):
        p.clock.now += notify.MAX_BACKOFF
        await notify.deliver_pending(p.rt.sessions, down, p.clock.now)
    async with p.rt.sessions() as session:
        row = await session.scalar(select(OutboxRow))
    assert row is not None and row.status == "failed" and "gateway down" in (row.last_error or "")


# ── Signed anchors ───────────────────────────────────────────


async def test_anchor_is_signed_and_verifies(p: Platform) -> None:
    await resolve(p, await p.headers("analyst"), signals=[bed(0.85)])
    auditor = await p.headers("regulator")
    first = (await p.client.post("/v1/audit/anchor", headers=auditor)).json()
    assert first["anchored"]
    # Nothing new since (only the anchor's own entry), so no second anchor.
    assert not (await p.client.post("/v1/audit/anchor", headers=auditor)).json()["anchored"]
    report = (await p.client.get("/v1/audit/verify", headers=auditor)).json()
    assert report["ok"] and report["anchors"]["anchors_checked"] == 1
    with pytest.raises(DBAPIError, match=r"append-only"):
        async with p.engine.begin() as conn:
            await conn.execute(text("UPDATE audit_anchors SET head_hash = 'x'"))


async def test_anchor_catches_a_consistently_rewritten_history(p: Platform) -> None:
    """The insider attack the hash chain alone cannot catch: change an old entry and
    recompute every later hash so the chain is internally consistent again."""
    await resolve(p, await p.headers("analyst"), signals=[bed(0.85)])
    auditor = await p.headers("regulator")
    await p.client.post("/v1/audit/anchor", headers=auditor)

    async with p.rt.sessions.begin() as session:
        await session.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only"))
        prev = audit.GENESIS
        for entry in (await session.scalars(select(AuditEntry).order_by(AuditEntry.seq))).all():
            if entry.event_type == "decision.recorded":
                entry.actor = "mallory"
            entry.payload_hash = audit._sha256(entry.payload)
            entry.prev_hash = prev
            entry.entry_hash = audit.expected_entry_hash(entry, prev)
            prev = entry.entry_hash
        await session.flush()
        await session.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_append_only"))

    report = (await p.client.get("/v1/audit/verify", headers=auditor)).json()
    assert report["chain"]["ok"]  # the rewrite is internally consistent...
    assert not report["anchors"]["ok"]  # ...but no longer reaches the signed head
    assert "rewritten" in report["anchors"]["problems"][0]
    # And a broken chain is never signed.
    await _tamper(p, "UPDATE audit_log SET actor = 'eve' WHERE seq = 1")
    assert (await p.client.post("/v1/audit/anchor", headers=auditor)).status_code == 409


async def test_anchor_from_an_untrusted_key_fails(p: Platform) -> None:
    await resolve(p, await p.headers("analyst"), signals=[bed(0.85)])
    await p.client.post("/v1/audit/anchor", headers=await p.headers("regulator"))
    p.rt.anchor_keys = {}
    report = (await p.client.get("/v1/audit/verify", headers=await p.headers("regulator"))).json()
    assert not report["ok"] and "untrusted" in report["anchors"]["problems"][0]


# ── Replay everything ────────────────────────────────────────


async def test_replay_all_covers_every_decision(p: Platform) -> None:
    analyst = await p.headers("analyst")
    for i, rate in enumerate((0.85, 0.40, 0.95)):
        p.clock.now = NOW + timedelta(seconds=i)
        await resolve(p, analyst, signals=[bed(rate), bed(rate + 0.01, source="ghs_dhims2")])
    regulator = await p.headers("regulator")
    report = (await p.client.post("/v1/audit/replay-all", headers=regulator)).json()
    assert report["ok"] and report["total"] == report["matched"] == 3

    await _tamper(p, "UPDATE audit_log SET payload = replace(payload, 'ICU', 'XXX')"
                     " WHERE event_type = 'decision.recorded'")
    report = (await p.client.post("/v1/audit/replay-all", headers=regulator)).json()
    assert not report["ok"] and len(report["errors"]) == 3


# ── Dashboard views ──────────────────────────────────────────


async def test_situation_room_reports_real_data_and_no_data(p: Platform) -> None:
    op, lead = await p.headers("operator"), await p.headers("sector_lead")
    ref = (await p.client.post("/v1/signals/ingest", json=bed(0.85, minutes_ago=60),
                               headers=op)).json()["signal_ref"]
    await resolve(p, await p.headers("analyst"), signal_refs=[ref],
                  hae={"worker_dignity_preserved": False})
    room = (await p.client.post("/v1/core/situation-room", json={}, headers=lead)).json()
    by_sector = {s["sector"]: s for s in room["sectors"]}
    assert len(by_sector) == 8
    health = by_sector["health"]
    assert health["status"] == "critical"  # an open critical escalation
    assert health["signals_in_window"] == 1 and health["decisions_in_window"] == 1
    assert health["mean_freshness"] == pytest.approx(0.5)  # 1 h old, half-life 1 h
    assert health["open_escalations"] == {"critical": 1}
    # Sectors without data say so; nothing is invented.
    ports = by_sector["ports"]
    assert ports["status"] == "no_data" and ports["mean_freshness"] is None
    assert ports["hae_alignment_mean"] is None and ports["latest_decision"] is None
    assert [e["sector"] for e in room["active_escalations"]] == ["health"]


async def test_situation_room_window_and_breach(p: Platform) -> None:
    lead = await p.headers("sector_lead")
    await p.client.post("/v1/escalations/create", headers=lead, json={
        "objective": "Corridor delay", "sector": "transport", "priority": "high",
        "reason": "Trucks held at Aflao"})
    p.clock.now += timedelta(hours=2)
    await service.sweep_sla(p.rt)
    room = (await p.client.post("/v1/core/situation-room", headers=lead,
                                json={"sectors": ["transport"], "time_window_hours": 1})).json()
    [transport] = room["sectors"]
    assert transport["status"] == "critical" and transport["breached_escalations"] == 1
    bad = await p.client.post("/v1/core/situation-room", headers=lead,
                              json={"sectors": ["mining"]})
    assert bad.status_code == 422


async def test_situation_room_requires_permission_and_nation(p: Platform) -> None:
    op = await p.headers("operator")
    assert (await p.client.post("/v1/core/situation-room", json={},
                                headers=op)).status_code == 403
    lead = await p.headers("sector_lead", nation="GH")
    assert (await p.client.post("/v1/core/situation-room", json={"nation_id": "NG"},
                                headers=lead)).status_code == 403


async def test_me_sectors_decision_list_and_audit_browser(p: Platform) -> None:
    h = await p.headers("analyst", "regulator")
    me = (await p.client.get("/v1/me", headers=h)).json()
    assert me["roles"] == ["analyst", "regulator"] and "audit_mode" in me["permissions"]
    sectors = (await p.client.get("/v1/sectors", headers=h)).json()
    assert {s["sector_id"] for s in sectors} >= {"health", "ports"}
    health = next(s for s in sectors if s["sector_id"] == "health")
    assert health["validation_thresholds"] == {"trusted": 0.88, "provisional": 0.60}

    for i in range(3):
        p.clock.now = NOW + timedelta(seconds=i)
        await resolve(p, h, signals=[bed(0.80 + i / 100)])
    listed = (await p.client.get("/v1/decisions?limit=2", headers=h)).json()
    assert len(listed) == 2 and listed[0]["audit_seq"] > listed[1]["audit_seq"]
    older = (await p.client.get(f"/v1/decisions?before_seq={listed[-1]['audit_seq']}",
                                headers=h)).json()
    assert len(older) == 1

    entries = (await p.client.get("/v1/audit/entries?event_type=decision.recorded",
                                  headers=h)).json()
    assert len(entries) == 3 and "payload" not in entries[0]
    one = (await p.client.get(f"/v1/audit/entries/{entries[0]['seq']}", headers=h)).json()
    assert one["payload"]["audit"]["decision_id"] == listed[0]["decision_id"]


async def test_inline_signals_are_stored_with_the_decision(p: Platform) -> None:
    analyst = await p.headers("analyst")
    out = await resolve(p, analyst, signals=[bed(0.85), bed(0.86, source="ghs_dhims2")])
    cited = out["decision"]["recommended_action"]["cited_signal_ids"]
    async with p.rt.sessions() as session:
        stored = await service.load_signals(session, cited, "GH")
    assert len(stored) == 2
    room = (await p.client.post("/v1/core/situation-room", json={"sectors": ["health"]},
                                headers=await p.headers("sector_lead"))).json()
    assert room["sectors"][0]["signals_in_window"] == 2
    assert room["sectors"][0]["status"] == "stable"  # trusted, proceed, no escalation
    # A decision that says "investigate" puts the sector in attention.
    p.clock.now += timedelta(seconds=1)
    await resolve(p, analyst, signals=[bed(0.40), bed(0.95, source="ghs_dhims2")],
                  objective="Conflicting bed counts")
    room = (await p.client.post("/v1/core/situation-room", json={"sectors": ["health"]},
                                headers=await p.headers("sector_lead"))).json()
    assert room["sectors"][0]["status"] in ("attention", "critical")
    future = await p.client.post("/v1/decisions/resolve", headers=analyst, json={
        "objective": "x", "sector": "health", "signals": [bed(0.8, minutes_ago=-60)]})
    assert future.status_code == 422 and "future" in future.text


async def test_situation_room_timeline_and_pulse(p: Platform) -> None:
    analyst, lead = await p.headers("analyst"), await p.headers("sector_lead")
    # One decision in the previous 24 h window, two in the current one.
    # Signals are observed 10 minutes before each decision.
    p.clock.now = NOW - timedelta(hours=30)
    await resolve(p, analyst, signals=[bed(0.85, minutes_ago=30 * 60 + 10)], objective="old")
    p.clock.now = NOW - timedelta(hours=5)
    await resolve(p, analyst, objective="trusted one",
                  signals=[bed(0.85, minutes_ago=310),
                           bed(0.86, source="ghs_dhims2", minutes_ago=310)])
    p.clock.now = NOW - timedelta(hours=4, minutes=30)
    await resolve(p, analyst, objective="blocked one",
                  signals=[bed(0.10, minutes_ago=280),
                           bed(0.95, source="ghs_dhims2", minutes_ago=280)])
    p.clock.now = NOW
    room = (await p.client.post("/v1/core/situation-room", headers=lead,
                                json={"sectors": ["health"]})).json()
    assert room["bucket_minutes"] == 60
    pulse = room["pulse"]
    assert (pulse["decisions_in_window"], pulse["decisions_previous_window"]) == (2, 1)
    assert pulse["open_escalations"] == {"critical": 1}
    [health] = room["sectors"]
    timeline = health["timeline"]
    assert len(timeline) == 24 and sum(b["decisions"] for b in timeline) == 2
    # Both decisions fall 19-20 h into the window; the bucket shows the worse state.
    busy = [b for b in timeline if b["decisions"]]
    assert len(busy) == 1 and busy[0]["worst_state"] == "blocked"
    assert sum(b["signals"] for b in timeline) == health["signals_in_window"]

    # The blocked decision's critical escalation (15 min SLA) was due long ago.
    p.clock.now = NOW - timedelta(hours=4, minutes=20)
    room = (await p.client.post("/v1/core/situation-room", headers=lead,
                                json={"sectors": ["health"]})).json()
    assert room["pulse"]["at_risk_escalations"] == 1


async def test_node_status(p: Platform) -> None:
    h = await p.headers("operator")
    before = (await p.client.get("/v1/node", headers=h)).json()
    assert before["last_anchor_seq"] is None and before["anchor_signing"] is True
    await p.client.post("/v1/audit/anchor", headers=await p.headers("regulator"))
    after = (await p.client.get("/v1/node", headers=h)).json()
    assert after["last_anchor_seq"] is not None and after["entries_since_anchor"] == 1


# ── Interface data (master prompt) ───────────────────────────


async def test_decision_carries_recorded_evidence_and_breakdown(p: Platform) -> None:
    out = await resolve(p, await p.headers("analyst"),
                        signals=[bed(0.10), bed(0.95, source="ghs_dhims2")])
    assert len(out["evidence"]) == 2
    first = out["evidence"][0]
    assert first["source_id"] == "korle_bu_emr" and first["freshness"] is not None
    assert first["source_reliability"] == pytest.approx(0.80)
    assert len(out["conflicts"]) == 1 and out["conflicts"][0]["field"] == "occupancy_rate"
    assert set(out["confidence_breakdown"]["inputs"]) >= {"evidence_strength", "signal_freshness"}
    again = (await p.client.get(f"/v1/decisions/{out['audit_ref']}",
                                headers=await p.headers("analyst"))).json()
    assert again["evidence"] == out["evidence"] and again["evaluated_at"]


async def test_signals_list_with_freshness_and_staleness(p: Platform) -> None:
    op = await p.headers("operator")
    await p.client.post("/v1/signals/bulk-ingest", headers=op, json={"signals": [
        bed(0.85, minutes_ago=30), bed(0.80, source="ghs_dhims2", minutes_ago=180)]})
    r = (await p.client.get("/v1/signals?sector=health", headers=op)).json()
    assert r["summary"]["received"] == 2 and r["summary"]["sources"] == 2
    fresh, old = r["signals"]
    assert fresh["reading"] == 0.85 and fresh["reading_field"] == "occupancy_rate"
    assert not fresh["stale"] and old["stale"]  # 3 h old, half-life 1 h: 0.125 < 0.25
    assert (await p.client.get("/v1/signals", headers=await p.headers("citizen_observer"))
            ).status_code == 403


async def test_decisions_date_range(p: Platform) -> None:
    analyst = await p.headers("analyst")
    p.clock.now = NOW - timedelta(days=3)
    await resolve(p, analyst, signals=[bed(0.85, minutes_ago=3 * 24 * 60 + 10)], objective="old")
    p.clock.now = NOW
    await resolve(p, analyst, signals=[bed(0.85)], objective="new")
    since = (NOW - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    rows = (await p.client.get(f"/v1/decisions?since={since}", headers=analyst)).json()
    assert [r["objective"] for r in rows] == ["new"]


async def test_api_keys_list_and_revoke(p: Platform) -> None:
    admin = await p.headers("administrator")
    made = (await p.client.post("/v1/admin/api-keys", headers=admin, json={
        "name": "dhis2-adapter", "roles": ["operator"], "nation_id": "GH"})).json()
    listed = (await p.client.get("/v1/admin/api-keys", headers=admin)).json()
    assert made["key_id"] in [k["key_id"] for k in listed]
    assert all("secret_hash" not in k for k in listed)
    r = await p.client.post(f"/v1/admin/api-keys/{made['key_id']}/revoke", headers=admin)
    assert r.status_code == 200
    again = await p.client.post(f"/v1/admin/api-keys/{made['key_id']}/revoke", headers=admin)
    assert again.status_code == 409
    assert (await p.client.post("/v1/signals/ingest", json=bed(0.8),
                                headers={"X-API-Key": made["token"]})).status_code == 401


async def test_replay_all_is_recorded(p: Platform) -> None:
    await resolve(p, await p.headers("analyst"), signals=[bed(0.85)])
    regulator = await p.headers("regulator")
    await p.client.post("/v1/audit/replay-all", headers=regulator)
    [entry] = (await p.client.get("/v1/audit/entries?event_type=audit.replay_checked",
                                  headers=regulator)).json()
    full = (await p.client.get(f"/v1/audit/entries/{entry['seq']}", headers=regulator)).json()
    assert full["payload"]["ok"] and full["payload"]["total"] == 1


# ── Serverless hosting ───────────────────────────────────────


@pytest.fixture
async def serverless(fresh_db: None) -> AsyncIterator[httpx.AsyncClient]:
    """The app as Vercel runs it: no start-up event, no connection pool."""
    assert DB_URL
    settings = Settings(database_url=DB_URL, profile_dir=PROFILE_DIR, serverless=True,
                        trust_forwarded_for=True, cron_secret="s3cret",
                        rate_limit_auth_failures_per_minute=2)
    app = create_app(settings)  # lifespan deliberately not run
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://antos") as c:
        yield c
    if app.state.engine is not None:
        await app.state.engine.dispose()


async def _key(*roles: str) -> dict[str, str]:
    assert DB_URL
    engine = create_async_engine(DB_URL)
    key_id, secret_hash, token = new_api_key()
    async with async_sessionmaker(engine)() as session, session.begin():
        session.add(ApiKey(key_id=key_id, secret_hash=secret_hash, name="t", roles=list(roles),
                           nation_id="GH", created_by="test"))
    await engine.dispose()
    return {"X-API-Key": token}


async def test_serverless_app_initialises_on_first_request(serverless: httpx.AsyncClient) -> None:
    assert (await serverless.get("/readyz")).json()["status"] == "ready"
    h = await _key("sector_lead")
    assert (await serverless.get("/v1/escalations", headers=h)).status_code == 200


async def test_lockout_is_per_forwarded_client(serverless: httpx.AsyncClient) -> None:
    good = await _key("sector_lead")
    bad = {"X-API-Key": "antos_x.guess"}
    for _ in range(2):
        r = await serverless.get("/v1/escalations", headers={**bad, "X-Forwarded-For": "203.0.113.9"})
        assert r.status_code == 401
    locked = await serverless.get("/v1/escalations", headers={**good, "X-Forwarded-For": "203.0.113.9"})
    assert locked.status_code == 429
    other = await serverless.get("/v1/escalations", headers={**good, "X-Forwarded-For": "198.51.100.4"})
    assert other.status_code == 200


async def test_daily_job_requires_the_scheduler_secret(serverless: httpx.AsyncClient) -> None:
    assert (await serverless.get("/v1/ops/daily")).status_code == 401
    assert (await serverless.get("/v1/ops/daily", headers={"Authorization": "Bearer nope"})).status_code == 401
    ok = await serverless.get("/v1/ops/daily", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200 and ok.json()["replay_ok"] is True


async def test_demo_seed_records_real_decisions(p: Platform) -> None:
    from antos_api import demo
    refs = await demo.seed(p.rt)
    assert len(refs) == 8
    report = await service.replay_all(p.rt)
    assert report.ok and report.total == 8
    queue = (await p.client.get("/v1/escalations", headers=await p.headers("regulator"))).json()
    assert queue and all(e["created_by"] == "system:demo-seed" for e in queue)


async def test_self_setup_migrates_seeds_and_creates_the_demo_key() -> None:
    """A brand-new, empty database: the service migrates it, records the sample
    decisions and the demo key, and a second start changes nothing."""
    assert DB_URL
    cfg = Config(str(ROOT / "services" / "api" / "alembic.ini"))
    cfg.attributes["database_url"] = DB_URL
    await asyncio.to_thread(command.downgrade, cfg, "base")  # the CLI path runs its own loop
    key_id, secret_hash, token = new_api_key()
    settings = Settings(database_url=DB_URL, profile_dir=PROFILE_DIR, serverless=True,
                        auto_migrate=True, demo_seed=True, demo_key_id=key_id,
                        demo_key_hash=secret_hash)
    for _ in range(2):
        app = create_app(settings)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            assert (await c.get("/readyz")).json()["status"] == "ready"
            me = (await c.get("/v1/me", headers={"X-API-Key": token})).json()
            assert "administrator" in me["roles"]
            decisions = (await c.get("/v1/decisions?limit=50", headers={"X-API-Key": token})).json()
            assert len(decisions) == 8
            assert (await c.get("/v1/audit/verify", headers={"X-API-Key": token})).json()["ok"]
        await app.state.engine.dispose()
