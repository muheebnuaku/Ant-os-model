"use client";

import Link from "next/link";
import { Suspense, useMemo, useState } from "react";

import { DataTable } from "@/components/DataTable";
import {
  Badge,
  CancelButton,
  ContextBar,
  Dialog,
  ErrorNotice,
  Kpi,
  Kpis,
  PageHeader,
  Section,
  Segmented,
  SECTOR_ORDER,
  Tabs,
  absolute,
  humanize,
  relative,
  who,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useApi, useNow, useQueryState } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { useToast } from "@/lib/toast";
import type { Escalation } from "@/lib/types";

type Status = "open" | "acknowledged" | "resolved" | "all";
const AT_RISK_MS = 30 * 60_000;

export default function ReviewQueuePage() {
  return <Suspense fallback={null}><ReviewQueue /></Suspense>;
}

function ReviewQueue() {
  const { me, can } = useSession();
  const toast = useToast();
  const now = useNow(15_000);
  const all = useApi<Escalation[]>("/v1/escalations", { pollMs: 20_000 });
  const [status, setStatus] = useQueryState<Status>("status", "open");
  const [sector, setSector] = useQueryState("sector", "");
  const [priority, setPriority] = useQueryState("priority", "");
  const [scope, setScope] = useQueryState<"mine" | "all">("scope", "mine");
  const [resolving, setResolving] = useState<Escalation | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const reviewer = can(["override_reviews"]);

  const items = all.data ?? [];
  const mine = useMemo(() => items.filter((e) => !reviewer || scope === "all" || me?.roles.includes(e.assigned_role)), [items, reviewer, scope, me]);
  const rows = useMemo(
    () => mine
      .filter((e) => (status === "all" || e.status === status) && (!sector || e.sector === sector) && (!priority || e.priority === priority))
      .sort((a, b) => a.due_at.localeCompare(b.due_at)),
    [mine, status, sector, priority],
  );
  const unresolved = mine.filter((e) => e.status !== "resolved");
  const overdue = unresolved.filter((e) => new Date(e.due_at).getTime() < now);
  const atRisk = unresolved.filter((e) => { const d = new Date(e.due_at).getTime() - now; return d >= 0 && d <= AT_RISK_MS; });

  async function act(e: Escalation, path: "acknowledge" | "resolve", body: unknown = {}) {
    setBusy(e.escalation_id);
    setError(null);
    try {
      await api(`/v1/escalations/${e.escalation_id}/${path}`, { method: "POST", body });
      toast(path === "acknowledge" ? `Review acknowledged: ${e.objective}` : `Review resolved: ${e.objective}`);
      setResolving(null);
      setNote("");
      all.reload();
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="page">
      <PageHeader title="Review queue" description="Decisions waiting for a person." />

      <div className="stack">
        <Tabs<Status> value={status} onChange={setStatus} tabs={[
          { value: "open", label: `New (${mine.filter((e) => e.status === "open").length})` },
          { value: "acknowledged", label: `In progress (${mine.filter((e) => e.status === "acknowledged").length})` },
          { value: "resolved", label: "Resolved" },
          { value: "all", label: "All" },
        ]} />
        <ContextBar>
          <select className="control" aria-label="Sector" value={sector} onChange={(e) => setSector(e.target.value)}>
            <option value="">All sectors</option>
            {SECTOR_ORDER.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </select>
          <select className="control" aria-label="Priority" value={priority} onChange={(e) => setPriority(e.target.value)}>
            <option value="">All priorities</option>
            {["critical", "high", "medium", "low"].map((p) => <option key={p} value={p}>{humanize(p)}</option>)}
          </select>
          {reviewer ? (
            <Segmented label="Scope" value={scope} onChange={setScope} options={[{ value: "mine", label: "Assigned to me" }, { value: "all", label: "All" }]} />
          ) : null}
        </ContextBar>
      </div>

      <Kpis count={4}>
        <Kpi label="New" value={mine.filter((e) => e.status === "open").length} context="Not yet picked up" />
        <Kpi label="In progress" value={mine.filter((e) => e.status === "acknowledged").length} context="Picked up, not resolved" />
        <Kpi label="Due within 30 min" value={atRisk.length} context={atRisk.length ? <Badge status="medium">Act soon</Badge> : "None"} />
        <Kpi label="Overdue" value={overdue.length} context={overdue.length ? <Badge status="overdue">Past deadline</Badge> : "None"} />
      </Kpis>

      <ErrorNotice error={all.error ?? error} />

      <Section title={status === "all" ? "All reviews" : status === "open" ? "New reviews" : status === "acknowledged" ? "Reviews in progress" : "Resolved reviews"}
        description="Soonest deadline first.">
        <div className="card">
          <DataTable
            caption="Reviews"
            rows={all.data ? rows : null}
            loading={all.loading}
            refreshing={all.refreshing}
            rowKey={(e) => e.escalation_id}
            empty={{ title: "Nothing here", description: "No reviews match these filters." }}
            columns={[
              { key: "p", header: "Priority", render: (e) => <Badge status={e.priority} /> },
              { key: "d", header: "Decision and reasons", render: (e) => (
                <>
                  <div className="cell-primary">{e.audit_ref ? <Link href={`/decisions/${e.audit_ref}`} style={{ color: "inherit" }}>{e.objective}</Link> : e.objective}</div>
                  <div className="cell-secondary">{e.reasons.map((r) => r.message).join(" · ")}</div>
                </>
              ) },
              { key: "s", header: "Sector", render: (e) => humanize(e.sector) },
              { key: "r", header: "Assigned role", render: (e) => humanize(e.assigned_role) },
              { key: "t", header: "Deadline", render: (e) => <Deadline e={e} now={now} /> },
              { key: "st", header: "Status", render: (e) => <Badge status={e.status} /> },
              { key: "a", header: "Actions", render: (e) => e.status === "resolved" ? (
                <span className="t-small t-muted" title={e.resolution ?? ""}>By {who(e.resolved_by)}</span>
              ) : (
                <div className="row" style={{ flexWrap: "nowrap" }}>
                  {e.status === "open" ? (
                    <button type="button" className="btn btn-compact" disabled={busy === e.escalation_id} onClick={() => void act(e, "acknowledge")}>Acknowledge</button>
                  ) : null}
                  <button type="button" className="btn btn-compact" onClick={() => { setResolving(e); setNote(""); }}>Resolve…</button>
                </div>
              ) },
            ]}
          />
        </div>
      </Section>

      {resolving ? (
        <Dialog title="Resolve review" onClose={() => setResolving(null)}>
          <p className="t-secondary">{resolving.objective}</p>
          <form className="stack" onSubmit={(ev) => { ev.preventDefault(); void act(resolving, "resolve", { note }); }}>
            <label className="field">
              <span>Resolution note</span>
              <textarea className="control" value={note} onChange={(ev) => setNote(ev.target.value)} required autoFocus />
              <span className="field-hint">This note becomes part of the permanent record.</span>
            </label>
            <div className="dialog-actions">
              <CancelButton />
              <button type="submit" className="btn btn-primary" disabled={!note.trim() || busy === resolving.escalation_id}
                aria-busy={busy === resolving.escalation_id}>Resolve</button>
            </div>
          </form>
        </Dialog>
      ) : null}
    </div>
  );
}

function Deadline({ e, now }: { e: Escalation; now: number }) {
  if (e.status === "resolved") return <span className="t-muted" title={absolute(e.resolved_at)}>Resolved {e.resolved_at ? relative(e.resolved_at, now) : ""}</span>;
  const due = new Date(e.due_at).getTime();
  const created = new Date(e.created_at).getTime();
  const used = Math.min(1, Math.max(0, (now - created) / Math.max(1, due - created)));
  const late = due < now;
  return (
    <div className="stack-sm" style={{ gap: 4, minWidth: 128 }}>
      <span title={absolute(e.due_at)} style={late ? { color: "var(--critical)", fontWeight: 600 } : undefined}>
        {late ? `Overdue by ${relative(e.due_at, now).replace(" ago", "")}` : `${relative(e.due_at, now).replace("in ", "")} left`}
      </span>
      <span className="meter" data-tone={late ? "critical" : used > 0.75 ? "warning" : undefined} aria-hidden><span style={{ width: `${used * 100}%` }} /></span>
    </div>
  );
}
