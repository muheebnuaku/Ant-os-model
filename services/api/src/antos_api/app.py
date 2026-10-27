"""FastAPI application.

The API schema's middleware chain maps onto this service as follows:
authentication + role resolution (``principal``/``require``) → nation binding
(``check_nation``) → sector pack activation and request validation (active
config + Pydantic) → guardrail precheck, 24HAE gate, execution, postcheck,
inclusion, ecology and local fit (the 19-step loop in ``antos_core``) → audit
log write (same transaction) → response.
"""

import asyncio
import hmac
import logging
import math
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any, Literal

import anyio
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from antos_api import anchor, audit, notify, service, setup, views
from antos_api.auth import (
    API_KEY_PREFIX,
    AuthError,
    OidcVerifier,
    Principal,
    Rbac,
    new_api_key,
    principal_from_api_key,
)
from antos_api.gateway import AnthropicClient, ModelGateway, OpenAICompatibleClient
from antos_api.notify import LogNotifier, Notifier, WebhookNotifier
from antos_api.ratelimit import (
    MemoryRateLimiter,
    NoRateLimit,
    RateLimited,
    RateLimiter,
    RedisRateLimiter,
)
from antos_api.service import Runtime
from antos_api.settings import Settings
from antos_api.tables import AnchorRow, ApiKey
from antos_core.config import UnknownSectorError
from antos_core.contracts import EscalationPriority, SignalInput

log = logging.getLogger("antos.api")

# Permissions (from roles.yaml) accepted by each operation: any one suffices.
INGEST = ("submit_signals", "submit_market_signals", "submit_research_signals")
RESOLVE = ("run_analysis", "trigger_allowed_prompts", "approve_sector_actions")
READ_DECISION = ("inspect_trails", "view_assigned_outputs", "inspect_sector_audits",
                 "inspect_cross_sector_trails", "audit_mode")
AUDIT = ("audit_mode", "audit_review", "inspect_sector_audits")
CREATE_ESCALATION = ("run_analysis", "review_escalations", "approve_sector_actions")
CONFIG_READ = ("config_management", "policy_threshold_control", "audit_review")
CONFIG_WRITE = ("policy_threshold_control", "weight_recalibration")  # sovereign_admin only
MANAGE_KEYS = ("role_assignment",)
ANCHOR = ("audit_review", "audit_mode")
# The API schema allows sector_lead and sovereign_admin; regulators and analysts
# also need the national picture.
SITUATION = ("review_escalations", "strategic_mode_control", "audit_mode", "run_analysis")
SIGNALS = (*INGEST, *READ_DECISION)


def build_gateway(settings: Settings) -> ModelGateway:
    cloud = sovereign = None
    if settings.cloud_provider == "anthropic":
        cloud = AnthropicClient(model=settings.anthropic_model, effort=settings.anthropic_effort,
                                max_tokens=settings.model_max_tokens,
                                timeout=settings.model_timeout_seconds)
    if settings.sovereign_base_url and settings.sovereign_model:
        key = settings.sovereign_api_key
        sovereign = OpenAICompatibleClient(
            base_url=settings.sovereign_base_url, model=settings.sovereign_model,
            max_tokens=settings.model_max_tokens, timeout=settings.model_timeout_seconds,
            api_key=key.get_secret_value() if key else None)
    return ModelGateway(cloud=cloud, sovereign=sovereign)


def build_oidc(settings: Settings) -> OidcVerifier | None:
    if not (settings.oidc_issuer and settings.oidc_audience and settings.oidc_jwks_url):
        return None
    return OidcVerifier(issuer=settings.oidc_issuer, audience=settings.oidc_audience,
                        jwks_url=settings.oidc_jwks_url, roles_claim=settings.oidc_roles_claim,
                        nation_claim=settings.oidc_nation_claim)


