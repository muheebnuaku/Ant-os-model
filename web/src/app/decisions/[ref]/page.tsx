"use client";

import { ChevronRight, Download, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useState } from "react";

import { ConfidenceBreakdown } from "@/components/charts";
import { DataTable } from "@/components/DataTable";
import {
  Badge,
  EmptyState,
  ErrorNotice,
  Notice,
  PageHeader,
  Section,
  SkeletonRows,
  Tabs,
  Time,
  absolute,
  humanize,
  pct,
  statusLabel,
  type Tone,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useCrumbs } from "@/lib/crumbs";
import { useApi, useQueryState } from "@/lib/hooks";
import { CAN, useSession } from "@/lib/session";
import { useToast } from "@/lib/toast";
import type { DecisionDetail, Escalation, ReplayReport, Sector, StoredDecision } from "@/lib/types";

type Tab = "overview" | "evidence" | "confidence" | "record";

interface AuditEntry {
  seq: number;
  entry_hash: string;
  prev_hash: string;
  payload: {
    audit: { trace: { step: number; name: string; detail: Record<string, unknown> }[]; engine_version: string; config_hash: string; input_hash: string; decision_hash: string };
    model_exchange: { provider: string; model: string; prompt_version: string; response_text: string | null; latency_ms: number | null; error: string | null } | null;
  };
}

const SOURCE_KIND: Record<string, string> = {
  formal_institution: "Official institution", api_feed: "Automated feed", satellite: "Satellite",
  informal_operator: "Informal operator", community_source: "Community report", manual_entry: "Entered by hand",
};

const STEP_NAMES: Record<number, string> = {
  1: "Receive the evidence", 2: "Classify by sector", 3: "Record where each item came from", 4: "Check freshness",
  5: "Weigh each source", 6: "Group into a trail", 7: "Look for disagreements", 8: "Score confidence",
  9: "Set the evidence result", 10: "Check inclusion", 11: "Check the 24-hour economy", 12: "Check environmental impact",
  13: "Check intra-African trade", 14: "Write the advice", 15: "Write the decision", 16: "Apply safeguards",
  17: "Test local fit", 18: "Seal the record", 19: "Clear for action or call a person",
};

const GROUPS = [
  { title: "Gathering evidence", steps: [1, 2, 3, 4, 5, 6] },
  { title: "Weighing", steps: [7, 8, 9] },
  { title: "Doctrine checks", steps: [10, 11, 12, 13] },
  { title: "Advice", steps: [14] },
  { title: "Safeguards and record", steps: [15, 16, 17, 18, 19] },
];

const SAFEGUARDS: Record<string, string> = {
  technology_subordination_guardrail: "The advised action was made more cautious to match the evidence.",
  truth_guardrail: "References to evidence that does not exist were removed.",
  contradiction_guardrail: "Sources disagreed, so confidence was reduced.",
  inclusion_guardrail: "Some affected groups may be left out.",
  ecology_guardrail: "The environmental impact is at warning level.",
  "24hae_policy": "The decision raises 24-hour economy concerns.",
  local_fit_guardrail: "The decision may not fit local conditions.",
};

export default function DecisionPage() {
  return <Suspense fallback={null}><Decision /></Suspense>;
}

