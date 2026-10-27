"use client";

import { ChevronRight, Link2, ShieldAlert, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { DataTable } from "@/components/DataTable";
import {
  ContextBar,
  Drawer,
  ErrorNotice,
  Kpi,
  Kpis,
  Notice,
  PageHeader,
  Section,
  SkeletonRows,
  Time,
  absolute,
  who,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useApi, useNow } from "@/lib/hooks";
import { useToast } from "@/lib/toast";
import type { AuditEntrySummary, AuditVerify, NodeStatus } from "@/lib/types";

const EVENTS: Record<string, string> = {
  "decision.recorded": "Decision recorded",
  "signals.ingested": "Evidence received",
  "escalation.opened": "Review requested",
  "escalation.acknowledged": "Review picked up",
  "escalation.resolved": "Review resolved",
  "escalation.sla_breached": "Review deadline missed",
  "config.activated": "Rules updated",
  "audit.anchored": "Records sealed",
  "audit.replay_checked": "Decisions re-run",
  "api_key.created": "Access granted",
  "api_key.revoked": "Access revoked",
};

interface ReplayCheck { total: number; matched: number; ok: boolean; at: string }

export default function RecordsPage() {
  const now = useNow(30_000);
  const toast = useToast();
  const verify = useApi<AuditVerify>("/v1/audit/verify");
  const node = useApi<NodeStatus>("/v1/node");
  const lastReplay = useApi<AuditEntrySummary[]>("/v1/audit/entries?event_type=audit.replay_checked&limit=1");
  const replaySeq = lastReplay.data?.[0]?.seq;
  const replayDetail = useApi<{ payload: ReplayCheck }>(replaySeq ? `/v1/audit/entries/${replaySeq}` : null);
  const [eventType, setEventType] = useState("");
  const [before, setBefore] = useState<number | null>(null);
  const q = new URLSearchParams({ limit: "50" });
  if (eventType) q.set("event_type", eventType);
  if (before !== null) q.set("before_seq", String(before));
  const entries = useApi<AuditEntrySummary[]>(`/v1/audit/entries?${q.toString()}`);
  const latest = useApi<AuditEntrySummary[]>("/v1/audit/entries?limit=6");
  const anchors = useApi<{ up_to_seq: number }[]>("/v1/audit/anchors");
  const [verifiedAt, setVerifiedAt] = useState<string>(new Date().toISOString());
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [open, setOpen] = useState<{ entry: AuditEntrySummary; payload: unknown } | null>(null);

  const refreshAll = () => {
    verify.reload(); node.reload(); lastReplay.reload(); entries.reload(); latest.reload(); anchors.reload();
    setVerifiedAt(new Date().toISOString());
  };

  async function run(what: string, fn: () => Promise<unknown>, done?: string) {
    setBusy(what);
    setError(null);
    try {
      await fn();
      if (done) toast(done);
      refreshAll();
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
    } finally {
      setBusy(null);
    }
  }

  async function openEntry(e: AuditEntrySummary) {
    try {
      setOpen({ entry: e, payload: (await api<{ payload: unknown }>(`/v1/audit/entries/${e.seq}`)).payload });
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    }
  }

  const v = verify.data;
  const n = node.data;
  const replay = replayDetail.data?.payload;
  const sealed = new Set((anchors.data ?? []).map((a) => a.up_to_seq));

  return (
    <div className="page">
      <PageHeader
        title="Records & verification"
        description="The permanent, tamper-evident record of every action."
        actions={<button type="button" className="btn btn-primary" disabled={busy !== null} onClick={() => run("verify", async () => undefined, "Verification started")}>{busy === "verify" ? "Verifying…" : "Verify all records"}</button>}
      />

      <ErrorNotice error={verify.error ?? error} />

      <section className="card card-pad" aria-label="Integrity">
        {v ? (
          <div className="integrity">
            <span className="integrity-icon" style={{ background: v.ok ? "var(--good-bg)" : "var(--critical-bg)", color: v.ok ? "var(--good)" : "var(--critical)" }} aria-hidden>
              {v.ok ? <ShieldCheck strokeWidth={1.5} /> : <ShieldAlert strokeWidth={1.5} />}
            </span>
            <div role="status">
              <div style={{ fontSize: 18, lineHeight: "26px", fontWeight: 600, letterSpacing: "-0.01em" }}>
                {v.ok ? `All ${v.chain.entries_checked.toLocaleString()} records intact` : "Integrity check failed"}
              </div>
              <div className="t-small t-muted">
                {v.ok
                  ? `${v.anchors.anchors_checked} seal${v.anchors.anchors_checked === 1 ? "" : "s"} valid. No record has been altered or removed.`
                  : v.chain.problem ? `Record ${v.chain.first_bad_seq}: ${v.chain.problem}.` : v.anchors.problems[0]}
              </div>
            </div>
            <dl className="facts">
              <div><dt>Last verified</dt><dd><Time iso={verifiedAt} now={now} /></dd></div>
              <div><dt>Last sealed</dt><dd>{n?.last_anchor_at ? <Time iso={n.last_anchor_at} now={now} /> : "Not yet"}</dd></div>
              <div><dt>Since last seal</dt><dd>{n ? `${n.entries_since_anchor.toLocaleString()} records` : "Not recorded"}</dd></div>
            </dl>
          </div>
        ) : <SkeletonRows rows={2} />}
      </section>

      <Kpis count={4}>
        <Kpi label="Records" value={v ? v.chain.entries_checked.toLocaleString() : "…"} context="Linked in one unbroken chain" />
        <Kpi label="Seals" value={v ? v.anchors.anchors_checked : "…"} context="Signed checkpoints of the chain" />
        <Kpi label="Decisions replayed" value={replay ? `${replay.matched} / ${replay.total}` : "Not run"}
          context={replay ? <>Last run <Time iso={replay.at} now={now} /></> : "Run a re-check below"} />
        <Kpi label="Last seal" value={n?.last_anchor_at ? <Time iso={n.last_anchor_at} now={now} /> : "None"} context={n?.last_anchor_seq ? `Up to record ${n.last_anchor_seq}` : "Sealing runs nightly"} />
      </Kpis>

      <Section title="Latest records, linked" description="Each record carries the fingerprint of the one before it. Sealed records are marked.">
        {latest.data?.length ? (
          <div className="chain">
            {[...latest.data].reverse().map((e, i) => (
              <div key={e.seq} style={{ display: "flex" }}>
                {i > 0 ? <span className="chain-link" aria-hidden><Link2 size={14} strokeWidth={1.5} /></span> : null}
                <button type="button" className="chain-block" data-sealed={sealed.has(e.seq)} onClick={() => void openEntry(e)}>
                  <span className="t-micro t-muted">#{e.seq} · <Time iso={e.created_at} now={now} /></span>
                  <span className="t-small t-strong">{EVENTS[e.event_type] ?? e.event_type}</span>
                  <span className="t-mono t-muted">{e.entry_hash.slice(0, 10)}</span>
                  {sealed.has(e.seq) ? <span className="t-micro" style={{ color: "var(--good)" }}>Sealed</span> : null}
                </button>
              </div>
            ))}
          </div>
        ) : <div className="card"><SkeletonRows rows={2} /></div>}
      </Section>

      <Section title="Checks you can run">
        <div className="grid-2">
          <div className="card card-pad between" style={{ alignItems: "flex-start" }}>
            <div><h3>Re-run every decision</h3><p className="t-small t-muted">Replays each decision from its record and confirms the result is identical.</p></div>
            <button type="button" className="btn" disabled={busy !== null} onClick={() => run("replay", () => api("/v1/audit/replay-all", { method: "POST" }), "Every decision was re-run")}>{busy === "replay" ? "Running…" : "Re-run"}</button>
          </div>
          <div className="card card-pad between" style={{ alignItems: "flex-start" }}>
            <div><h3>Seal records now</h3><p className="t-small t-muted">Signs the current state of the record. This also happens every night.</p></div>
            <button type="button" className="btn" disabled={busy !== null} onClick={() => run("seal", () => api("/v1/audit/anchor", { method: "POST" }), "Records sealed")}>{busy === "seal" ? "Sealing…" : "Seal"}</button>
          </div>
        </div>
      </Section>

      <Section title="History" description="Every recorded action, newest first.">
        <ContextBar>
          <select className="control" aria-label="Event" value={eventType} onChange={(e) => { setEventType(e.target.value); setBefore(null); }}>
            <option value="">All events</option>
            {Object.entries(EVENTS).map(([k, t]) => <option key={k} value={k}>{t}</option>)}
          </select>
        </ContextBar>
        <div className="card">
          <DataTable
            caption="Record history"
            rows={entries.data}
            loading={entries.loading}
            refreshing={entries.refreshing}
            rowKey={(e) => String(e.seq)}
            onRowClick={(e) => void openEntry(e)}
            empty={{ title: "No records of this kind" }}
            footer={entries.data ? <>
              {before !== null ? <button type="button" className="btn btn-compact" onClick={() => setBefore(null)}>Newest</button> : null}
              {entries.data.length === 50 ? <button type="button" className="btn btn-compact" onClick={() => setBefore(entries.data!.at(-1)!.seq)}>Load older</button> : null}
            </> : null}
            columns={[
              { key: "e", header: "Event", render: (e) => <span className="cell-primary">{EVENTS[e.event_type] ?? e.event_type}</span> },
              { key: "r", header: "Reference", render: (e) => <span className="t-small t-muted">#{e.seq} · {e.ref}</span> },
              { key: "w", header: "By", render: (e) => who(e.actor) },
              { key: "t", header: "When", render: (e) => <Time iso={e.created_at} now={now} /> },
              { key: "o", header: "", render: () => <ChevronRight size={16} strokeWidth={1.5} className="t-muted" aria-hidden /> },
            ]}
          />
        </div>
      </Section>

      {open ? (
        <Drawer title={EVENTS[open.entry.event_type] ?? open.entry.event_type} eyebrow={`Record #${open.entry.seq}`} onClose={() => setOpen(null)}>
          <Section title="Summary">
            <dl className="kv">
              <dt>What</dt><dd>{EVENTS[open.entry.event_type] ?? open.entry.event_type}</dd>
              <dt>By</dt><dd>{who(open.entry.actor)}</dd>
              <dt>When</dt><dd>{absolute(open.entry.created_at)}</dd>
              <dt>Reference</dt><dd>{open.entry.ref}</dd>
            </dl>
          </Section>
          <details className="disclosure">
            <summary><ChevronRight size={16} strokeWidth={1.5} aria-hidden />Technical record</summary>
            <div className="disclosure-body">
              <dl className="kv">
                <dt>Fingerprint</dt><dd className="t-mono">{open.entry.entry_hash}</dd>
                <dt>Links to</dt><dd className="t-mono">{open.entry.prev_hash}</dd>
                <dt>Content hash</dt><dd className="t-mono">{open.entry.payload_hash}</dd>
              </dl>
              <pre className="json">{JSON.stringify(open.payload, null, 2)}</pre>
            </div>
          </details>
        </Drawer>
      ) : null}
    </div>
  );
}
