"""Background worker (arq on Redis).

    uv run arq antos_api.worker.WorkerSettings

Jobs: escalation SLA sweep (every minute), notification delivery (every 30 s),
signed audit anchor (daily 00:05 UTC) and a full replay check (daily 00:20 UTC).
"""

import logging
from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from antos_api import anchor, notify, service
from antos_api.app import build_notifier, build_runtime
from antos_api.settings import Settings

log = logging.getLogger("antos.worker")
settings = Settings()


async def startup(ctx: dict[str, Any]) -> None:
    ctx["engine"] = create_async_engine(settings.database_url, pool_pre_ping=True)
    ctx["runtime"] = build_runtime(settings,
                                   async_sessionmaker(ctx["engine"], expire_on_commit=False))
    ctx["notifier"] = build_notifier(settings)


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["engine"].dispose()


async def sweep_sla(ctx: dict[str, Any]) -> list[str]:
    return await service.sweep_sla(ctx["runtime"])


async def deliver_notifications(ctx: dict[str, Any]) -> dict[str, int]:
    rt: service.Runtime = ctx["runtime"]
    report = await notify.deliver_pending(rt.sessions, ctx["notifier"], rt.clock())
    return report.model_dump()


async def anchor_audit(ctx: dict[str, Any]) -> str | None:
    rt: service.Runtime = ctx["runtime"]
    if rt.anchor_signer is None:
        log.warning("no anchor key configured (ANTOS_ANCHOR_PRIVATE_KEY_PATH); skipping")
        return None
    async with rt.sessions.begin() as session:
        row = await anchor.create_anchor(session, rt.anchor_signer, rt.node_id, rt.clock())
    return row.anchor_id if row else None


async def replay_check(ctx: dict[str, Any]) -> dict[str, Any]:
    report = await service.replay_all(ctx["runtime"], recorded_by="system:replay_check")
    if not report.ok:
        log.error("replay check failed: %s", report.model_dump())
    return report.model_dump()


class WorkerSettings:
    functions: ClassVar = [sweep_sla, deliver_notifications, anchor_audit, replay_check]
    cron_jobs: ClassVar = [
        cron(sweep_sla, second=0, run_at_startup=True),
        cron(deliver_notifications, second={0, 30}),
        cron(anchor_audit, hour=0, minute=5, second=0),
        cron(replay_check, hour=0, minute=20, second=0),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
