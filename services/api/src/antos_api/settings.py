"""Service settings, read from ``ANTOS_*`` environment variables (or ``.env``).

Secrets are never given defaults. The Anthropic SDK reads ``ANTHROPIC_API_KEY``
itself; it is not duplicated here.
"""

from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SSL_MODES = {"require", "verify-ca", "verify-full"}


def normalize_database_url(url: str) -> str:
    """Accept the URLs hosted Postgres providers hand out (``postgres://…?sslmode=
    require&channel_binding=require``) and turn them into the asyncpg form
    SQLAlchemy needs (``postgresql+asyncpg://…?ssl=require``)."""
    parts = urlsplit(url)
    if parts.scheme not in ("postgres", "postgresql", "postgresql+asyncpg"):
        return url
    query = parse_qsl(parts.query, keep_blank_values=True)
    sslmode = dict(query).get("sslmode")
    kept = [(k, v) for k, v in query if k not in ("sslmode", "channel_binding")]
    if sslmode in _SSL_MODES and not any(k == "ssl" for k, _ in kept):
        kept.append(("ssl", "require"))
    return urlunsplit(("postgresql+asyncpg", parts.netloc, parts.path, urlencode(kept),
                       parts.fragment))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANTOS_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://antos@localhost:5432/antos"
    profile_dir: Path = Path("profiles/africa")

    # Serverless hosting (Vercel): no connection pool kept between requests, no
    # background worker (overdue reviews are swept as the app is used, and a
    # daily scheduled call seals records), and client addresses come from
    # the proxy's X-Forwarded-For header.
    serverless: bool = False
    trust_forwarded_for: bool = False
    # Shared secret for scheduled calls to /v1/ops/daily (Vercel sets CRON_SECRET).
    cron_secret: SecretStr | None = None
    # Apply database migrations at start-up (hosts where no one can run Alembic).
    auto_migrate: bool = False
    # Demonstration node: record the sample decisions when the database is empty,
    # and ensure one access key exists. Only the key's id and SHA-256 hash are
    # configured; the key itself is never stored anywhere.
    demo_seed: bool = False
    demo_key_id: str | None = None
    demo_key_hash: SecretStr | None = None
    demo_key_roles: list[str] = ["analyst", "operator", "sector_lead", "regulator", "administrator"]

    # Human identity: OIDC (Keycloak). When unset, only API keys are accepted.
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_roles_claim: str = "realm_access.roles"
    oidc_nation_claim: str = "nation_id"

    # Step 14 model gateway. "none" means the deterministic rule-based recommender.
    cloud_provider: Literal["none", "anthropic"] = "none"
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    # Sovereign (on-prem) model behind an OpenAI-compatible API, e.g. vLLM or Ollama.
    sovereign_base_url: str | None = None
    sovereign_model: str | None = None
    sovereign_api_key: SecretStr | None = None
    model_timeout_seconds: float = 60.0
    model_max_tokens: int = 8000

    redis_url: str = "redis://localhost:6379"

    # Rate limits per caller, per minute. "memory" suits one API process;
    # use "redis" when running several so they share counters.
    rate_limit_backend: Literal["memory", "redis", "off"] = "memory"
    rate_limit_per_minute: int = 600
    # /v1/decisions/resolve may call a paid model, so it has its own lower limit.
    rate_limit_decisions_per_minute: int = 60
    # Failed authentications per client address, against API-key guessing.
    rate_limit_auth_failures_per_minute: int = 20

    # Notifications (escalation opened / SLA breached), sent by the worker
    # from the outbox. Payloads are signed with HMAC-SHA256 when a secret is set.
    notify_webhook_url: str | None = None
    notify_webhook_secret: SecretStr | None = None

    # Signed audit anchors. node_id names this deployment in every anchor.
    node_id: str = "gh-pilot-1"
    anchor_private_key_path: Path | None = None
    # The key itself, for hosts without a file system for secrets (Vercel).
    anchor_private_key_pem: SecretStr | None = None
    # Extra trusted public keys (PEM files), e.g. after a key rotation.
    anchor_public_key_paths: list[Path] = []

    @field_validator("database_url")
    @classmethod
    def _asyncpg_url(cls, url: str) -> str:
        return normalize_database_url(url)

    @property
    def roles_path(self) -> Path:
        return self.profile_dir / "roles.yaml"
