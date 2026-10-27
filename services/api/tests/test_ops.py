"""Unit tests for operational pieces that need no database."""

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from antos_api.notify import WebhookNotifier
from antos_api.ratelimit import MemoryRateLimiter

pytestmark = pytest.mark.anyio
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_memory_limiter_resets_each_window() -> None:
    now = [0.0]
    limiter = MemoryRateLimiter(clock=lambda: now[0])
    assert [await limiter.hit("k", 2) for _ in range(3)][:2] == [None, None]
    assert await limiter.exceeded("k", 2) is not None
    now[0] = 61.0
    assert await limiter.hit("k", 2) is None


async def test_webhook_is_signed_with_hmac() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"], seen["headers"] = request.content, request.headers
        return httpx.Response(204)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    hook = WebhookNotifier("https://sms-bridge.example/hook", "s3cret", http=http)
    await hook.send("escalation.opened", "ESC-1", {"assigned_role": "sector_lead"})
    expected = hmac.new(b"s3cret", seen["body"], hashlib.sha256).hexdigest()
    assert seen["headers"]["X-Antos-Signature"] == f"sha256={expected}"
    assert json.loads(seen["body"])["event"] == "escalation.opened"


async def test_webhook_failure_raises_for_retry() -> None:
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(httpx.HTTPStatusError):
        await WebhookNotifier("https://x.example", None, http=http).send("e", "r", {})


def test_keycloak_realm_matches_roles_yaml() -> None:
    realm = json.loads((ROOT / "deploy" / "keycloak" / "antos-realm.json")
                       .read_text(encoding="utf-8"))
    roles = yaml.safe_load((ROOT / "profiles" / "africa" / "roles.yaml")
                           .read_text(encoding="utf-8"))["roles"]
    assert {r["name"] for r in realm["roles"]["realm"]} == set(roles)
    mappers = {m["protocolMapper"]: m["config"]
               for s in realm["clientScopes"] for m in s["protocolMappers"]}
    assert mappers["oidc-audience-mapper"]["included.client.audience"] == "antos-api"
    assert mappers["oidc-usermodel-attribute-mapper"]["claim.name"] == "nation_id"
    web = next(c for c in realm["clients"] if c["clientId"] == "antos-web")
    assert web["publicClient"] and web["attributes"]["pkce.code.challenge.method"] == "S256"


# ── Hosting ──────────────────────────────────────────────────


@pytest.mark.parametrize(("given", "expected"), [
    ("postgresql://u:p@ep-x.neon.tech/db?sslmode=require&channel_binding=require",
     "postgresql+asyncpg://u:p@ep-x.neon.tech/db?ssl=require"),
    ("postgres://u:p@host:5432/db", "postgresql+asyncpg://u:p@host:5432/db"),
    ("postgresql+asyncpg://antos@localhost:5432/antos", "postgresql+asyncpg://antos@localhost:5432/antos"),
    ("postgresql://u@h/db?sslmode=disable&application_name=x", "postgresql+asyncpg://u@h/db?application_name=x"),
])
def test_hosted_database_urls_are_normalised(given: str, expected: str) -> None:
    from antos_api.settings import Settings, normalize_database_url
    assert normalize_database_url(given) == expected
    assert Settings(database_url=given).database_url == expected


def test_anchor_key_can_come_from_an_environment_variable() -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from antos_api.app import build_runtime
    from antos_api.settings import Settings

    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    rt = build_runtime(Settings(anchor_private_key_pem=pem, profile_dir=ROOT / "profiles" / "africa"),
                       sessions=None)  # type: ignore[arg-type]
    assert rt.anchor_signer is not None and len(rt.anchor_keys) == 1


async def test_service_starts_and_answers_health_checks_without_a_database() -> None:
    from antos_api.app import create_app
    from antos_api.settings import Settings

    app = create_app(Settings(database_url="postgresql+asyncpg://nobody@127.0.0.1:9/none",
                              profile_dir=ROOT / "profiles" / "africa"))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            assert (await client.get("/healthz")).status_code == 200
            assert (await client.get("/readyz")).status_code == 500