function Decision() {
  const { ref } = useParams<{ ref: string }>();
  const { can } = useSession();
  const toast = useToast();
  const [tab, setTab] = useQueryState<Tab>("tab", "overview");
  const stored = useApi<StoredDecision>(`/v1/decisions/${encodeURIComponent(ref)}`);
  const sectors = useApi<Sector[]>("/v1/sectors");
  const auditor = can(CAN.audit);
  const entry = useApi<AuditEntry>(auditor && stored.data && tab === "record" ? `/v1/audit/entries/${stored.data.audit_seq}` : null);
  const [replay, setReplay] = useState<ReplayReport | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const d = stored.data?.decision as unknown as DecisionDetail | undefined;
  useCrumbs([{ label: "Decisions", href: "/decisions" }, { label: d?.objective ?? "Decision" }]);

  async function verify() {
    setVerifying(true);
    setError(null);
    try {
      const r = await api<ReplayReport>("/v1/audit/replay", { body: { audit_ref: stored.data?.audit_ref } });
      setReplay(r);
      toast(r.match && r.projection_matches_audit ? "Decision verified" : "Verification failed", r.match && r.projection_matches_audit ? "good" : "critical");
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
    } finally {
      setVerifying(false);
    }
  }

  function exportRecord() {
    const blob = new Blob([JSON.stringify(stored.data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${stored.data?.audit_ref ?? "decision"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (stored.error) return <div className="page"><PageHeader title="Decision" /><ErrorNotice error={stored.error} /></div>;
  if (!stored.data || !d) return <div className="page"><div className="card"><SkeletonRows rows={6} /></div></div>;

  const s = stored.data;
  const esc = s.escalation as unknown as Escalation | null;
  const rec = d.recommended_action;
  const byModel = rec.produced_by.startsWith("llm:");
  const verdict: { tone: Tone; text: string } = d.allowed_for_action
    ? { tone: "good", text: "Cleared to act." }
    : d.human_escalation_required
      ? { tone: "warning", text: "A person must review this before anyone acts." }
      : { tone: "neutral", text: "Not enough trustworthy evidence to act." };
  const verified = replay ? replay.match && replay.projection_matches_audit : null;
  const sector = sectors.data?.find((x) => x.sector_id === d.sector);
  const fieldFor = (type: string) => sector?.signal_types[type] ?? null;
  const thresholds = sector?.validation_thresholds;

  return (
    <div className="page">
      <PageHeader
        title={d.objective}
        description={<>{humanize(d.sector)} · {d.nation_id === "GH" ? "Ghana" : d.nation_id} · evaluated {absolute(s.evaluated_at)}</>}
        actions={<>
          {auditor ? <button type="button" className="btn" onClick={() => void verify()} disabled={verifying}><ShieldCheck size={16} strokeWidth={1.5} aria-hidden />{verifying ? "Verifying…" : "Verify decision"}</button> : null}
          <button type="button" className="btn" onClick={exportRecord}><Download size={16} strokeWidth={1.5} aria-hidden />Export</button>
        </>}
      />

      {verified !== null ? (
        <Notice tone={verified ? "good" : "critical"}>
          {verified
            ? "Verified. Re-running this decision from its sealed record reproduced it exactly."
            : "Verification failed. Re-running this decision did not reproduce the record. Inform the regulator."}
        </Notice>
      ) : null}
      <ErrorNotice error={error} />

      <section className="card card-pad stack" aria-label="Verdict" style={{ gap: 20 }}>
        <div className="layout-main" style={{ gap: 32 }}>
          <div className="stack-sm">
            <span className="t-caption t-muted">ANT-OS advises</span>
            <div className="row" style={{ gap: 10 }}>
              <span className="t-verdict">{statusLabel(rec.action)}</span>
              <Badge status={rec.action} />
            </div>
            <p style={{ fontSize: 15, lineHeight: "24px", maxWidth: "62ch" }}>{rec.primary_recommendation}</p>
          </div>
          <div className="stack-sm" style={{ borderLeft: "1px solid var(--border)", paddingLeft: 24 }}>
            <span className="kpi-label">Confidence</span>
            <span className="kpi-value">{pct(d.confidence)}</span>
            <ConfidenceBar value={d.confidence} thresholds={thresholds} />
            <div className="row"><span className="t-small t-muted">Evidence result</span><Badge status={d.validation_state} /></div>
            <span className="t-small t-muted">
              Advice written by {byModel ? <>{rec.produced_by.split(":").slice(2).join(":")}, checked by the rules</> : "the built-in rules"}
            </span>
          </div>
        </div>
        <Notice tone={verdict.tone}>{verdict.text}</Notice>
      </section>

      <div className="stack">
        <Tabs<Tab> value={tab} onChange={setTab} tabs={[
          { value: "overview", label: "Overview" },
          { value: "evidence", label: `Evidence (${s.evidence.length})` },
          { value: "confidence", label: "Confidence" },
          { value: "record", label: "Record" },
        ]} />

        {tab === "overview" ? (
          <div className="page" style={{ gap: 32, marginTop: 8 }}>
            <Section title="Why">
              <div className="card card-pad stack">
                {rec.secondary_recommendations.length ? (
                  <ul style={{ margin: 0, paddingLeft: 20 }}>{rec.secondary_recommendations.map((x) => <li key={x}>{x}</li>)}</ul>
                ) : null}
                <div className="grid-2">
                  <div><h3>Effect on people (Ubuntu)</h3><p className="t-secondary" style={{ marginTop: 4 }}>{rec.ubuntu_note || "No note recorded."}</p></div>
                  <div><h3>Effect on the 24-hour economy</h3><p className="t-secondary" style={{ marginTop: 4 }}>{rec.hae_note || "No note recorded."}</p></div>
                </div>
              </div>
            </Section>

            <Section title="Checks" description="Each check the decision was tested against.">
              <div className="card">
                <DataTable caption="Checks" rowKey={(r) => r.name} empty={{ title: "No checks" }} rows={checks(d)}
                  columns={[
                    { key: "n", header: "Check", render: (r) => <span className="cell-primary">{r.name}</span> },
                    { key: "r", header: "Result", render: (r) => <Badge status={r.result} /> },
                    { key: "f", header: "Finding", render: (r) => r.finding },
                  ]} />
              </div>
            </Section>

            <Section title="Safeguards applied">
              <div className="card card-pad">
                {d.guardrail_events.length ? (
                  <ul className="summary-list">
                    {d.guardrail_events.map((g) => {
                      const [code, ...rest] = g.split(":");
                      return <li key={g}><Badge tone="info">Safeguard</Badge><span>{SAFEGUARDS[code ?? ""] ?? humanize(code)} <span className="t-muted t-small">{rest.join(":").trim()}</span></span></li>;
                    })}
                  </ul>
                ) : <p className="t-muted">No safeguards were needed.</p>}
              </div>
            </Section>

            <Section title="Human review" actions={esc ? <Link className="btn btn-tertiary" href="/escalations">Open review queue</Link> : null}>
              <div className="card card-pad">
                {esc ? (
                  <div className="stack-sm">
                    <div className="row"><Badge status={esc.priority} /><span>Assigned to {humanize(esc.assigned_role)} · due {absolute(esc.due_at)}</span>{esc.status ? <Badge status={esc.status} /> : null}</div>
                    <ul style={{ margin: 0, paddingLeft: 20 }} className="t-secondary">{esc.reasons.map((r) => <li key={r.code}>{r.message}</li>)}</ul>
                  </div>
                ) : <p className="t-muted">No human review was required.</p>}
              </div>
            </Section>
          </div>
        ) : null}

        {tab === "evidence" ? (
          <div className="page" style={{ gap: 32, marginTop: 8 }}>
            <Section title="Evidence used" description="As recorded when the decision was evaluated.">
              <div className="card">
                <DataTable caption="Evidence used" rows={s.evidence} rowKey={(e) => e.signal_id} empty={{ title: "No evidence recorded" }}
                  columns={[
                    { key: "t", header: "Type", render: (e) => <span className="cell-primary">{humanize(e.signal_type)}</span> },
                    { key: "r", header: "Reading", numeric: true, render: (e) => { const f = fieldFor(e.signal_type); const v = f ? e.payload[f] : undefined; return v === undefined ? <span className="t-muted">Not given</span> : `${String(v)}`; } },
                    { key: "s", header: "Source", render: (e) => humanize(e.source_id) },
                    { key: "k", header: "Kind of source", render: (e) => SOURCE_KIND[e.source_type] ?? humanize(e.source_type) },
                    { key: "o", header: "Observed", render: (e) => e.observed_at ? <span title={absolute(e.observed_at)}>{absolute(e.observed_at)}</span> : <span className="t-muted">Not given</span> },
                    { key: "f", header: "Freshness", numeric: true, render: (e) => pct(e.freshness) },
                    { key: "l", header: "Reliability", numeric: true, render: (e) => pct(e.source_reliability) },
                  ]} />
              </div>
            </Section>
            <Section title="Disagreements found">
              <div className="card">
                <DataTable caption="Disagreements" rows={s.conflicts} rowKey={(c) => `${c.signal_a}${c.signal_b}`}
                  empty={{ title: "No disagreements", description: "The sources were consistent within tolerance." }}
                  columns={[
                    { key: "t", header: "Measure", render: (c) => <span className="cell-primary">{humanize(c.field)}</span> },
                    { key: "v", header: "Values", numeric: true, render: (c) => `${c.value_a} vs ${c.value_b}` },
                    { key: "d", header: "Difference", numeric: true, render: (c) => pct(c.relative_difference) },
                    { key: "o", header: "Allowed", numeric: true, render: (c) => pct(c.tolerance) },
                    { key: "s", header: "Severity", numeric: true, render: (c) => c.severity.toFixed(2) },
                  ]} />
              </div>
            </Section>
          </div>
        ) : null}

        {tab === "confidence" ? (
          <Section title="How confidence was calculated" description="Each component's score multiplied by its weight, less the disagreement penalty.">
            <div className="card card-pad">
              {s.confidence_breakdown ? (
                <ConfidenceBreakdown confidence={d.confidence}
                  inputs={(s.confidence_breakdown as { inputs: Record<string, number> }).inputs}
                  weights={(s.confidence_breakdown as { weights_applied: Record<string, number> }).weights_applied} />
              ) : <EmptyState title="Breakdown not recorded" />}
            </div>
          </Section>
        ) : null}

        {tab === "record" ? (
          auditor ? (
            <div className="page" style={{ gap: 32, marginTop: 8 }}>
              <Section title="The 19-step trail" description="Select a step to see what it recorded.">
                <div className="card card-pad">
                  {entry.data ? (
                    <ol className="timeline" style={{ listStyle: "none", margin: 0, padding: 0 }}>
                      {GROUPS.map((g) => (
                        <li key={g.title} className="timeline-group">
                          <div className="timeline-title">{g.title}</div>
                          {g.steps.map((n) => {
                            const step = entry.data!.payload.audit.trace.find((t) => t.step === n);
                            return (
                              <details key={n} className="timeline-step" data-flag={n === 14 ? "advice" : undefined}>
                                <summary>
                                  <span className="timeline-node" aria-hidden>{n}</span>
                                  <span>{STEP_NAMES[n]}</span>
                                  <ChevronRight className="chev" size={16} strokeWidth={1.5} aria-hidden />
                                </summary>
                                <pre className="json">{JSON.stringify(step?.detail ?? {}, null, 2)}</pre>
                              </details>
                            );
                          })}
                        </li>
                      ))}
                    </ol>
                  ) : entry.error ? <ErrorNotice error={entry.error} /> : <SkeletonRows rows={5} />}
                </div>
              </Section>
              <Section title="Verification">
                <div className="card card-pad stack-sm">
                  {verified === null ? <p className="t-muted">Not verified in this session. Use “Verify decision” above.</p>
                    : <Notice tone={verified ? "good" : "critical"}>{verified ? "This decision reproduces exactly from its sealed record." : "This decision did not reproduce from its record."}</Notice>}
                </div>
              </Section>
              <details className="disclosure">
                <summary><ChevronRight size={16} strokeWidth={1.5} aria-hidden />Technical record</summary>
                <div className="disclosure-body">
                  {entry.data ? (
                    <>
                      <dl className="kv">
                        <dt>Record</dt><dd className="t-mono">#{entry.data.seq} · {s.audit_ref}</dd>
                        <dt>Decision ID</dt><dd className="t-mono">{s.decision_id}</dd>
                        <dt>Fingerprint</dt><dd className="t-mono">{entry.data.entry_hash}</dd>
                        <dt>Links to</dt><dd className="t-mono">{entry.data.prev_hash}</dd>
                        <dt>Decision hash</dt><dd className="t-mono">{entry.data.payload.audit.decision_hash}</dd>
                        <dt>Rules version</dt><dd className="t-mono">{entry.data.payload.audit.config_hash}</dd>
                        <dt>Engine</dt><dd className="t-mono">{entry.data.payload.audit.engine_version}</dd>
                        <dt>Advice source</dt><dd className="t-mono">{rec.produced_by}{entry.data.payload.model_exchange?.latency_ms != null ? ` · ${entry.data.payload.model_exchange.latency_ms} ms` : ""}</dd>
                      </dl>
                      {entry.data.payload.model_exchange?.response_text ? (
                        <><h3>Exact model response</h3><pre className="json">{entry.data.payload.model_exchange.response_text}</pre></>
                      ) : null}
                      <h3>Raw decision</h3>
                      <pre className="json">{JSON.stringify(d, null, 2)}</pre>
                    </>
                  ) : <SkeletonRows rows={3} />}
                </div>
              </details>
            </div>
          ) : (
            <EmptyState title="The full record is available to auditors" />
          )
        ) : null}
      </div>
      <p className="t-caption t-muted">Record <Time iso={s.evaluated_at} /> · {s.audit_ref}</p>
    </div>
  );
}

function checks(d: DecisionDetail): { name: string; result: string; finding: string }[] {
  const contradictions = d.contradiction_count
    ? { result: d.contradiction_severity === "severe" ? "failed" : "concern", finding: `${d.contradiction_count} disagreement${d.contradiction_count > 1 ? "s" : ""} between sources (${d.contradiction_severity}).` }
    : { result: "passed", finding: "The sources are consistent." };
  return [
    { name: "Sources agree", ...contradictions },
    { name: "Inclusion", result: d.inclusion_state === "not_assessed" ? "not_assessed" : d.inclusion_state === "inclusive" ? "passed" : d.inclusion_state === "critical_exclusion" ? "failed" : "concern",
      finding: d.inclusion_state === "not_assessed" ? "Not assessed for this decision." : `${humanize(d.inclusion_state)} (score ${pct(d.inclusion_score)}).` },
    { name: "24-hour economy", result: d.hae_alignment_score === null ? "not_assessed" : d.hae_alignment_score >= 0.6 ? "passed" : "concern",
      finding: d.hae_alignment_score === null ? "Not assessed for this decision." : `Alignment ${pct(d.hae_alignment_score)}.` },
    { name: "Environment", result: d.ecology_state === "not_assessed" ? "not_assessed" : d.ecology_state === "acceptable" ? "passed" : d.ecology_state === "critical" ? "failed" : "concern",
      finding: d.ecology_state === "not_assessed" ? "Not assessed for this decision." : `${humanize(d.ecology_state)} impact${d.ecology_score !== null ? ` (${d.ecology_score.toFixed(2)})` : ""}.` },
    { name: "Local fit", result: d.local_fit_passed === null ? "not_assessed" : d.local_fit_passed ? "passed" : "failed",
      finding: d.local_fit_passed === null ? "Not assessed for this decision." : d.local_fit_passed ? "Fits local law, language and infrastructure." : `Concerns: ${d.local_fit_report.dimensions_failed.map(humanize).join(", ")}.` },
  ];
}

/** Confidence on a bar marked at the sector's provisional and trusted thresholds. */
function ConfidenceBar({ value, thresholds }: { value: number; thresholds?: { trusted: number; provisional: number } }) {
  return (
    <div className="conf-bar" role="img"
      aria-label={`Confidence ${pct(value)}${thresholds ? `; provisional from ${pct(thresholds.provisional)}, trusted from ${pct(thresholds.trusted)}` : ""}`}>
      <span className="fill" style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
      {thresholds ? (
        <>
          <span className="mark" style={{ left: `${thresholds.provisional * 100}%` }}><span>Provisional</span></span>
          <span className="mark" style={{ left: `${thresholds.trusted * 100}%` }}><span>Trusted</span></span>
        </>
      ) : null}
    </div>
  );
}