def build_runtime(settings: Settings, sessions: async_sessionmaker[AsyncSession]) -> Runtime:
    signer = None
    if settings.anchor_private_key_pem:
        signer = anchor.load_private_key_pem(
            settings.anchor_private_key_pem.get_secret_value().encode(),
            "ANTOS_ANCHOR_PRIVATE_KEY_PEM")
    elif settings.anchor_private_key_path:
        signer = anchor.load_private_key(settings.anchor_private_key_path)
    public = [signer.public_key()] if signer else []
    public += [anchor.load_public_key(p) for p in settings.anchor_public_key_paths]
    return Runtime(sessions=sessions, rbac=Rbac.load(settings.roles_path),
                   gateway=build_gateway(settings), node_id=settings.node_id,
                   anchor_signer=signer, anchor_keys={anchor.key_id(k): k for k in public})


def build_notifier(settings: Settings) -> Notifier:
    if not settings.notify_webhook_url:
        return LogNotifier()
    secret = settings.notify_webhook_secret
    return WebhookNotifier(settings.notify_webhook_url,
                           secret.get_secret_value() if secret else None)


def build_limiter(settings: Settings) -> RateLimiter:
    if settings.rate_limit_backend == "off":
        return NoRateLimit()
    if settings.rate_limit_backend == "redis":
        return RedisRateLimiter(Redis.from_url(settings.redis_url))
    return MemoryRateLimiter()


