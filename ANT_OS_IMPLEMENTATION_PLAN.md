# ANT-OS Ω — Implementation Plan & Recommended Stack

*Draft v0.1 · 2026-10-25 · Based on a full read of every file in this folder*

---

## 0. What was reviewed

| Artifact | Version | What it is |
|---|---|---|
| `ANT_OS_OMEGA_unified_install_manifest_v1_2.yaml` | 1.2 | Generic engine spec: 8 layers, 16-step contract, confidence/λ/EIS/local-fit |
| `ANT_OS_OMEGA_universal_api_llm_integration_schema_v1_2.yaml` | 1.2 | REST contract, middleware chain, LLM/adapter contracts |
| `ANT_OS_OMEGA_calibration_governance_annex_v1_2.yaml` | 1.2 | Rationale for weights, λ table, EIS variables, reference sector packs |
| `AFRICA_OS_OMEGA_master_manifest_v1_0.yaml` | 1.0 | Africa profile: 24HAE, Ubuntu, inclusion engine, 10 layers, 19-step contract, 12 guardrails |
| `AFRICA_OS_OMEGA_sector_packs_core8_v1_0.yaml` | 1.0 | 8 sector packs (health, agri, finance, energy, transport, education, governance, ports) |
| `AFRICA_OS_OMEGA_api_schema_v1_0.yaml` | 1.0 | Africa API (adds inclusion, 24HAE, AfCFTA, entrepreneur, university) |
| Academic Paper v1.0, Deployment Runbook v1.0 | — | Theory, pilot design (GHS + BoG), ops runbook |
| `africa_os_omega_reference_impl_v1_0.zip` → v1.1 → `v1_2_intelligence_os.zip` | code | FastAPI + Pydantic reference implementation (~3.6k lines, 23 tests) |
| `africa_os_omega_ui.html`, `situation_room_dashboard.html`, `entrepreneur_interface.html` | UI | Static HTML mockups |

**Bottom line:** the *doctrine and math* are well specified. The *code* is a prototype. It shows the shape of the system, but it is not yet the "deployable system" the paper and runbook describe. The plan below keeps what's good (Python/FastAPI, Pydantic contracts, deterministic engines, LLM-at-one-step-only), fixes the spec contradictions, and lays out a production architecture that holds up the sovereignty and auditability claims in practice.

---

## 1. Resolve naming and scope first

Two names are in use. The documents themselves suggest a clean split:

- **ANT-OS Ω = the engine.** A model-agnostic, sector-agnostic, validation-first reasoning layer (the v1.2 manifest). Reusable anywhere.
- **AFRICA-OS Ω = the doctrine profile running on ANT-OS.** 24HAE, Ubuntu, inclusion, AfCFTA, the 8 Ghana sector packs and federation (the v1.0 Africa manifest).

In code this becomes `antos-core` (engine library) + `profiles/africa` (policy pack, sector packs, prompts). That keeps the engine credible to non-African buyers and stops the doctrine from being hardcoded into the math.

---

## 2. Spec contradictions to fix before writing more code

These must be decided by the author (sovereign_admin), because they change results.

