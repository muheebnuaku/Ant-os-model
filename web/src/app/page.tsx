"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo } from "react";

import { ActivityHeatmap, HeatLegend, Sparkline } from "@/components/charts";
import { DataTable } from "@/components/DataTable";
import {
  Badge,
  ContextBar,
  Delta,
  Drawer,
  EmptyState,
  ErrorNotice,
  Kpi,
  Kpis,
  Meter,
  Notice,
  PageHeader,
  Section,
  Segmented,
  SECTOR_ORDER,
  SkeletonRows,
  Time,
  absolute,
  humanize,
  pct,
  relative,
  sectorName,
  type Tone,
} from "@/components/ui";
import { useApi, useNow, useQueryState } from "@/lib/hooks";
import { CAN, useSession } from "@/lib/session";
import type { DecisionSummary, Escalation, SectorSummary, SituationRoom } from "@/lib/types";

const WINDOWS = [
  { value: "6", label: "6 h" },
  { value: "24", label: "24 h" },
  { value: "72", label: "3 days" },
  { value: "168", label: "7 days" },
];

function windowText(h: number): string {
  return h < 24 ? `${h} hours` : h === 24 ? "24 hours" : `${h / 24} days`;
}

/** Up to three plain sentences, written by fixed rules from the data (§7.1.4). */
function situation(room: SituationRoom, queue: Escalation[], hours: number, now: number): { tone: Tone; text: string }[] {
  const out: { tone: Tone; text: string }[] = [];
  const overdue = queue.filter((e) => new Date(e.due_at).getTime() < now);
  const next = queue.find((e) => new Date(e.due_at).getTime() >= now);
  if (overdue.length) {
    const e = overdue[0]!;
    out.push({ tone: "critical", text: `${overdue.length} review${overdue.length > 1 ? "s are" : " is"} overdue. The oldest, in ${humanize(e.sector)}, was due ${relative(e.due_at, now)}.` });
  }
  if (next) {
    out.push({ tone: next.priority === "critical" ? "critical" : "warning", text: `${humanize(next.sector)} has a ${next.priority}-priority review due ${relative(next.due_at, now)}: ${next.objective}.` });
  }
  const silent = room.sectors.filter((s) => s.status === "no_data");
  if (silent.length && silent.length < room.sectors.length) {
    out.push({ tone: "neutral", text: `No data from ${silent.map((s) => sectorName(s.sector_name)).join(", ")} in the last ${windowText(hours)}.` });
  }
  if (!out.length) {
    out.push(room.sectors.every((s) => s.status === "no_data")
      ? { tone: "neutral", text: `No evidence or decisions in the last ${windowText(hours)}.` }
      : { tone: "good", text: "No reviews are waiting and every reporting sector is stable." });
  }
  return out.slice(0, 3);
}

export default function BriefingPage() {
  return (
    <Suspense fallback={<SkeletonRows rows={6} />}>
      <Briefing />
    </Suspense>
  );
}

