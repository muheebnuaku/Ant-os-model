# Decision Log — spec questions awaiting author sign-off

Phase 1 needed answers to the spec contradictions listed in
`ANT_OS_IMPLEMENTATION_PLAN.md` §2. To avoid blocking, each one has a
**provisional default** that is implemented as configuration where possible.
Dr. Boison (sovereign_admin) should confirm or change each one. Changing a
configured value needs no code change, but it does change `config_hash`, so
earlier decisions will no longer replay under the new profile (by design).

| ID | Question | Provisional default | Where to change |
|---|---|---|---|
| S1 | Base weights W1–W5 sum to 0.90 (health 0.92), but the spec says 1.0 | Keep the weights as authored; the engine **rescales W1–W5 to sum to 1.0**, keeping their ratios. W6 is applied as authored. | `ConfidenceWeights.normalized()` |
| S2 | Multiplying by the domain modifier makes "trusted" unreachable in agriculture and inflates finance | Modifier is **not** multiplied into confidence. The same value is used as `domain_sensitivity`, which scales contradiction severity. | `manifest.domain_modifier_mode` (`none` / `multiply`), `domain_sensitivity` per pack |
| S3 | Contradiction thresholds: paper 0.20/0.50 vs manifest 0.20/0.50/0.80 | Paper's version: < 0.20 minor, 0.20–0.49 moderate, ≥ 0.50 severe | `manifest.contradiction` |
| S4 | Health bed-capacity tolerance 0.08 vs 0.10 | 0.08 (the sector pack overrides the base manifest) | `sector_packs.yaml` |
| S5 | Tolerance had no unit; the reference code compared the first number in a payload as an absolute difference | **Relative** difference on a **declared field** per signal type. Undeclared types are not compared. | `signal_types.*.compare_field / tolerance` |
| S6 | 8 vs 10 layers; 16 vs 19 steps | 19-step contract; every decision's audit trace lists all 19 steps | `loop.py` |
| S7 | λ values were rounded inconsistently | Store **half-life**; derive λ = ln2 / t½. Education reuses governance's 35 h with no rationale given. | `half_life_hours` |
| S8 | "Decayed" was never assigned | A would-be trusted/provisional result whose mean freshness is below `decay_freshness_floor` (0.25) becomes **decayed** | `validation_thresholds.decay_freshness_floor` |
| S9 | Missing context was scored as evidence (inclusion always "exclusionary", 24HAE always "critical", EIS always "acceptable") | Missing inputs → `not_assessed`. Partial inputs are scored over what was supplied, with a `coverage` figure. | `engines/scoring.py` |

## Other provisional values (no source in the spec)

| Value | Default | Note |
|---|---|---|
| Domain stability input D | 0.65 for every sector | Same as the reference code. No per-sector value exists in any manifest. |
| Inclusion "critical exclusion" | score < 0.30 | The manifest names the outcome but gives no threshold. |
| Evidence-strength heuristic | base 0.30 + value 0.25 + cited source 0.15 + observation time 0.15 + lineage hash 0.15 | Replaces the reference "count the numbers in the payload" heuristic. |
| Signal `compare_field` names | e.g. `occupancy_rate`, `stock_days` | **Placeholders.** Confirm against the real DHIMS2 / GIFMIS / SCADA / AIS field mappings. |
| Escalation routing | CRITICAL → `sovereign_admin` in health and energy, `sector_lead` elsewhere | The pack default. A rule that names its own role and SLA overrides it. Among reasons at the top priority, the shortest SLA wins. |

## Phase 2 provisional choices

| Value | Default | Note |
|---|---|---|
| Escalation rules | The source's 31 free-text triggers, translated into the rule language (`engines/triggers.py`) | Field names are placeholders, like `compare_field`. Missing data never fires a rule; undecided rules are listed in the step-19 trace. |
| Unnamed thresholds | Where the source gave none (`BoG_minimum`, `safety_threshold`, `sector_alert_threshold`, "threshold"), the rule compares against a field the source system sends with the signal | The author may prefer fixed values in the pack, which is a one-line change per rule. |
| Energy "72-hour fuel reserve" | `fuel_stock_signal.stock_days < 3` | Expressed in days to match the declared `stock_days` field. |
| Sovereign model route | health, finance and governance only ever use an on-prem model; with none configured they use the rule-based recommender | Runbook §7 names "security-sensitive" packs without listing them. |
| Who can change configuration | `PUT /v1/admin/config` needs `policy_threshold_control` or `weight_recalibration` (`sovereign_admin`) | The API schema also allows `administrator`. That was narrowed because thresholds are a sovereignty matter. |
| Escalation handling | The assigned role, or anyone with `override_reviews` (regulator), may acknowledge or resolve. Resolving requires a note. | `sovereign_admin` has no escalation permission in the source manifest but is the CRITICAL route. |
| SLA breach | Marked once (`breached_at`) and audited. The item is not re-routed and no one is notified yet. | No escalation path after a breach is defined in the spec. |
| Roles | `roles.yaml` holds the master manifest v1.0 roles, kept outside the decision config | Changing permissions therefore does not change `config_hash`. |
| Header binding | The API schema's `role_header_binding_required` is **not** implemented | Roles from headers can be forged. Roles come only from tokens or API keys. |
| Rate limits | 600 requests/min per caller; 60 decisions/min; 20 failed logins/min per address, then locked out until the minute ends | Fixed windows. Tune once real traffic is known. |
| Notifications | One signed webhook receives all events, routed downstream by `assigned_role`. 8 attempts with backoff of up to 1 hour, then marked failed. | SMS, email and chat bridges sit behind the webhook. Notifications carry no signal data. |
| Audit anchors | Daily at 00:05 UTC, Ed25519. Each anchor is also sent out as a notification so that copies exist outside the database. | Real protection needs the copies held by an independent party (e.g. the regulator or a partner node), and the signing key kept off the database host. |

## Calibration findings

**C1 — the confidence floor is too high for empty evidence.** A single manual
signal that is 48 hours old, has an empty payload and no lineage still scores
≈ 0.38 in health. That is CONFLICTED, not BLOCKED, because neutral consistency
(0.50) and domain stability (0.65) contribute about 0.15 whatever the evidence
says. The postcheck still prevents action on it (the floor is *investigate*,
and the decision is escalated), but the author may want one of these:
(a) a minimum evidence strength below which the state is BLOCKED,
(b) neutral consistency of 0 for single-source evidence, or
(c) the empirical recalibration planned for Phase 5.
Covered by `test_empty_stale_signal_is_not_trusted`.

**C2 — a low-reliability source softens the contradictions it raises.**
Contradiction severity = relative difference × *mean source reliability* ×
domain sensitivity. In the demo, the Electoral Commission reported 61% turnout
and a community observer 79% (a 23% relative difference). Severity was
0.23 × 0.675 × 1.05 ≈ 0.16, which is "minor", so the governance rule
`contradiction.electoral_signal >= moderate` did not fire. A community
source contradicting an official figure therefore looks *less* serious than
two official sources disagreeing. That is the prestige bias the paper (§VI.C)
says the system avoids. Options:
(a) use the *maximum* reliability of the pair, so a conflict is as serious as
its most credible side;
(b) drop reliability from severity and let it act only on confidence;
(c) keep it as it is, and add per-sector rules on the raw relative difference
for sensitive signals such as electoral data.
The confidence score already discounts low-reliability evidence, so (a) or (b)
avoid counting that discount twice.