def create_app(settings: Settings | None = None, *, runtime: Runtime | None = None,
               oidc: OidcVerifier | None = None, limiter: RateLimiter | None = None) -> FastAPI:
    settings = settings or Settings()

    async def init(app: FastAPI) -> None:
        app.state.settings = settings
        app.state.limiter = limiter or build_limiter(settings)
        app.state.engine = None
        app.state.last_sweep = 0.0
        if runtime is None:
            # Serverless instances are frozen between requests, so keep no pool.
            engine = (create_async_engine(settings.database_url, poolclass=NullPool)
                      if settings.serverless
                      else create_async_engine(settings.database_url, pool_pre_ping=True))
            app.state.engine = engine
            app.state.runtime = build_runtime(
                settings, async_sessionmaker(engine, expire_on_commit=False))
            app.state.oidc = build_oidc(settings)
        else:
            app.state.runtime, app.state.oidc = runtime, oidc
        rt: Runtime = app.state.runtime
        if settings.auto_migrate and app.state.engine is not None:
            await setup.migrate(app.state.engine)
        async with rt.sessions.begin() as session:
            await service.bootstrap(session, rt.configs, settings.profile_dir)
        if settings.demo_seed and app.state.engine is not None:
            await setup.prepare_demo(app.state.engine, rt, settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # A database that is down at start-up must not take the whole service
        # (and its health check) down with it; requests retry initialisation.
        try:
            await ensure_ready(app)
        except Exception:
            log.exception("start-up initialisation failed; will retry on the next request")
        yield
        if getattr(app.state, "engine", None) is not None:
            await app.state.engine.dispose()

    app = FastAPI(title="ANT-OS Ω / AFRICA-OS Ω", version="0.2.0", lifespan=lifespan,
                  description="Sovereign, validation-first reasoning layer. "
                              "Creator: Dr. David King Boison.")
    # Initialised on first use as well as at start-up: serverless hosts may not
    # run the start-up event.
    app.state.ready = False
    app.state.settings = settings
    app.state.init = init
    app.state.init_lock = asyncio.Lock()
    _errors(app)
    _routes(app)
    return app


async def ensure_ready(app: FastAPI) -> None:
    if app.state.ready:
        return
    async with app.state.init_lock:
        if not app.state.ready:
            await app.state.init(app)
            app.state.ready = True


# ── Errors ───────────────────────────────────────────────────


def _errors(app: FastAPI) -> None:
    def handler(status: int) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
        async def handle(_: Request, exc: Exception) -> JSONResponse:
            return JSONResponse({"detail": str(exc).strip("'\"")}, status_code=status)
        return handle

    for exc_type, status in ((AuthError, 401), (service.Forbidden, 403), (service.NotFound, 404),
                             (UnknownSectorError, 422), (service.Conflict, 409),
                             (anchor.ChainBroken, 409), (ValueError, 422)):
        app.add_exception_handler(exc_type, handler(status))

    async def rate_limited(_: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RateLimited)
        return JSONResponse({"detail": str(exc)}, status_code=429,
                            headers={"Retry-After": str(math.ceil(exc.retry_after))})

    app.add_exception_handler(RateLimited, rate_limited)


# ── Auth dependencies ────────────────────────────────────────


async def get_runtime(request: Request) -> Runtime:
    await ensure_ready(request.app)
    rt: Runtime = request.app.state.runtime
    return rt


def client_address(request: Request) -> str:
    """The caller's address; behind a trusted proxy, the first X-Forwarded-For hop."""
    settings: Settings = request.app.state.settings
    forwarded = request.headers.get("x-forwarded-for")
    if settings.trust_forwarded_for and forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _authenticate(request: Request) -> Principal:
    rt: Runtime = request.app.state.runtime
    auth = request.headers.get("authorization", "")
    token = request.headers.get("x-api-key") or (
        auth[7:].strip() if auth.lower().startswith("bearer ") else None)
    if not token:
        raise AuthError("missing credentials")
    if token.startswith(API_KEY_PREFIX):
        async with rt.sessions() as session:
            return await principal_from_api_key(session, token)
    verifier: OidcVerifier | None = request.app.state.oidc
    if verifier is None:
        raise AuthError("bearer tokens are not enabled on this node")
    return await anyio.to_thread.run_sync(verifier.verify, token)


async def limit(request: Request, key: str, per_minute: int, what: str) -> None:
    limiter: RateLimiter = request.app.state.limiter
    wait = await limiter.hit(key, per_minute)
    if wait is not None:
        raise RateLimited(wait, what)


async def principal(request: Request) -> Principal:
    await ensure_ready(request.app)
    settings: Settings = request.app.state.settings
    limiter: RateLimiter = request.app.state.limiter
    failures = f"authfail:{client_address(request)}"
    # Refuse further attempts from an address that keeps failing, before checking.
    wait = await limiter.exceeded(failures, settings.rate_limit_auth_failures_per_minute)
    if wait is not None:
        raise RateLimited(wait, "failed authentication attempts")
    try:
        who = await _authenticate(request)
    except AuthError:
        await limiter.hit(failures, settings.rate_limit_auth_failures_per_minute)
        raise
    await limit(request, f"caller:{who.subject}", settings.rate_limit_per_minute, "this caller")
    return who


def require(*any_of: str) -> Callable[..., Awaitable[Principal]]:
    async def dependency(request: Request,
                         who: Annotated[Principal, Depends(principal)]) -> Principal:
        rt: Runtime = request.app.state.runtime
        if any_of and not rt.rbac.allows(who, *any_of):
            raise HTTPException(403, f"requires one of the permissions {list(any_of)}")
        return who
    return dependency


RT = Annotated[Runtime, Depends(get_runtime)]

SWEEP_EVERY_SECONDS = 60.0


async def sweep_if_due(request: Request) -> None:
    """Serverless hosts have no background worker, so overdue reviews are marked
    as the app is used (at most once a minute per instance)."""
    await ensure_ready(request.app)
    settings: Settings = request.app.state.settings
    if not settings.serverless:
        return
    now = time.monotonic()
    if now - request.app.state.last_sweep < SWEEP_EVERY_SECONDS:
        return
    request.app.state.last_sweep = now
    await service.sweep_sla(request.app.state.runtime)


SWEPT = Depends(sweep_if_due)


# ── Request bodies ───────────────────────────────────────────


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SignalIngestBody(SignalInput):
    nation_id: str = "GH"


class BulkIngestBody(Body):
    nation_id: str = "GH"
    sector: str | None = None
    signals: list[SignalInput] = Field(min_length=1, max_length=1000)


class ReplayBody(Body):
    audit_ref: str


class EscalationBody(Body):
    objective: str = Field(min_length=1)
    sector: str
    nation_id: str = "GH"
    priority: EscalationPriority
    reason: str = Field(min_length=1)
    source_ref: str | None = None


class NoteBody(Body):
    note: str | None = None


class ConfigBody(Body):
    manifest: dict[str, Any]
    sector_packs: dict[str, Any]
    recalibration_rationale: str = Field(min_length=10)


class SituationBody(Body):
    nation_id: str = "GH"
    sectors: list[str] | None = None
    time_window_hours: int = Field(default=24, ge=1, le=24 * 31)


class ApiKeyBody(Body):
    name: str = Field(min_length=1)
    roles: list[str] = Field(min_length=1)
    nation_id: str | None = None


# ── Routes ───────────────────────────────────────────────────


def _routes(app: FastAPI) -> None:
    @app.get("/healthz", tags=["ops"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False, response_model=None)
    async def front_page(request: Request) -> RedirectResponse | dict[str, str]:
        """People who open the API address in a browser are sent to the web app."""
        settings: Settings = request.app.state.settings
        if settings.public_web_url:
            return RedirectResponse(settings.public_web_url, status_code=307)
        return {"service": "ANT-OS Ω API", "web_app": "not configured",
                "documentation": "/docs", "health": "/healthz"}

    @app.get("/v1/ops/daily", tags=["ops"])
    async def daily(request: Request, rt: RT) -> dict[str, Any]:
        """The worker's jobs, for hosts without one: called once a day by the
        scheduler with ``Authorization: Bearer <ANTOS_CRON_SECRET>``."""
        settings: Settings = request.app.state.settings
        secret = settings.cron_secret.get_secret_value() if settings.cron_secret else ""
        given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not secret or not hmac.compare_digest(given, secret):
            raise AuthError("invalid scheduler credentials")
        breached = await service.sweep_sla(rt)
        delivered = await notify.deliver_pending(rt.sessions, LogNotifier(), rt.clock())
        anchored = None
        if rt.anchor_signer is not None:
            async with rt.sessions.begin() as session:
                row = await anchor.create_anchor(session, rt.anchor_signer, rt.node_id, rt.clock())
            anchored = row.anchor_id if row else None
        replay = await service.replay_all(rt, recorded_by="system:daily_check")
        return {"breached": breached, "notifications": delivered.model_dump(),
                "anchored": anchored, "replay_ok": replay.ok}

    @app.get("/readyz", tags=["ops"])
    async def readyz(rt: RT) -> dict[str, Any]:
        async with rt.sessions() as session:
            await session.execute(text("select 1"))
            config_hash, profile = await rt.configs.active(session)
        return {"status": "ready", "config_hash": config_hash,
                "profile": profile.manifest.name, "manifest_version": profile.manifest.version,
                "model_gateway": rt.gateway.describe()}

    # Session and reference data

    @app.get("/v1/me", tags=["session"])
    async def me(rt: RT, who: Annotated[Principal, Depends(principal)]) -> dict[str, Any]:
        return {"subject": who.subject, "roles": sorted(who.roles), "nation_id": who.nation_id,
                "method": who.method, "permissions": sorted(rt.rbac.permissions(who))}

    @app.get("/v1/node", tags=["session"])
    async def node(rt: RT, _caller: Annotated[Principal, Depends(principal)]
                   ) -> views.NodeStatus:
        return await views.node_status(rt)

    @app.get("/v1/sectors", tags=["session"])
    async def sectors(rt: RT, _caller: Annotated[Principal, Depends(principal)]
                      ) -> list[dict[str, Any]]:
        async with rt.sessions() as session:
            _, profile = await rt.configs.active(session)
        return [{"sector_id": p.sector_id, "sector_name": p.sector_name,
                 "priority_24hae": p.priority_24hae, "half_life_hours": p.half_life_hours,
                 "model_route": p.model_route,
                 "signal_types": {t: s.compare_field for t, s in p.signal_types.items()}}
                for p in profile.packs.values()]

    @app.post("/v1/core/situation-room", tags=["situation room"])
    async def situation_room(body: SituationBody, rt: RT,
                             who: Annotated[Principal, Depends(require(*SITUATION))],
                             _swept: None = SWEPT) -> views.SituationRoom:
        return await views.situation_room(rt, who, nation_id=body.nation_id,
                                          sectors=body.sectors,
                                          time_window_hours=body.time_window_hours)

    # Signals

    @app.post("/v1/signals/ingest", tags=["signals"])
    async def ingest_one(body: SignalIngestBody, rt: RT,
                         who: Annotated[Principal, Depends(require(*INGEST))]) -> dict[str, Any]:
        signal = SignalInput(**body.model_dump(exclude={"nation_id"}))
        [result] = await service.ingest(rt, who, [signal], nation_id=body.nation_id,
                                        sector=body.sector)
        if not result.accepted:
            raise HTTPException(422, result.error)
        return result.model_dump()

    @app.post("/v1/signals/bulk-ingest", tags=["signals"])
    async def ingest_bulk(body: BulkIngestBody, rt: RT,
                          who: Annotated[Principal, Depends(require(*INGEST))]) -> dict[str, Any]:
        results = await service.ingest(rt, who, body.signals, nation_id=body.nation_id,
                                       sector=body.sector)
        return {"accepted_count": sum(r.accepted for r in results),
                "rejected_count": sum(not r.accepted for r in results),
                "results": [r.model_dump() for r in results]}

    # Decisions

    @app.post("/v1/decisions/resolve", tags=["decisions"])
    async def resolve(body: service.ResolveBody, rt: RT, request: Request,
                      who: Annotated[Principal, Depends(require(*RESOLVE))]
                      ) -> service.StoredDecision:
        settings: Settings = request.app.state.settings
        await limit(request, f"decide:{who.subject}", settings.rate_limit_decisions_per_minute,
                    "decisions by this caller")
        return await service.resolve(rt, who, body)

    @app.get("/v1/decisions", tags=["decisions"])
    async def list_decisions(rt: RT, who: Annotated[Principal, Depends(require(*READ_DECISION))],
                             sector: str | None = None,
                             limit: Annotated[int, Query(ge=1, le=500)] = 50,
                             before_seq: int | None = None,
                             since: datetime | None = None,
                             until: datetime | None = None) -> list[dict[str, Any]]:
        return await views.list_decisions(rt, who, sector=sector, limit=limit,
                                          before_seq=before_seq, since=since, until=until)

    @app.get("/v1/signals", tags=["signals"])
    async def list_signals(rt: RT, who: Annotated[Principal, Depends(require(*SIGNALS))],
                           sector: str | None = None, signal_type: str | None = None,
                           source: str | None = None,
                           hours: Annotated[int, Query(ge=1, le=24 * 90)] = 24,
                           limit: Annotated[int, Query(ge=1, le=1000)] = 300) -> dict[str, Any]:
        return await views.list_signals(rt, who, sector=sector, signal_type=signal_type,
                                        source=source, hours=hours, limit=limit)

    @app.get("/v1/decisions/{ref}", tags=["decisions"])
    async def get_decision(ref: str, rt: RT,
                           who: Annotated[Principal, Depends(require(*READ_DECISION))]
                           ) -> service.StoredDecision:
        return await service.get_decision(rt, who, ref)

    # Audit

    @app.get("/v1/audit/entries", tags=["audit"])
    async def audit_entries(rt: RT, _: Annotated[Principal, Depends(require(*AUDIT))],
                            limit: Annotated[int, Query(ge=1, le=200)] = 50,
                            before_seq: int | None = None,
                            event_type: str | None = None) -> list[dict[str, Any]]:
        return await views.list_audit_entries(rt, limit=limit, before_seq=before_seq,
                                              event_type=event_type)

    @app.get("/v1/audit/entries/{seq}", tags=["audit"])
    async def audit_entry(seq: int, rt: RT, _: Annotated[Principal, Depends(require(*AUDIT))]
                          ) -> dict[str, Any]:
        return await views.get_audit_entry(rt, seq)

    @app.post("/v1/audit/replay", tags=["audit"])
    async def replay(body: ReplayBody, rt: RT,
                     who: Annotated[Principal, Depends(require(*AUDIT))]) -> service.ReplayReport:
        return await service.replay(rt, who, body.audit_ref)

    @app.get("/v1/audit/verify", tags=["audit"])
    async def verify(rt: RT, _: Annotated[Principal, Depends(require(*AUDIT))]
                     ) -> dict[str, Any]:
        async with rt.sessions() as session:
            chain = await audit.verify_chain(session)
            anchors = await anchor.verify_anchors(session, rt.anchor_keys)
        return {"ok": chain.ok and anchors.ok, "chain": chain.model_dump(),
                "anchors": anchors.model_dump()}

    @app.post("/v1/audit/replay-all", tags=["audit"])
    async def replay_all(rt: RT, who: Annotated[Principal, Depends(require(*AUDIT))]
                         ) -> dict[str, Any]:
        report = await service.replay_all(rt, recorded_by=who.subject)
        return {"ok": report.ok, **report.model_dump()}

    @app.get("/v1/audit/anchors", tags=["audit"])
    async def list_anchors(rt: RT, _: Annotated[Principal, Depends(require(*AUDIT))]
                           ) -> list[dict[str, Any]]:
        async with rt.sessions() as session:
            rows = (await session.scalars(select(AnchorRow).order_by(AnchorRow.up_to_seq))).all()
        return [{"anchor_id": r.anchor_id, "up_to_seq": r.up_to_seq, "head_hash": r.head_hash,
                 "anchored_at": r.anchored_at, "key_id": r.key_id, "statement": r.statement,
                 "signature": r.signature} for r in rows]

    @app.post("/v1/audit/anchor", tags=["audit"])
    async def create_anchor(rt: RT, _: Annotated[Principal, Depends(require(*ANCHOR))]
                            ) -> dict[str, Any]:
        if rt.anchor_signer is None:
            raise service.Conflict("no anchor signing key is configured on this node")
        async with rt.sessions.begin() as session:
            row = await anchor.create_anchor(session, rt.anchor_signer, rt.node_id, rt.clock())
        return {"anchored": row is not None, "anchor_id": row.anchor_id if row else None}

    # Escalations

    @app.post("/v1/escalations/create", tags=["escalations"])
    async def create_escalation(body: EscalationBody, rt: RT,
                                who: Annotated[Principal, Depends(require(*CREATE_ESCALATION))]
                                ) -> dict[str, Any]:
        return await service.create_escalation(rt, who, **body.model_dump())

    @app.get("/v1/escalations", tags=["escalations"])
    async def list_escalations(rt: RT, who: Annotated[Principal, Depends(principal)],
                               status: Literal["open", "acknowledged", "resolved"] | None = None,
                               _swept: None = SWEPT) -> list[dict[str, Any]]:
        return await service.list_escalations(rt, who, status)

    @app.post("/v1/escalations/{escalation_id}/acknowledge", tags=["escalations"])
    async def acknowledge(escalation_id: str, rt: RT,
                          who: Annotated[Principal, Depends(principal)]) -> dict[str, Any]:
        return await service.transition(rt, who, escalation_id, "acknowledged", None)

    @app.post("/v1/escalations/{escalation_id}/resolve", tags=["escalations"])
    async def resolve_escalation(escalation_id: str, body: NoteBody, rt: RT,
                                 who: Annotated[Principal, Depends(principal)]) -> dict[str, Any]:
        return await service.transition(rt, who, escalation_id, "resolved", body.note)

    # Admin

    @app.get("/v1/admin/config", tags=["admin"])
    async def get_config(rt: RT, _: Annotated[Principal, Depends(require(*CONFIG_READ))]
                         ) -> dict[str, Any]:
        async with rt.sessions() as session:
            config_hash, profile = await rt.configs.active(session)
        return {"config_hash": config_hash, "profile": profile.model_dump(mode="json")}

    @app.put("/v1/admin/config", tags=["admin"])
    async def put_config(body: ConfigBody, rt: RT,
                         who: Annotated[Principal, Depends(require(*CONFIG_WRITE))]
                         ) -> dict[str, Any]:
        async with rt.sessions.begin() as session:
            config_hash = await rt.configs.activate(
                session, manifest_doc=body.manifest, packs_doc=body.sector_packs,
                rationale=body.recalibration_rationale, actor=who.subject)
        return {"updated": True, "config_ref": config_hash}

    @app.get("/v1/admin/api-keys", tags=["admin"])
    async def list_api_keys(rt: RT, who: Annotated[Principal, Depends(require(*MANAGE_KEYS))]
                            ) -> list[dict[str, Any]]:
        async with rt.sessions() as session:
            query = select(ApiKey).order_by(ApiKey.created_at.desc())
            if who.nation_id:
                query = query.where(ApiKey.nation_id == who.nation_id)
            rows = (await session.scalars(query)).all()
        return [{"key_id": k.key_id, "name": k.name, "roles": k.roles, "nation_id": k.nation_id,
                 "created_by": k.created_by, "created_at": k.created_at,
                 "revoked_at": k.revoked_at} for k in rows]

    @app.post("/v1/admin/api-keys/{key_id}/revoke", tags=["admin"])
    async def revoke_api_key(key_id: str, rt: RT,
                             who: Annotated[Principal, Depends(require(*MANAGE_KEYS))]
                             ) -> dict[str, Any]:
        async with rt.sessions.begin() as session:
            key = await session.get(ApiKey, key_id, with_for_update=True)
            if key is None or (who.nation_id and key.nation_id != who.nation_id):
                raise service.NotFound(f"key {key_id} not found")
            if key.revoked_at is not None:
                raise service.Conflict("key is already revoked")
            key.revoked_at = rt.clock()
            await session.flush()
            await audit.append(session, "api_key.revoked", key_id, who.subject,
                               {"key_id": key_id, "name": key.name})
        return {"revoked": True, "key_id": key_id}

    @app.post("/v1/admin/api-keys", tags=["admin"])
    async def create_api_key(body: ApiKeyBody, rt: RT,
                             who: Annotated[Principal, Depends(require(*MANAGE_KEYS))]
                             ) -> dict[str, Any]:
        roles = rt.rbac.known_roles(body.roles)
        if who.nation_id and body.nation_id != who.nation_id:
            raise service.Forbidden("keys must be bound to the caller's nation")
        key_id, secret_hash, token = new_api_key()
        async with rt.sessions.begin() as session:
            session.add(ApiKey(key_id=key_id, secret_hash=secret_hash, name=body.name,
                               roles=roles, nation_id=body.nation_id, created_by=who.subject))
            await session.flush()
            await audit.append(session, "api_key.created", key_id, who.subject,
                               {"key_id": key_id, "name": body.name, "roles": roles,
                                "nation_id": body.nation_id})
        return {"key_id": key_id, "token": token, "roles": roles,
                "note": "Store this token now. It cannot be shown again."}
