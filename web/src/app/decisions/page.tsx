"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { DataTable } from "@/components/DataTable";
import { Badge, ContextBar, ErrorNotice, Kpi, Kpis, Meter, PageHeader, Section, Time, humanize, pct, sectorName } from "@/components/ui";
import { useApi, useNow, useQueryState } from "@/lib/hooks";
import { CAN, useSession } from "@/lib/session";
import type { DecisionSummary, Sector } from "@/lib/types";

const RANGES = [
  { value: "1", label: "Last 24 hours" },
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
];

export default function DecisionsPage() {
  return <Suspense fallback={null}><Decisions /></Suspense>;
}

function Decisions() {
  const { can } = useSession();
  const router = useRouter();
  const now = useNow(60_000);
  const [q, setQ] = useQueryState("q", "");
  const [query, setQuery] = useState(q);
  const [sector, setSector] = useQueryState("sector", "");
  const [result, setResult] = useQueryState("result", "");
  const [outcome, setOutcome] = useQueryState("outcome", "");
  const [days, setDays] = useQueryState("range", "30");
  // Typing updates the list at once; the URL follows after a short pause.
  useEffect(() => {
    const id = setTimeout(() => { if (query !== q) setQ(query); }, 400);
    return () => clearTimeout(id);
  }, [query, q, setQ]);
  const sectors = useApi<Sector[]>("/v1/sectors");
  // Rounded to the hour so the request (and its cached result) is stable between visits.
  const since = useMemo(() => {
    const hour = Math.floor(Date.now() / 3_600_000) * 3_600_000;
    return new Date(hour - Number(days) * 86_400_000).toISOString();
  }, [days]);
  const list = useApi<DecisionSummary[]>(
    `/v1/decisions?limit=500&since=${encodeURIComponent(since)}${sector ? `&sector=${sector}` : ""}`,
    { pollMs: 60_000 },
  );

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (list.data ?? []).filter((d) =>
      (!q || `${d.objective ?? ""} ${d.audit_ref}`.toLowerCase().includes(q))
      && (!result || d.validation_state === result)
      && (outcome !== "ready" || d.allowed_for_action)
      && (outcome !== "person" || d.human_escalation_required)
      && (outcome !== "hold" || (!d.allowed_for_action && !d.human_escalation_required)));
  }, [list.data, query, result, outcome]);

  return (
    <div className="page">
      <PageHeader
        title="Decisions"
        description="Every decision ANT-OS has evaluated."
        actions={can(CAN.decide) ? <Link className="btn btn-primary" href="/decisions/new">New decision</Link> : null}
      />

      <ContextBar>
        <label className="search-field">
          <Search size={16} strokeWidth={1.5} aria-hidden />
          <input className="control" type="search" placeholder="Search decisions" aria-label="Search decisions" value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
        <select className="control" aria-label="Sector" value={sector} onChange={(e) => setSector(e.target.value)}>
          <option value="">All sectors</option>
          {sectors.data?.map((s) => <option key={s.sector_id} value={s.sector_id}>{sectorName(s.sector_name)}</option>)}
        </select>
        <select className="control" aria-label="Result" value={result} onChange={(e) => setResult(e.target.value)}>
          <option value="">All results</option>
          {["trusted", "provisional", "conflicted", "blocked", "decayed"].map((r) => <option key={r} value={r}>{humanize(r)}</option>)}
        </select>
        <select className="control" aria-label="Outcome" value={outcome} onChange={(e) => setOutcome(e.target.value)}>
          <option value="">All outcomes</option>
          <option value="ready">Cleared to act</option>
          <option value="person">Needs a person</option>
          <option value="hold">On hold</option>
        </select>
        <select className="control" aria-label="Date range" value={days} onChange={(e) => setDays(e.target.value)}>
          {RANGES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
        </select>
      </ContextBar>

      <Kpis count={4}>
        <Kpi label="Total in range" value={rows.length} context={RANGES.find((r) => r.value === days)?.label} />
        <Kpi label="Cleared to act" value={rows.filter((d) => d.allowed_for_action).length}
          context={rows.length ? `${pct(rows.filter((d) => d.allowed_for_action).length / rows.length)} of decisions` : "No decisions"} />
        <Kpi label="Needs a person" value={rows.filter((d) => d.human_escalation_required).length} context="Sent for human review" />
        <Kpi label="Blocked" value={rows.filter((d) => d.validation_state === "blocked").length} context="Evidence unsafe to act on" />
      </Kpis>

      <ErrorNotice error={list.error} />

      <Section title="All decisions" description="Newest first. Select a row for the full explanation.">
        <div className="card">
          <DataTable
            caption="Decisions"
            rows={list.data ? rows : null}
            loading={list.loading}
            refreshing={list.refreshing}
            rowKey={(d) => d.audit_ref}
            onRowClick={(d) => router.push(`/decisions/${d.audit_ref}`)}
            empty={{ title: "No decisions match", description: "Try a wider date range or fewer filters." }}
            columns={[
              { key: "d", header: "Decision", render: (d) => <><Link href={`/decisions/${d.audit_ref}`} className="cell-primary" style={{ color: "var(--text)" }}>{d.objective ?? d.decision_id}</Link><div className="cell-secondary">{humanize(d.sector)}</div></> },
              { key: "r", header: "Evidence result", render: (d) => <Badge status={d.validation_state} dot /> },
              { key: "c", header: "Confidence", render: (d) => <Meter value={d.confidence} width={48} /> },
              { key: "a", header: "Advised action", render: (d) => <Badge status={d.action} dot /> },
              { key: "h", header: "Human review", render: (d) => (d.human_escalation_required ? "Required" : "Not required") },
              { key: "w", header: "Evaluated", render: (d) => <Time iso={d.created_at} now={now} /> },
            ]}
          />
        </div>
      </Section>
    </div>
  );
}
