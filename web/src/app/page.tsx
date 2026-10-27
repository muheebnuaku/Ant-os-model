"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { Suspense, useMemo } from "react";

import { ActivityHeatmap, HeatLegend, Sparkline } from "@/components/charts";
import { ListItem, ListSkeleton, Pane, SplitView, useSelectHref } from "@/components/console";
import { DataTable } from "@/components/DataTable";
import {
  Badge,
  Delta,
  EmptyState,
  ErrorNotice,
  Kpi,
  Kpis,
  Meter,
  Notice,
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
  const now = useNow(30_000);
  const [win, setWin] = useQueryState("window", "24");
  const hours = WINDOWS.some((w) => w.value === win) ? Number(win) : 24;
  const allowed = can(CAN.situation);
  const nation = me?.nation_id ?? "GH";
  const room = useApi<SituationRoom>(allowed ? "/v1/core/situation-room" : null, {
    pollMs: 30_000,
    body: { nation_id: nation, time_window_hours: hours },
  });
  const [openSector, setSectorParam] = useQueryState("sector", "");
  const setSector = (id: string | null) => setSectorParam(id ?? "");
  const sectorHref = useSelectHref("sector");

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
        <header className="page-header"><div><h1>Briefing</h1><p>The national picture is available to sector leads, analysts and regulators.</p></div></header>
        <EmptyState title="Your work is in the review queue" action={<Link className="btn" href="/escalations">Open the review queue</Link>} />
      </div>
    );
  }

  const p = data?.pulse;
  const waiting = p ? Object.values(p.open_escalations).reduce((a, b) => a + b, 0) : 0;
  const overdue = queue.filter((e) => new Date(e.due_at).getTime() < now).length;
  const diff = p ? p.decisions_in_window - p.decisions_previous_window : 0;

  return (
    <SplitView hasSelection={!!openSector} stackOnMobile>
      <Pane kind="list" title="Briefing" label="Needs action and sectors"
        actions={can(CAN.decide) ? <Link className="btn btn-primary btn-compact" href="/decisions/new"><Plus size={14} strokeWidth={1.5} aria-hidden />New</Link> : null}
        toolbar={<Segmented label="Time window" options={WINDOWS} value={String(hours)} onChange={setWin} />}>
        {!data ? <ListSkeleton /> : (
          <>
            <div className="list-group-label"><span>Needs action</span><span>{queue.length}</span></div>
            {queue.length ? (
              <ul className="list" aria-label="Open reviews">
                {queue.map((e) => (
                  <ListItem key={e.escalation_id} href={`/escalations?id=${encodeURIComponent(e.escalation_id)}`} selected={false}
                    title={e.objective}
                    aside={<RemainingText e={e} now={now} />}
                    meta={<><Badge status={e.priority} dot /><span>{humanize(e.sector)}</span><span>{humanize(e.assigned_role)}</span></>}
                  />
                ))}
              </ul>
            ) : <p className="list-empty">Nothing is waiting. New reviews appear here as soon as they are raised.</p>}
            <div className="list-group-label"><span>Sectors</span><span>{sectors.length}</span></div>
            <ul className="list" aria-label="Sectors">
              {sectors.map((s) => {
                const reviews = Object.values(s.open_escalations).reduce((a, b) => a + b, 0);
                return (
                  <ListItem key={s.sector} href={sectorHref(s.sector)} selected={s.sector === openSector}
                    title={sectorName(s.sector_name)}
                    aside={reviews ? `${reviews} review${reviews > 1 ? "s" : ""}` : null}
                    meta={<><Badge status={s.status} dot />{s.mean_freshness === null ? <span>No data</span> : <Meter value={s.mean_freshness} width={64} />}</>}
                  />
                );
              })}
            </ul>
          </>
        )}
      </Pane>

      {openSector && data ? (
        <SectorPanel s={data.sectors.find((x) => x.sector === openSector)} queue={queue.filter((e) => e.sector === openSector)}
          now={now} back={sectorHref(null)} />
      ) : (
        <Pane kind="detail" label="National overview"
          title={`National picture · ${nation === "GH" ? "Ghana" : nation}`}
          actions={data ? <span className="t-small t-muted row" style={{ gap: 6 }}><span className="live-dot" aria-hidden /> Updated <Time iso={data.generated_at} now={now} /></span> : null}>
          <div className="overview">
            <ErrorNotice error={room.error} />
            {!data ? <div className="card"><SkeletonRows rows={6} /></div> : (
              <div className="overview refreshable" data-refreshing={room.refreshing}>
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

                <Section title="Activity by sector" description={`Last ${windowText(hours)}. Each cell shows the weakest result among that period's decisions.`} actions={<HeatLegend />}>
                  <div className="card card-pad">
                    <ActivityHeatmap bucketMinutes={data.bucket_minutes} onRowClick={setSector} showLegend={false}
                      rows={sectors.map((s) => ({ key: s.sector, label: sectorName(s.sector_name), buckets: s.timeline }))} />
                  </div>
                </Section>
              </div>
            )}
          </div>
        </Pane>
      )}
    </SplitView>
  );
}

function RemainingText({ e, now }: { e: Escalation; now: number }) {
  const late = new Date(e.due_at).getTime() < now;
  return (
    <span title={absolute(e.due_at)} style={late ? { color: "var(--critical)", fontWeight: 600 } : undefined}>
      {late ? `${relative(e.due_at, now).replace(" ago", "")} late` : `${relative(e.due_at, now).replace("in ", "")} left`}
    </span>
  );
}

function SectorPanel({ s, queue, now, back }: { s: SectorSummary | undefined; queue: Escalation[]; now: number; back: string }) {
  const decisions = useApi<DecisionSummary[]>(s ? `/v1/decisions?sector=${s.sector}&limit=8` : null);
  if (!s) return <Pane kind="detail" title="Sector" back={back}><EmptyState title="This sector is not configured" /></Pane>;
  return (
    <Pane kind="detail" back={back} label={s.sector_name} title={<>Sector <span className="count">{humanize(s.sector)}</span></>}
      actions={<Link className="btn btn-compact" href={`/decisions?sector=${s.sector}`}>All decisions</Link>}>
    <div className="pane-detail-inner">
      <header className="detail-head">
        <span className="eyebrow"><Badge status={s.status} dot /> 24-hour economy priority: {s.priority_24hae.toLowerCase()}</span>
        <h2>{s.sector_name}</h2>
      </header>
      <div className="kpis" style={{ ["--n" as string]: 3 }}>
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
              <Link key={e.escalation_id} href={`/escalations?id=${encodeURIComponent(e.escalation_id)}`} className="row" style={{ color: "var(--text)" }}>
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
              { key: "d", header: "Decision", render: (d) => <Link href={`/decisions?ref=${encodeURIComponent(d.audit_ref)}`} className="cell-primary">{d.objective}</Link> },
              { key: "r", header: "Result", render: (d) => <Badge status={d.validation_state} dot /> },
              { key: "w", header: "When", render: (d) => <Time iso={d.created_at} now={now} /> },
            ]} />
        </div>
      </Section>
      {queue.length || s.status !== "no_data" ? null : <Notice tone="neutral">Nothing has been reported for this sector in the selected window. Nothing is estimated.</Notice>}
    </div>
    </Pane>
  );
}
