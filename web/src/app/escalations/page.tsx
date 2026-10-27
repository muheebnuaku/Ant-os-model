"use client";

import { ArrowUpRight, Check, Inbox } from "lucide-react";
import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";

import { DetailEmpty, ListItem, ListSkeleton, Pane, SplitView, useSelectHref } from "@/components/console";
import {
  Badge,
  ErrorNotice,
  Kpi,
  Kpis,
  Notice,
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
  const [selectedId] = useQueryState("id", "");
  const hrefFor = useSelectHref("id");
  const [busy, setBusy] = useState(false);
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
  const selected = items.find((e) => e.escalation_id === selectedId) ?? null;

  async function act(e: Escalation, path: "acknowledge" | "resolve", body: unknown = {}) {
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/escalations/${e.escalation_id}/${path}`, { method: "POST", body });
      toast(path === "acknowledge" ? `Review acknowledged: ${e.objective}` : `Review resolved: ${e.objective}`);
      all.reload();
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <SplitView hasSelection={!!selected}>
      <Pane kind="list" title="Review queue" count={all.data ? rows.length : null}
        toolbar={<>
          <Tabs<Status> value={status} onChange={setStatus} tabs={[
            { value: "open", label: "New", count: mine.filter((e) => e.status === "open").length },
            { value: "acknowledged", label: "In progress", count: mine.filter((e) => e.status === "acknowledged").length },
            { value: "resolved", label: "Resolved" },
            { value: "all", label: "All" },
          ]} />
          <select className="control" aria-label="Sector" value={sector} onChange={(e) => setSector(e.target.value)}>
            <option value="">All sectors</option>
            {SECTOR_ORDER.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </select>
          <select className="control" aria-label="Priority" value={priority} onChange={(e) => setPriority(e.target.value)}>
            <option value="">Any priority</option>
            {["critical", "high", "medium", "low"].map((p) => <option key={p} value={p}>{humanize(p)}</option>)}
          </select>
          {reviewer ? (
            <Segmented label="Scope" value={scope} onChange={setScope} options={[{ value: "mine", label: "Mine" }, { value: "all", label: "Everyone" }]} />
          ) : null}
        </>}>
        <ErrorNotice error={all.error} />
        {!all.data ? <ListSkeleton /> : rows.length ? (
          <ul className="list" aria-label="Reviews">
            {rows.map((e) => (
              <ListItem key={e.escalation_id} href={hrefFor(e.escalation_id)} selected={e.escalation_id === selectedId}
                title={e.objective}
                aside={<DueText e={e} now={now} />}
                meta={<>
                  <Badge status={e.priority} dot />
                  <span>{humanize(e.sector)}</span>
                  <span>{humanize(e.assigned_role)}</span>
                  {status === "all" ? <Badge status={e.status} dot /> : null}
                </>}
              />
            ))}
          </ul>
        ) : <p className="list-empty">Nothing here. No reviews match these filters.</p>}
      </Pane>

      {selected ? (
        <ReviewDetail key={selected.escalation_id} e={selected} now={now} busy={busy} error={error}
          back={hrefFor(null)} onAct={act} />
      ) : (
        <Pane kind="detail" title="Queue overview" label="Queue overview">
          <div className="pane-detail-inner">
            <Kpis count={4}>
              <Kpi label="New" value={mine.filter((e) => e.status === "open").length} context="Not yet picked up" />
              <Kpi label="In progress" value={mine.filter((e) => e.status === "acknowledged").length} context="Picked up, not resolved" />
              <Kpi label="Due within 30 min" value={atRisk.length} context={atRisk.length ? <Badge status="medium">Act soon</Badge> : "None"} />
              <Kpi label="Overdue" value={overdue.length} context={overdue.length ? <Badge status="overdue">Past deadline</Badge> : "None"} />
            </Kpis>
            <DetailEmpty icon={Inbox} title="Select a review">
              Reviews are ordered by deadline, soonest first. Pick one to see why it was sent to a person and to act on it.
            </DetailEmpty>
          </div>
        </Pane>
      )}
    </SplitView>
  );
}

function ReviewDetail({ e, now, busy, error, back, onAct }: {
  e: Escalation; now: number; busy: boolean; error: Error | null; back: string;
  onAct: (e: Escalation, path: "acknowledge" | "resolve", body?: unknown) => Promise<void>;
}) {
  const [note, setNote] = useState("");
  useEffect(() => setNote(""), [e.status]);
  const open = e.status !== "resolved";

  return (
    <Pane kind="detail" back={back} label="Review"
      title={<><Badge status={e.priority} dot /> <span className="count">{humanize(e.sector)}</span></>}
      actions={e.audit_ref ? (
        <Link className="btn btn-compact" href={`/decisions?ref=${encodeURIComponent(e.audit_ref)}`}>
          Open decision <ArrowUpRight size={14} strokeWidth={1.5} aria-hidden />
        </Link>
      ) : null}>
      <div className="pane-detail-inner">
        <header className="detail-head">
          <span className="eyebrow"><Badge status={e.status} dot /> Assigned to {humanize(e.assigned_role)} · raised {relative(e.created_at, now)}</span>
          <h2>{e.objective}</h2>
        </header>

        <div className="card card-pad stack">
          <span className="kpi-label">Deadline</span>
          <Deadline e={e} now={now} />
        </div>

        <Section title="Why a person must review this">
          <div className="card card-pad">
            <ul className="summary-list">
              {e.reasons.map((r) => <li key={r.code}><Badge tone="warning">{humanize(r.code)}</Badge><span>{r.message}</span></li>)}
            </ul>
          </div>
        </Section>

        <ErrorNotice error={error} />

        {open ? (
          <Section title="Act on this review">
            <div className="card card-pad stack">
              {e.status === "open" ? (
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <span className="t-secondary">Let the team know you are handling it.</span>
                  <button type="button" className="btn btn-compact" disabled={busy} onClick={() => void onAct(e, "acknowledge")}>
                    <Check size={14} strokeWidth={1.5} aria-hidden />Acknowledge
                  </button>
                </div>
              ) : null}
              <form className="stack" onSubmit={(ev) => { ev.preventDefault(); void onAct(e, "resolve", { note }); }}>
                <label className="field">
                  <span>Resolution note</span>
                  <textarea className="control" value={note} onChange={(ev) => setNote(ev.target.value)} required />
                  <span className="field-hint">This note becomes part of the permanent record.</span>
                </label>
                <div className="row" style={{ justifyContent: "flex-end" }}>
                  <button type="submit" className="btn btn-primary btn-compact" disabled={!note.trim() || busy} aria-busy={busy}>Resolve review</button>
                </div>
              </form>
            </div>
          </Section>
        ) : (
          <Notice tone="good">
            Resolved by {who(e.resolved_by)} {e.resolved_at ? <span title={absolute(e.resolved_at)}>{relative(e.resolved_at, now)}</span> : null}.
            {e.resolution ? <> Note: “{e.resolution}”</> : null}
          </Notice>
        )}
      </div>
    </Pane>
  );
}

function DueText({ e, now }: { e: Escalation; now: number }) {
  if (e.status === "resolved") return <span>Resolved</span>;
  const late = new Date(e.due_at).getTime() < now;
  return (
    <span title={absolute(e.due_at)} style={late ? { color: "var(--critical)", fontWeight: 600 } : undefined}>
      {late ? `${relative(e.due_at, now).replace(" ago", "")} late` : `${relative(e.due_at, now).replace("in ", "")} left`}
    </span>
  );
}

function Deadline({ e, now }: { e: Escalation; now: number }) {
  if (e.status === "resolved") return <span className="t-muted" title={absolute(e.resolved_at)}>Resolved {e.resolved_at ? relative(e.resolved_at, now) : ""}</span>;
  const due = new Date(e.due_at).getTime();
  const created = new Date(e.created_at).getTime();
  const used = Math.min(1, Math.max(0, (now - created) / Math.max(1, due - created)));
  const late = due < now;
  return (
    <div className="stack-sm" style={{ gap: 6 }}>
      <span title={absolute(e.due_at)} style={late ? { color: "var(--critical)", fontWeight: 600 } : undefined}>
        {late ? `Overdue by ${relative(e.due_at, now).replace(" ago", "")}` : `${relative(e.due_at, now).replace("in ", "")} left`} · due {absolute(e.due_at)}
      </span>
      <span className="meter" data-tone={late ? "critical" : used > 0.75 ? "warning" : undefined} aria-hidden><span style={{ width: `${used * 100}%` }} /></span>
    </div>
  );
}