| # | Issue | Where | Recommendation |
|---|---|---|---|
| S1 | **Confidence weights W1–W5 sum to 0.90, not 1.0.** The spec says they "must sum to 1.0". Health overrides sum to 0.92. | All manifests, `sector_packs.py` | Either renormalise (0.311/0.200/0.178/0.200/0.111) or drop the "sum to 1.0" rule. Enforce whichever you pick with a validator. |
| S2 | **The domain modifier is applied as a post-multiplier.** Max confidence for agriculture is 0.90 × 0.95 = 0.855, so "trusted" is almost never reachable. Finance (×1.20) inflates weak evidence. | `ConfidenceEngine.score` | Use the modifier to shift *thresholds* per domain, or feed it as the D input. Don't scale the final score. |
| S3 | **Contradiction severity thresholds differ.** The paper says minor <0.20 / moderate 0.20–0.49 / severe ≥0.50. The manifest and code say 0.20 / 0.50 / 0.80. | Paper vs manifest | Pick one. The paper's version is stricter and better suited to health. |
| S4 | **Health bed-capacity tolerance:** 0.08 in the paper and sector pack, 0.10 in the v1.2 manifest. | — | 0.08 (sector pack wins over the base manifest). |
| S5 | **Contradiction tolerance has no defined unit.** The code compares the *first numeric field* of two payloads as an absolute difference, so "3 beds vs 5 beds" gives a diff of 2, which is far above 0.08. | `ContradictionEngine` | Define tolerance as a **relative** difference on a **named field** declared per signal type: `|a−b| / max(|a|,|b|)`. |
| S6 | **Layer count and contract length:** 8 layers + 16 steps (ANT v1.2), 10 layers + 19 steps (AFRICA v1.0), 5 layers (runbook). | — | Canonical: 10 layers, 19 steps. The runbook's "5 layers" are *deployment tiers*, so rename them. |
| S7 | λ values: agriculture 0.035 vs 0.0347, governance 0.020 vs 0.0198. Education reuses governance λ with no rationale. | — | Store **half-life** as the source of truth and derive λ = ln2 / t½. |
| S8 | The "Decayed" validation state is defined but never assigned. | Engine | Rule: the previous state was trusted/provisional **and** freshness < 0.25 → decayed. |
| S9 | Inclusion, 24HAE and EIS inputs fall back to silent defaults when omitted. Inclusion defaults to 0.5, so the result is always "exclusionary". 24HAE defaults score 0.175, which is always CRITICAL. EIS defaults to 0, which is always "acceptable". | `schemas.py` | Add an explicit `not_assessed` state. Never score missing data as if it were evidence (truth guardrail). |

**Credibility gaps (paper/runbook vs code):** the paper claims 4,670 lines and 50 passing tests. The code has about 3,575 lines and **23** tests. The runbook references `tests/test_federation.py` (27 tests), `smoke_test_decision.py`, `PATCH /v1/escalations/{id}` and `/v1/admin/config`. **None of these exist.** The Continental Federation Schema is cited but has **no code and no spec file**. Fix the code or the claims before the paper is submitted or the pilot is pitched to GHS/BoG.

---

## 3. Defects in the current reference code

Ordered by severity. Every item was checked against the v1.2 source.

