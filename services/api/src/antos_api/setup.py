"""Self-setup for hosts where no one can run commands against the database
(serverless): apply migrations, then optionally prepare a demonstration node.

Both steps take a Postgres advisory lock, so concurrent cold starts of several
instances do the work once.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from antos_api import audit, demo, service
from antos_api.settings import Settings
from antos_api.tables import ApiKey, DecisionRow

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
MIGRATE_LOCK = 726287650002
DEMO_LOCK = 726287650003


def _upgrade(connection: Connection) -> None:
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["connection"] = connection
    command.upgrade(cfg, "head")


async def migrate(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(f"select pg_advisory_xact_lock({MIGRATE_LOCK})"))
        await conn.run_sync(_upgrade)


async def prepare_demo(engine: AsyncEngine, rt: service.Runtime, settings: Settings) -> None:
    async with engine.connect() as lock:
        got = await lock.scalar(text(f"select pg_try_advisory_lock({DEMO_LOCK})"))
        if not got:
            return  # another instance is doing it
        try:
            if settings.demo_key_id and settings.demo_key_hash:
                async with rt.sessions.begin() as session:
                    if await session.get(ApiKey, settings.demo_key_id) is None:
                        session.add(ApiKey(key_id=settings.demo_key_id,
                                           secret_hash=settings.demo_key_hash.get_secret_value(),
                                           name="Demo access", roles=settings.demo_key_roles,
                                           nation_id="GH", created_by="system:demo-setup"))
                        await session.flush()
                        await audit.append(session, "api_key.created", settings.demo_key_id,
                                           "system:demo-setup",
                                           {"key_id": settings.demo_key_id, "name": "Demo access",
                                            "roles": settings.demo_key_roles, "nation_id": "GH"})
            async with rt.sessions() as session:
                decisions = await session.scalar(select(func.count()).select_from(DecisionRow))
            if not decisions:
                await demo.seed(rt)
        finally:
            await lock.execute(text(f"select pg_advisory_unlock({DEMO_LOCK})"))