function Briefing() {
  const { me, can } = useSession();
  const router = useRouter();
  const params = useSearchParams();
  const now = useNow(30_000);
  const [win, setWin] = useQueryState("window", "24");
  const hours = WINDOWS.some((w) => w.value === win) ? Number(win) : 24;
  const allowed = can(CAN.situation);
  const nation = me?.nation_id ?? "GH";
  const room = useApi<SituationRoom>(allowed ? "/v1/core/situation-room" : null, {
    pollMs: 30_000,
    body: { nation_id: nation, time_window_hours: hours },
  });
  const openSector = params.get("sector");
  const setSector = (id: string | null) => {
    const next = new URLSearchParams(params.toString());
    if (id) next.set("sector", id);
    else next.delete("sector");
    const qs = next.toString();
    router.replace(qs ? `/?${qs}` : "/", { scroll: false });
  };

  const data = room.data;
  const queue = useMemo(
    () => ((data?.active_escalations ?? []) as unknown as Escalation[]).slice().sort((a, b) => a.due_at.localeCompare(b.due_at)),
    [data],
  );
  const sectors = useMemo(
    () => (data ? [...data.sectors].sort((a, b) => SECTOR_ORDER.indexOf(a.sector) - SECTOR_ORDER.indexOf(b.sector)) : []),
    [data],
  );

  if (!allowed) {
    return (
      <div className="page">
        <PageHeader title="Briefing" description="The national picture is available to sector leads, analysts and regulators." />
        <EmptyState title="Your work is in the review queue" action={<Link className="btn" href="/escalations">Open the review queue</Link>} />
      </div>
    );
  }

  const p = data?.pulse;
  const waiting = p ? Object.values(p.open_escalations).reduce((a, b) => a + b, 0) : 0;
  const overdue = queue.filter((e) => new Date(e.due_at).getTime() < now).length;
  const diff = p ? p.decisions_in_window - p.decisions_previous_window : 0;

  return (
    <div className="page">
      <PageHeader
        title="Briefing"
        description={`National picture for ${nation === "GH" ? "Ghana" : nation}`}
        actions={can(CAN.decide) ? <Link className="btn btn-primary" href="/decisions/new">New decision</Link> : null}
      />

      <ContextBar
        meta={data ? <><span className="live-dot" aria-hidden /> Live · updated <Time iso={data.generated_at} now={now} /></> : null}
      >
        <Segmented label="Time window" options={WINDOWS} value={String(hours)} onChange={setWin} />
      </ContextBar>

      <ErrorNotice error={room.error} />

      {!data ? (
        <div className="card"><SkeletonRows rows={6} /></div>
      ) : (
        <div className="page refreshable" data-refreshing={room.refreshing}>
          <Kpis count={4}>
            <Kpi label="Waiting for review" value={waiting} context={`${p!.at_risk_escalations} due within 30 min`} />
            <Kpi label="Overdue reviews" value={overdue} context={overdue ? <Badge status="overdue">Past deadline</Badge> : "None past deadline"} />
            <Kpi label={`Decisions · last ${windowText(hours)}`} value={p!.decisions_in_window}
              context={<><Delta value={diff} /> vs previous {windowText(hours)}</>} />
            <Kpi label="Cleared to act" value={p!.decisions_in_window ? pct(p!.allowed_for_action / p!.decisions_in_window) : "No decisions"}
              context={`${p!.allowed_for_action} of ${p!.decisions_in_window} decisions`} />
          </Kpis>

          <Section title="Situation summary">
            <div className="card card-pad">
              <ul className="summary-list">
                {situation(data, queue, hours, now).map((s, i) => (
                  <li key={i}><Badge tone={s.tone} dot>{s.tone === "good" ? "Stable" : s.tone === "neutral" ? "Note" : s.tone === "critical" ? "Urgent" : "Soon"}</Badge><span>{s.text}</span></li>
                ))}
              </ul>
            </div>
          </Section>

          <div className="layout-main">
            <Section title="Needs action" description="Open reviews, soonest deadline first."
              actions={<Link className="btn btn-tertiary" href="/escalations">Open review queue</Link>}>
              <div className="card">
                <DataTable
                  caption="Open reviews"
                  rows={queue}
                  rowKey={(e) => e.escalation_id}
                  empty={{ title: "Nothing is waiting", description: "New reviews appear here as soon as they are raised." }}
                  onRowClick={(e) => router.push(e.audit_ref ? `/decisions/${e.audit_ref}` : "/escalations")}
                  columns={[
                    { key: "p", header: "Priority", render: (e) => <Badge status={e.priority} dot /> },
                    { key: "d", header: "Decision", render: (e) => <><div className="cell-primary">{e.objective}</div><div className="cell-secondary">{e.reasons[0]?.message}</div></> },
                    { key: "s", header: "Sector", render: (e) => humanize(e.sector) },
                    { key: "a", header: "Assigned to", render: (e) => humanize(e.assigned_role) },
                    { key: "t", header: "Time remaining", render: (e) => <Remaining e={e} now={now} /> },
                    { key: "o", header: "", render: (e) => <Link href={e.audit_ref ? `/decisions/${e.audit_ref}` : "/escalations"}>Open</Link> },
                  ]}
                />
              </div>
            </Section>

            <Section title="Sector status" description="All eight sectors, in fixed order.">
              <div className="card">
                <table className="table">
                  <caption className="sr-only">Sector status</caption>
                  <thead><tr><th>Sector</th><th>Status</th><th className="num">Freshness</th><th className="num">Reviews</th></tr></thead>
                  <tbody>
                    {sectors.map((s) => (
                      <tr key={s.sector} data-clickable="true" onClick={() => setSector(s.sector)}>
                        <td data-label="Sector"><button type="button" className="heat-label t-strong" onClick={() => setSector(s.sector)}>{sectorName(s.sector_name)}</button></td>
                        <td data-label="Status"><Badge status={s.status} dot /></td>
                        <td data-label="Freshness" className="num">{s.mean_freshness === null ? <span className="t-muted">No data</span> : <Meter value={s.mean_freshness} width={48} />}</td>
                        <td data-label="Reviews" className="num">{Object.values(s.open_escalations).reduce((a, b) => a + b, 0)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          </div>

          <Section title="Activity by sector" description={`Last ${windowText(hours)}. Each cell shows the weakest result among that period's decisions.`} actions={<HeatLegend />}>
            <div className="card card-pad">
              <ActivityHeatmap bucketMinutes={data.bucket_minutes} onRowClick={setSector} showLegend={false}
                rows={sectors.map((s) => ({ key: s.sector, label: sectorName(s.sector_name), buckets: s.timeline }))} />
            </div>
          </Section>

          {openSector ? (
            <SectorDrawer s={data.sectors.find((x) => x.sector === openSector)} queue={queue.filter((e) => e.sector === openSector)}
              now={now} onClose={() => setSector(null)} />
          ) : null}
        </div>
      )}
    </div>
  );
}

function Remaining({ e, now }: { e: Escalation; now: number }) {
  const due = new Date(e.due_at).getTime();
  const created = new Date(e.created_at).getTime();
  const used = Math.min(1, Math.max(0, (now - created) / Math.max(1, due - created)));
  const late = due < now;
  return (
    <div className="stack-sm" style={{ gap: 4, minWidth: 120 }}>
      <span className={late ? "t-strong" : undefined} style={late ? { color: "var(--critical)" } : undefined} title={absolute(e.due_at)}>
        {late ? `Overdue by ${relative(e.due_at, now).replace(" ago", "")}` : relative(e.due_at, now).replace("in ", "")}
      </span>
      <span className="meter" data-tone={late ? "critical" : used > 0.75 ? "warning" : undefined} aria-hidden><span style={{ width: `${used * 100}%` }} /></span>
    </div>
  );
}

function SectorDrawer({ s, queue, now, onClose }: { s: SectorSummary | undefined; queue: Escalation[]; now: number; onClose: () => void }) {
  const decisions = useApi<DecisionSummary[]>(s ? `/v1/decisions?sector=${s.sector}&limit=8` : null);
  if (!s) return <Drawer title="Unknown sector" onClose={onClose}><EmptyState title="This sector is not configured" /></Drawer>;
  return (
    <Drawer title={s.sector_name} eyebrow="Sector" status={<><Badge status={s.status} /><span className="t-small t-muted">24-hour economy priority: {s.priority_24hae.toLowerCase()}</span></>} onClose={onClose}>
      <div className="kpis" style={{ ["--n" as string]: 3, gap: 16 }}>
        <Kpi label="Evidence received" value={s.signals_in_window} />
        <Kpi label="Decisions" value={s.decisions_in_window} />
        <Kpi label="24HAE alignment" value={s.hae_alignment_mean === null ? <span className="t-small t-muted">Not assessed</span> : pct(s.hae_alignment_mean)} />
      </div>
      <Section title="Evidence received over time">
        <Sparkline values={s.timeline.map((b) => b.signals)} starts={s.timeline.map((b) => b.start)} what="Evidence received" height={48} />
      </Section>
      <Section title="Latest readings">
        <div className="card">
          <DataTable caption="Latest readings" rows={s.signal_types} rowKey={(t) => t.signal_type}
            empty={{ title: "No data", description: "No evidence in this window." }}
            columns={[
              { key: "t", header: "Signal", render: (t) => <span className="cell-primary">{humanize(t.signal_type)}</span> },
              { key: "s", header: "Source", render: (t) => humanize(t.source_id) },
              { key: "o", header: "Observed", render: (t) => <Time iso={t.timestamp} now={now} /> },
              { key: "f", header: "Freshness", numeric: true, render: (t) => <Meter value={t.freshness} /> },
            ]} />
        </div>
      </Section>
      <Section title="Open reviews">
        {queue.length ? (
          <div className="stack-sm">
            {queue.map((e) => (
              <Link key={e.escalation_id} href={e.audit_ref ? `/decisions/${e.audit_ref}` : "/escalations"} className="row" style={{ color: "var(--text)" }}>
                <Badge status={e.priority} /><span>{e.objective}</span><span className="t-small t-muted">· due {relative(e.due_at, now)}</span>
              </Link>
            ))}
          </div>
        ) : <p className="t-small t-muted">No open reviews.</p>}
      </Section>
      <Section title="Recent decisions">
        <div className="card">
          <DataTable caption="Recent decisions" rows={decisions.data} loading={decisions.loading} rowKey={(d) => d.audit_ref}
            empty={{ title: "No decisions yet" }}
            columns={[
              { key: "d", header: "Decision", render: (d) => <Link href={`/decisions/${d.audit_ref}`} className="cell-primary">{d.objective}</Link> },
              { key: "r", header: "Result", render: (d) => <Badge status={d.validation_state} dot /> },
              { key: "w", header: "When", render: (d) => <Time iso={d.created_at} now={now} /> },
            ]} />
        </div>
      </Section>
      {queue.length || s.status !== "no_data" ? null : <Notice tone="neutral">Nothing has been reported for this sector in the selected window. Nothing is estimated.</Notice>}
    </Drawer>
  );
}
