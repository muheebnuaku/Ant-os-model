"""Authentication and role-based access.

A caller's roles come from a verified OIDC token (Keycloak) or from a stored
API key, never from a request header. Permissions come from ``roles.yaml``.
"""

import hashlib
import hmac
import secrets
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import jwt
import yaml
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from antos_api.tables import ApiKey

API_KEY_PREFIX = "antos_"


class AuthError(Exception):
    pass


class Principal(BaseModel):
    model_config = ConfigDict(frozen=True)

    subject: str
    roles: frozenset[str]
    nation_id: str | None = None
    method: Literal["oidc", "api_key"]


class Rbac:
    def __init__(self, role_permissions: Mapping[str, frozenset[str]]) -> None:
        self.role_permissions = dict(role_permissions)

    @classmethod
    def load(cls, path: Path) -> "Rbac":
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls({name: frozenset(spec["permissions"]) for name, spec in doc["roles"].items()})

    def permissions(self, principal: Principal) -> frozenset[str]:
        perms: set[str] = set()
        for role in principal.roles:
            perms |= self.role_permissions.get(role, frozenset())
        return frozenset(perms)

    def allows(self, principal: Principal, *any_of: str) -> bool:
        return bool(self.permissions(principal) & set(any_of))

    def known_roles(self, roles: list[str]) -> list[str]:
        unknown = sorted(set(roles) - set(self.role_permissions))
        if unknown:
            raise ValueError(f"unknown roles: {unknown}")
        return sorted(set(roles))


# ── API keys ─────────────────────────────────────────────────


def _hash_secret(secret: str) -> str:
    # Secrets are 256-bit random values, so a fast hash is sufficient.
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def new_api_key() -> tuple[str, str, str]:
    """Returns (key_id, secret_hash, token). Only the token is shown to the user."""
    key_id = secrets.token_hex(8)
    secret = secrets.token_urlsafe(32)
    return key_id, _hash_secret(secret), f"{API_KEY_PREFIX}{key_id}.{secret}"


async def principal_from_api_key(session: AsyncSession, token: str) -> Principal:
    body = token.removeprefix(API_KEY_PREFIX)
    key_id, _, secret = body.partition(".")
    row = await session.get(ApiKey, key_id) if key_id and secret else None
    if (row is None or row.revoked_at is not None
            or not hmac.compare_digest(row.secret_hash, _hash_secret(secret))):
        raise AuthError("invalid API key")
    return Principal(subject=f"api_key:{row.key_id}:{row.name}", roles=frozenset(row.roles),
                     nation_id=row.nation_id, method="api_key")


# ── OIDC ─────────────────────────────────────────────────────


def _claim(claims: Mapping[str, Any], path: str) -> Any:
    value: Any = claims
    for part in path.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


class OidcVerifier:
    """Verifies bearer JWTs from the identity provider. Pass ``jwks_url`` in
    production; ``key`` (a PEM public key) is for tests and offline installs."""

    ALGORITHMS = ("RS256", "PS256", "ES256")

    def __init__(self, *, issuer: str, audience: str, jwks_url: str | None = None,
                 key: Any = None, roles_claim: str = "realm_access.roles",
                 nation_claim: str = "nation_id") -> None:
        if (jwks_url is None) == (key is None):
            raise ValueError("give exactly one of jwks_url or key")
        self.issuer, self.audience = issuer, audience
        self.roles_claim, self.nation_claim = roles_claim, nation_claim
        self._key = key
        self._jwks = jwt.PyJWKClient(jwks_url, cache_keys=True) if jwks_url else None

    def verify(self, token: str) -> Principal:
        try:
            key = (self._key if self._jwks is None
                   else self._jwks.get_signing_key_from_jwt(token).key)
            claims = jwt.decode(token, key, algorithms=list(self.ALGORITHMS),
                                audience=self.audience, issuer=self.issuer,
                                options={"require": ["exp", "iat", "sub"]})
        except jwt.PyJWTError as exc:
            raise AuthError(f"invalid token: {exc}") from None
        roles = _claim(claims, self.roles_claim) or []
        if not isinstance(roles, list):
            raise AuthError("roles claim must be a list")
        nation = _claim(claims, self.nation_claim)
        return Principal(subject=f"oidc:{claims['sub']}",
                         roles=frozenset(str(r) for r in roles),
                         nation_id=str(nation) if nation else None, method="oidc")
