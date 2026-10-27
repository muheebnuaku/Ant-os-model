"""Unit tests that need no database: model gateway routing and adapters, auth."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from antos_api.auth import AuthError, OidcVerifier, Principal, Rbac
from antos_api.gateway import (
    AnthropicClient,
    GatewayRecommender,
    ModelError,
    ModelGateway,
    ModelOutput,
    OpenAICompatibleClient,
)
from antos_core import load_profile
from antos_core.contracts import Action

pytestmark = pytest.mark.anyio

ROOT = Path(__file__).resolve().parents[3]
PROFILE = load_profile(ROOT / "profiles" / "africa")
OUTPUT = ModelOutput(action=Action.DEFER, primary_recommendation="Verify first.",
                     ubuntu_note="u", hae_note="h", escalation_suggested=False,
                     cited_signal_ids=["SIG-1"])


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class StubClient:
    def __init__(self, provider: str, model: str = "m") -> None:
        self.provider, self.model = provider, model

    async def complete(self, system: str, user: str) -> tuple[ModelOutput, str, str | None]:
        return OUTPUT, OUTPUT.model_dump_json(), "end_turn"


# ── Routing ──────────────────────────────────────────────────


def test_sovereign_pack_never_uses_cloud() -> None:
    gw = ModelGateway(cloud=StubClient("anthropic"))
    assert PROFILE.pack("health").model_route == "sovereign"
    assert gw.client_for(PROFILE.pack("health")) is None  # rules, not cloud
    assert gw.client_for(PROFILE.pack("agriculture")) is gw.cloud


def test_sovereign_pack_uses_on_prem_model_when_configured() -> None:
    gw = ModelGateway(cloud=StubClient("anthropic"), sovereign=StubClient("sovereign"))
    assert gw.client_for(PROFILE.pack("finance")) is gw.sovereign


def test_default_pack_falls_back_to_sovereign_then_rules() -> None:
    assert ModelGateway(sovereign=StubClient("sovereign")).client_for(
        PROFILE.pack("ports")) is not None
    assert ModelGateway().recommender_for(PROFILE.pack("ports")) is None


def test_rules_only_pack_never_calls_a_model() -> None:
    pack = PROFILE.pack("ports").model_copy(update={"model_route": "rules_only"})
    assert ModelGateway(cloud=StubClient("anthropic")).client_for(pack) is None


# ── Adapters ─────────────────────────────────────────────────


def _anthropic(
    stop_reason: str, parsed: ModelOutput | None
) -> tuple[AnthropicClient, dict[str, Any]]:
    seen: dict[str, Any] = {}

    async def parse(**kwargs: Any) -> Any:
        seen.update(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=parsed.model_dump_json() if parsed else "")],
            stop_reason=stop_reason, stop_details=None, parsed_output=parsed)

    fake = SimpleNamespace(messages=SimpleNamespace(parse=parse))
    return AnthropicClient(model="claude-opus-5-5", effort="medium", max_tokens=8000,
                           timeout=30, client=fake), seen  # type: ignore[arg-type]


async def test_anthropic_adapter_requests_structured_output() -> None:
    client, seen = _anthropic("end_turn", OUTPUT)
    output, _, stop = await client.complete("sys", "user")
    assert output == OUTPUT and stop == "end_turn"
    assert seen["model"] == "claude-opus-5-5"
    assert seen["output_format"] is ModelOutput
    assert seen["output_config"] == {"effort": "medium"}


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
async def test_anthropic_adapter_rejects_refusal_and_truncation(stop: str) -> None:
    client, _ = _anthropic(stop, OUTPUT)
    with pytest.raises(ModelError):
        await client.complete("sys", "user")


async def test_openai_compatible_adapter_uses_json_schema() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{
            "message": {"content": OUTPUT.model_dump_json()}, "finish_reason": "stop"}]})

    http = httpx.AsyncClient(base_url="http://vllm.local/v1",
                             transport=httpx.MockTransport(handler))
    client = OpenAICompatibleClient(base_url="unused", model="local", max_tokens=100,
                                    timeout=5, http=http)
    output, _, _ = await client.complete("sys", "user")
    assert output == OUTPUT
    assert seen["response_format"]["type"] == "json_schema"
    assert "validation_state" not in json.dumps(seen["response_format"])  # no state, no scores


async def test_recommender_records_the_exact_exchange() -> None:
    from antos_core.loop import DecisionRequest, prepare

    now = datetime(2026, 10, 25, 12, tzinfo=UTC)
    req = DecisionRequest(objective="o", sector="ports", signals=[{
        "signal_type": "berth_occupancy", "source_id": "gpha",
        "payload": {"occupancy_rate": 0.5}, "observed_at": now}])
    ctx = prepare(req, PROFILE, now).recommendation_context()
    rec = GatewayRecommender(StubClient("anthropic", "claude-opus-5-5"))
    result = await rec.recommend(ctx)
    assert result.produced_by == "llm:anthropic:claude-opus-5-5"
    assert rec.exchange is not None and rec.exchange.response_text
    assert "berth_occupancy" in rec.exchange.user


# ── Auth ─────────────────────────────────────────────────────


RBAC = Rbac.load(ROOT / "profiles" / "africa" / "roles.yaml")


def test_rbac_permissions_come_from_roles() -> None:
    lead = Principal(subject="x", roles=frozenset({"sector_lead"}), method="oidc")
    assert RBAC.allows(lead, "review_escalations")
    assert not RBAC.allows(lead, "policy_threshold_control")
    with pytest.raises(ValueError):
        RBAC.known_roles(["sector_lead", "emperor"])


@pytest.fixture(scope="module")
def keypair() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _token(key: rsa.RSAPrivateKey, **overrides: Any) -> str:
    now = datetime.now(UTC)
    claims = {"sub": "ama", "iss": "https://id.gov.gh/realms/antos", "aud": "antos-api",
              "iat": now, "exp": now + timedelta(minutes=5),
              "realm_access": {"roles": ["sector_lead"]}, "nation_id": "GH", **overrides}
    return jwt.encode(claims, key, algorithm="RS256")


def _verifier(key: rsa.RSAPrivateKey) -> OidcVerifier:
    return OidcVerifier(issuer="https://id.gov.gh/realms/antos", audience="antos-api",
                        key=key.public_key())


def test_oidc_token_yields_roles_and_nation(keypair: rsa.RSAPrivateKey) -> None:
    who = _verifier(keypair).verify(_token(keypair))
    assert who.roles == {"sector_lead"} and who.nation_id == "GH" and who.subject == "oidc:ama"


@pytest.mark.parametrize("bad", [
    {"aud": "someone-else"},
    {"iss": "https://evil.example"},
    {"exp": datetime.now(UTC) - timedelta(minutes=1)},
])
def test_oidc_rejects_bad_claims(keypair: rsa.RSAPrivateKey, bad: dict[str, Any]) -> None:
    with pytest.raises(AuthError):
        _verifier(keypair).verify(_token(keypair, **bad))


def test_oidc_rejects_foreign_signature(keypair: rsa.RSAPrivateKey) -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(AuthError):
        _verifier(keypair).verify(_token(other))


def test_oidc_rejects_unsigned_token(keypair: rsa.RSAPrivateKey) -> None:
    token = jwt.encode({"sub": "x", "realm_access": {"roles": ["sovereign_admin"]}}, None,
                       algorithm="none")
    with pytest.raises(AuthError):
        _verifier(keypair).verify(token)
