# ANT-OS Ω

A sovereign, validation-first reasoning layer. **AFRICA-OS Ω** is the doctrine
profile that runs on it: 24-Hour Africa Economy Policy, Ubuntu, inclusion, and
the core-8 Ghana sector packs.

Creator: **Dr. David King Boison**. Attribution to the creator, the VPF and the
24-Hour Africa Economy Policy is a condition of every deployment.

## Layout

```
packages/antos-core/   deterministic engines + 19-step reasoning contract (no I/O)
services/api/          FastAPI service, Postgres audit store, escalations, model gateway
web/                   Next.js app: Situation Room, Escalations, Decisions, Audit
profiles/africa/       manifest, sector packs (incl. escalation rules), roles.yaml
deploy/                Dockerfile, docker compose pilot stack, .env.example
docs/DECISIONS.md      spec decisions awaiting author sign-off
docs/UI_MASTER_PROMPT.md  the interface brief every screen must follow
ANT_OS_IMPLEMENTATION_PLAN.md   architecture, stack, phased roadmap
```

Original source material (papers, manifests, reference implementation zips)
is kept at the repository root and is not modified.

## Develop

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync            # create .venv and install the workspace
uv run pytest      # tests
uv run ruff check .
uv run mypy
```

Database tests run when `ANTOS_TEST_DATABASE_URL` points at a **disposable**
PostgreSQL database (they drop and re-create the schema, and the tamper tests
need a superuser). Without it they are skipped:

```bash
ANTOS_TEST_DATABASE_URL=postgresql+asyncpg://antos@localhost:5432/antos_test uv run pytest
```

## Run the platform

```bash
export ANTOS_DATABASE_URL=postgresql+asyncpg://antos:PASSWORD@localhost:5432/antos
uv run alembic -c services/api/alembic.ini upgrade head
uv run python -m antos_api.cli create-api-key --name ops --roles administrator --nation GH
uv run uvicorn antos_api.app:create_app --factory --port 8000   # API docs at /docs
uv run arq antos_api.worker.WorkerSettings                      # SLA timers (needs Redis)
```

The web app (needs Node 24; it proxies `/api` to `ANTOS_API_URL`, default
`http://127.0.0.1:8000`):

```bash
cd web
npm install
npm run dev            # http://localhost:3000, sign in with an API key
npm run gen:api        # regenerate TypeScript types after API changes
```

Or the whole pilot stack: `docker compose -f deploy/compose.yaml up --build`
(copy `deploy/.env.example` to `deploy/.env` first).

| Endpoint | Purpose |
|---|---|
| `POST /v1/signals/ingest`, `/v1/signals/bulk-ingest` | Store signals. IDs come from content, so re-ingesting is harmless. |
| `POST /v1/decisions/resolve` | Run the 19-step loop over inline and/or stored (`signal_refs`) signals |
| `GET /v1/decisions/{audit_ref or decision_id}` | Read a recorded decision |
| `POST /v1/audit/replay` | Re-execute a decision from the audit log under the config version it ran under |
| `GET /v1/audit/verify` | Recompute the whole audit hash chain and check every signed anchor |
| `POST /v1/audit/replay-all` | Replay every recorded decision (all must match) |
| `POST /v1/audit/anchor`, `GET /v1/audit/anchors` | Sign the chain's current head (the worker does this daily) |
| `GET /v1/escalations`, `POST …/{id}/acknowledge`, `…/{id}/resolve`, `/v1/escalations/create` | Human escalation queue |
| `GET`/`PUT /v1/admin/config` | Read or activate a configuration version (PUT: `sovereign_admin`, rationale required) |
| `POST /v1/admin/api-keys` | Issue an API key (`administrator`) |

**Guarantees the tests check:**
- The audit log, decisions and signals are append-only, enforced by database
  triggers. The audit log is a SHA-256 hash chain computed by the database and
  re-verified independently in Python, so altered, re-hashed or deleted
  entries are detected.
- Roles come from a verified OIDC token or a hashed API key, never from a header.
- Callers bound to a nation can only touch that nation's data.
- Health, finance and governance decisions never go to a cloud model.
- Signed daily anchors (Ed25519) catch even a full, internally consistent
  rewrite of the audit history by someone with database superuser access.
- Rate limits per caller, a lower limit for decisions (which may call a paid
  model), and a lockout for addresses that keep failing authentication.
- Escalation opened / SLA breached notifications go out through a
  transactional outbox to a signed webhook, with retries.

## Use the core

```python
import asyncio
from datetime import UTC, datetime
from antos_core import DecisionRequest, load_profile, run

profile = load_profile("profiles/africa")
request = DecisionRequest(
    objective="Assess ICU capacity at Korle Bu Teaching Hospital",
    sector="health",
    signals=[{
        "signal_type": "bed_capacity_signal",
        "source_id": "korle_bu_emr",
        "source_type": "formal_institution",
        "observed_at": "2026-10-25T11:40:00Z",
        "payload": {"occupancy_rate": 0.85, "source_ref": "KBH-ICU-2026-10"},
    }],
)
result = asyncio.run(run(request, profile, now=datetime.now(UTC)))
print(result.decision.validation_state, result.decision.recommended_action.action)
```

`run()` uses the rule-based recommender at step 14 unless a `Recommender` is
passed in. A recommender can never set scores or validation states. Its action
can only be made more cautious by the postcheck, and it may only cite signals
that exist in the trail. Every result carries an `AuditRecord`.
`verify_replay(audit, profile)` re-executes the decision and checks that it
reproduces the recorded hash exactly.

## Status

Phases 1 (core engine) and 2 (platform) are built and tested. Two parts
are untested because no Docker was available: the Docker/compose files and
the Keycloak realm import. Live Claude and vLLM calls are also untested; the
tests use stand-ins. Phase 3 has started: the Next.js app (Situation Room,
Escalations, Decisions, Audit Explorer) is built. Still to come: Keycloak
sign-in in the app, the DHIS2 and finance adapters, and Grafana metrics.