1. **The reasoning loop's LLM call can never succeed.** `reasoning_loop.py` posts to Anthropic with no `x-api-key` or `anthropic-version` header, and `ReasoningLoop` is built without an LLM client. Step 14 therefore *always* falls back to rules, and nothing reports it.
2. **Sector agents let the LLM write the scores.** `SectorIntelligenceResult(**data)` takes `confidence`, `validation_state`, `hae_alignment_score`, etc. straight from the model's JSON. This breaks the core doctrine: "LLM at Step 14 only, all other steps deterministic" and the *technology subordination* guardrail (ABSOLUTE). The agents also bypass the 19-step loop entirely, so the codebase has two pipelines.
3. **The Situation Room shows invented data as live.** `_default_signals()` feeds hardcoded numbers ("84 beds", "2850 MW") with `freshness=0.85` into every dashboard run. All three HTML UIs use `Math.random()` and never call the API. This breaks the truth guardrail.
4. **Freshness is always ~1.0.** Ingest stamps every signal with `now()` and ignores the source's observation time, so the λ-decay machinery never takes effect.
5. **The local fit test always passes.** It is called with all six dimensions defaulting to `True`.
6. **Audit immutability is not enforced.** `REVOKE ... FROM PUBLIC` has no effect on Supabase roles. The `service_role_all FOR ALL` policy grants update and delete. There is no hash chain, and replay returns a summary, not the inputs, so the decision **cannot be reproduced**.
7. **Sector escalation rules are never evaluated.** Every escalation goes to `SECTOR_LEAD` with a hardcoded SLA, and nothing persists the escalation.
8. **Auth is a single shared API key** with a hardcoded dev default. CORS is `*`. The spec's `X-ANTOS-Role` header would let callers pick their own role.
9. **The v1.2 `main.py` regressed.** Trails, escalation and admin endpoints from v1.0 are gone. `supabase_store.py` exists but is not wired in. The audit log is local JSONL.
10. The model ID `claude-sonnet-4-20250514` is outdated. JSON is parsed by fence-stripping (`lstrip("```json")` strips *characters*, not a prefix).

---

## 4. Recommended stack

Chosen for three constraints in the documents: **sovereignty** (must run on-prem in a ministry, with no hard dependency on any one foreign cloud), **intermittent connectivity** (district and CHPS level), and **auditability** (every decision replayable).

| Concern | Choice | Why |
|---|---|---|
| Language (engine + API) | **Python 3.12**, `uv` for packaging | Keeps the existing code. Best numeric and ML ecosystem. Pydantic contracts already written. |
| API framework | **FastAPI** + **Pydantic v2** | Already used. OpenAPI generated for free, which drives the TS client and contract tests. |
| Engine library | `antos-core`: pure functions, **no I/O** | Deterministic, property-testable, embeddable offline (edge nodes, notebooks for researchers). |
| Config / sector packs | YAML manifests → validated Pydantic models → **versioned rows in Postgres**, content-hashed | The manifest is the single source of truth. Every decision records the config hash it ran under. |
| Primary database | **PostgreSQL 16** (self-hosted, or managed in an African region) + **SQLAlchemy 2 (async) / asyncpg** + **Alembic** | Portable and sovereign. Supabase stays an *optional hosting choice* for the pilot, not a code dependency. |
| Time-series signals | **TimescaleDB** extension (when volume justifies it) | Hypertables for signals and metrics. Same Postgres, no new system. |
| Raw lineage storage | **S3-compatible object store** (MinIO on-prem, or cloud S3) | Raw payloads stored as received, referenced by hash from `signals`. |
| Audit store | Postgres `audit_log`, **append-only by trigger** + **SHA-256 hash chain** (`prev_hash`) + daily signed Merkle root | Tamper-evident, not just tamper-discouraged. The app's DB role has INSERT only. |
| Cache | **Redis 7 / Valkey** | Dashboard TTL cache, rate limiting, idempotency keys. |
| Background jobs / queue | **Phase 1:** Redis + `arq` workers. **Phase 4:** **NATS JetStream** | `arq` covers ingestion, SLA timers and agent runs. NATS *leaf nodes* fit offline-first district nodes and cross-border federation. Kafka is overkill below ~10⁵ signals/hour. |
| LLM gateway | Internal `ModelGateway` interface with adapters: **Anthropic SDK** (cloud default), **OpenAI-compatible** (covers **vLLM** / **Ollama** sovereign models) | Matches the spec's provider-agnostic contract. Route by sector pack: security-sensitive packs are pinned to on-prem models (runbook §7). |
| Cloud LLM default | **Claude Opus 5.5** (`claude-opus-5-5`), structured outputs via `client.messages.parse()` / `output_config.format`, `effort` tuned per route, refusal handling | Guaranteed-schema JSON replaces fence-stripping. The schema only allows narrative + an enum action, never scores. |
| Sovereign LLM | **vLLM** serving an open-weight model on on-prem GPUs | Pick the model with an eval harness on African-language and sector test sets (paper limitation #3). |
| Identity (humans) | **Keycloak** (OIDC; can federate to national SSO) | Self-hostable. Roles from the manifest map to realm roles. Role comes from the **token**, never a header. |
| Identity (machines / federation) | Scoped API keys (hashed, rotated) for adapters. **mTLS** (step-ca or national CA) + **JWS-signed** signal envelopes between nodes | Matches runbook §7. |
| Authorization | Permission map from the manifest, enforced in a FastAPI dependency + **Postgres RLS** on `tenant_id` / `nation_id` | Least privilege at two layers. |
| Frontend (institutional) | **Next.js (React + TypeScript)**, TanStack Query, client generated from OpenAPI, **ECharts**, **MapLibre** (corridor map), **SSE** for live updates | One app with role-based areas: Situation Room, Escalation Console, Audit Explorer, Sector Admin, Research Portal. |
| Entrepreneur / field access | **PWA** (offline cache) + **USSD/SMS** via Africa's Talking / Hubtel + optional WhatsApp | The inclusion doctrine needs reach beyond smartphones and broadband. |
| Legacy adapters | Adapter SDK: REST, DB pull, CSV/file drop, webhook, manual form, **DHIS2 (DHIMS2)**, **HL7 FHIR** | Each emits the signal contract with a raw-source hash. |
| Observability | **OpenTelemetry** → Prometheus + Grafana + **Loki** (lighter than Elastic) | Domain metrics from the manifest (escalation_rate, contradiction_rate, stale_signal_rate, …). |
| Packaging / deploy | Docker → **docker compose** (pilot) → **k3s / Kubernetes + Helm** (production / on-prem). Terraform for cloud. **SOPS or Vault** for secrets | Same artifacts deploy to cloud, on-prem and hybrid (the manifest's three profiles). |
| CI | GitHub Actions: ruff, mypy, pytest + **Hypothesis**, contract tests, migration check, container scan | — |

**Explicitly not recommended now:** Kafka, Temporal, microservices per engine, or a second backend in Node. One modular monolith plus workers until a pilot gives real load numbers.

---

## 5. Target architecture

```
                ┌─────────────── Interfaces ────────────────┐
                │ Next.js app (Situation Room, Escalations, │
                │ Audit, Admin, Research) · PWA · USSD/SMS  │
                └───────────────┬───────────────────────────┘
                                │ OIDC (Keycloak) / API keys
┌───────────────────────────────▼───────────────────────────────┐
│ API (FastAPI) — middleware chain from the API schema:         │
│ auth → role → mode → sector-pack → validate → guardrail-pre → │
│ execute → guardrail-post → local-fit → ecology-post → audit   │
├───────────────┬────────────────┬──────────────────────────────┤
│ Reasoning     │ Escalation     │ Admin/Config (versioned,     │
│ service       │ service (SLA)  │ sovereign_admin, audited)    │
└──────┬────────┴───────┬────────┴──────────────┬───────────────┘
       │ antos-core (pure, deterministic engines)│
       │ confidence · contradiction · trail ·    │
       │ ecology · inclusion · 24HAE · local-fit │
       │ · route · policy                        │
       │            ▲ Step 14 only               │
       │     ModelGateway → Claude │ vLLM │ Ollama│
┌──────▼────────────────────────────────────────▼───────────────┐
│ Postgres(+Timescale) · Redis · Object store · Audit hash chain│
└──────▲────────────────────────────────────────────────────────┘
       │ workers (arq): ingest, normalise, freshness refresh,
       │ situation-room runs, SLA timers
┌──────┴──────────────┐            ┌────────────────────────────┐
│ Adapters: DHIS2,    │            │ Federation gateway (Ph. 4) │
│ FHIR, REST, CSV,    │            │ mTLS + JWS + consent L0–L4 │
│ manual, USSD        │            │ NATS leaf ↔ partner nodes  │
└─────────────────────┘            └────────────────────────────┘
```

### Non-negotiable design rules (turning the doctrine into code)

1. **One pipeline.** Sector agents become *prompt profiles* used at Step 14 of the single 19-step loop. The Situation Room runs that loop per sector over **stored, real signals**. If a sector has no fresh signals, it shows "no data", never a default.
2. **The LLM never produces a number or a state.** Its output schema is `{action: enum, primary_recommendation, secondary[], ubuntu_note, hae_note, escalation_suggested: bool, cited_signal_ids[]}`. Post-check: `cited_signal_ids` must exist in the trail (truth guardrail), and the action may never be *less cautious* than the deterministic state allows.
3. **Replay means re-execution.** Each decision stores the input snapshot hash, config version hash, engine version, model ID, and the exact prompt and response. `/v1/audit/replay` re-runs the deterministic steps and must reproduce the result bit-for-bit. The Step 14 output is shown as recorded.
4. **Freshness uses `observed_at`** supplied by the source, with `received_at` kept separately. A missing `observed_at` counts against evidence strength.
5. **Unknown ≠ zero.** Every scorer can return `not_assessed`, and the decision object shows which checks actually ran.
6. **Local fit gets real evaluators.** Rule checks from sector-pack data (jurisdiction law list, language config, infrastructure profile), an LLM-as-judge for linguistic and cultural dimensions (scored, auditable), and a required human attestation per sector pack before go-live.
7. **Federation schema uses an allowlist.** Federated payloads must match a declared per-signal-type schema. A PII *denylist* is not enough.

---

## 6. Repository layout

```
ant-os/
├── packages/
│   └── antos-core/            # pure engines + Pydantic contracts (no I/O)
│       ├── confidence.py  contradiction.py  freshness.py  ecology.py
│       ├── inclusion.py   hae.py  local_fit.py  policy.py  route.py
│       └── loop.py            # 19-step contract as a pure state machine
├── services/
│   ├── api/                   # FastAPI app, middleware chain, routers
│   ├── worker/                # arq jobs: ingest, situation room, SLA timers
│   └── federation/            # Phase 4
├── adapters/                  # dhis2, fhir, rest, csv, ussd, manual
├── profiles/africa/           # manifests, sector packs (YAML), prompt library
├── db/migrations/             # Alembic; audit triggers + hash chain
├── web/                       # Next.js app
├── deploy/                    # compose, helm, terraform
└── tests/                     # golden, property, contract, replay, LLM evals
```

---

## 7. Phased delivery

| Phase | Weeks | Outcome | Exit criteria |
|---|---|---|---|
| **0. Spec freeze** | 1–2 | Decisions on S1–S9. One canonical manifest, schema-validated. Paper and runbook claims corrected. | Signed-off manifest v1.3. CI rejects invalid packs. |
| **1. Core engine** | 3–6 | `antos-core` rewritten against the frozen spec. Golden tests (every number in the paper's tables), Hypothesis properties (bounds, monotonicity, weight sums). | ≥150 tests, 100% branch coverage on engines. |
| **2. Platform** | 5–10 | Postgres + migrations, hash-chained audit, ingest with `observed_at`, single 19-step loop, ModelGateway (Claude + vLLM) with structured output, escalations with real SLA timers, Keycloak RBAC, admin config versioning. | Runbook checklist passes for real. Replay reproduces 100% of decisions. |
| **3. Pilot product** | 9–14 | Next.js Situation Room + Escalation Console + Audit Explorer on live data. DHIS2 adapter (GHS) and a finance feed adapter (BoG test data). Grafana dashboards for the paper's Table III metrics. | GHS/BoG sandbox running 30 days. Metrics collected automatically. |
| **4. Reach & federation** | 14–24 | USSD/SMS + PWA entrepreneur access. Federation gateway (mTLS, JWS, consent levels, cross-border recalibration). NATS leaf nodes for offline sites. | Two nodes exchange signals. Federation test suite passes. |
| **5. Calibration** | after 60–90 days of pilot data | Fit confidence weights and λ against observed outcomes (paper limitation #1). Inclusion engine validated with community reviewers (limitation #4). | Recalibration recorded via audited admin flow. |

---

## 8. Testing strategy

- **Golden tests:** every value in the paper and manifests, e.g. health freshness at 1 h ≈ 0.50, and the EIS thresholds.
- **Property tests (Hypothesis):** confidence ∈ [0,1]. More contradiction never raises confidence. Older signals never get fresher. Weights validate.
- **Guardrail tests:** each of the 12 guardrails has a test that tries to break it, e.g. the LLM says "proceed" on a BLOCKED state, or the LLM cites a signal that doesn't exist.
- **Replay tests:** random decisions re-executed from the audit log must match.
- **Contract tests:** OpenAPI ↔ the API schema YAML. Generated TS client compiles.
- **LLM evals:** per sector prompt set, graded for groundedness, action-enum correctness, and language. Run against every candidate model, including sovereign ones.
- **Load test:** k6 at the pilot's expected signal rate × 10.

---

## 9. Immediate next steps

1. The author decides S1–S9 (about an hour's discussion). Everything else depends on it.
2. Set up the monorepo skeleton and CI, and port the engines into `antos-core` with golden tests.
3. Replace the Step-14 call with the ModelGateway and structured outputs, and delete `_default_signals()`.
4. Write the Postgres migrations with the trigger-enforced, hash-chained audit log.
5. Correct the paper's line and test counts, and the runbook's references to files that don't exist.

*Attribution: ANT-OS Ω / AFRICA-OS Ω, the VPF and the 24-Hour Africa Economy Policy are the work of Dr. David King Boison. All deployments must keep this attribution, as the manifests require.*
