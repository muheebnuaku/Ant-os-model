"use client";

import { Suspense, useEffect, useState } from "react";

import { DataTable } from "@/components/DataTable";
import { Badge, ContextBar, ErrorNotice, Kpi, Kpis, Meter, PageHeader, Section, Time, humanize, pct, sectorName } from "@/components/ui";
import { useApi, useNow, useQueryState } from "@/lib/hooks";
import type { Sector, SignalsResponse } from "@/lib/types";

const SOURCE_KIND: Record<string, string> = {
  formal_institution: "Official institution", api_feed: "Automated feed", satellite: "Satellite",
  informal_operator: "Informal operator", community_source: "Community report", manual_entry: "Entered by hand",
};

const WINDOWS = [
  { value: "6", label: "Last 6 hours" },
  { value: "24", label: "Last 24 hours" },
  { value: "72", label: "Last 3 days" },
  { value: "168", label: "Last 7 days" },
  { value: "720", label: "Last 30 days" },
];

export default function SignalsPage() {
  return <Suspense fallback={null}><Signals /></Suspense>;
}

function Signals() {
  const now = useNow(30_000);
  const [sector, setSector] = useQueryState("sector", "");
  const [type, setType] = useQueryState("type", "");
  const [sourceQ, setSourceQ] = useQueryState("source", "");
  const [source, setSource] = useState(sourceQ);
  const [hours, setHours] = useQueryState("window", "24");
  useEffect(() => {
    const id = setTimeout(() => { if (source !== sourceQ) setSourceQ(source); }, 400);
    return () => clearTimeout(id);
  }, [source, sourceQ, setSourceQ]);
  const sectors = useApi<Sector[]>("/v1/sectors");
  const types = sector ? Object.keys(sectors.data?.find((s) => s.sector_id === sector)?.signal_types ?? {}) : [];
  // A type left over from another sector is ignored rather than cleared.
  const activeType = types.includes(type) ? type : "";
  const q = new URLSearchParams({ hours, limit: "300" });
  if (sector) q.set("sector", sector);
  if (activeType) q.set("signal_type", activeType);
  if (sourceQ.trim()) q.set("source", sourceQ.trim());
  const list = useApi<SignalsResponse>(`/v1/signals?${q.toString()}`, { pollMs: 30_000 });
  const sum = list.data?.summary;

  return (
    <div className="page">
      <PageHeader title="Signals" description="Evidence received from institutions, feeds and communities." />

      <ContextBar>
        <select className="control" aria-label="Sector" value={sector} onChange={(e) => setSector(e.target.value)}>
          <option value="">All sectors</option>
          {sectors.data?.map((s) => <option key={s.sector_id} value={s.sector_id}>{sectorName(s.sector_name)}</option>)}
        </select>
        <select className="control" aria-label="Signal type" value={activeType} onChange={(e) => setType(e.target.value)} disabled={!sector}>
          <option value="">{sector ? "All signal types" : "Select a sector for types"}</option>
          {types.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
        </select>
        <input className="control" aria-label="Source" placeholder="Source, e.g. ghs_dhims2" value={source} onChange={(e) => setSource(e.target.value)} />
        <select className="control" aria-label="Time" value={hours} onChange={(e) => setHours(e.target.value)}>
          {WINDOWS.map((w) => <option key={w.value} value={w.value}>{w.label}</option>)}
        </select>
      </ContextBar>

      <Kpis count={4}>
        <Kpi label="Received" value={sum ? sum.received.toLocaleString() : "…"} context={list.data?.truncated ? "Showing the latest 300" : WINDOWS.find((w) => w.value === hours)?.label} />
        <Kpi label="Sources" value={sum ? sum.sources : "…"} context="Distinct reporting sources" />
        <Kpi label="Mean freshness" value={sum ? (sum.mean_freshness === null ? "No data" : pct(sum.mean_freshness)) : "…"} context="Weight remaining after ageing" />
        <Kpi label="Stale" value={sum ? sum.stale : "…"} context={sum?.stale ? <Badge status="decayed">Below sector minimum</Badge> : "None below sector minimum"} />
      </Kpis>

      <ErrorNotice error={list.error} />

      <Section title="Evidence" description="Newest observation first.">
        <div className="card">
          <DataTable
            caption="Signals"
            rows={list.data?.signals ?? null}
            loading={list.loading}
            refreshing={list.refreshing}
            rowKey={(s) => s.signal_id}
            empty={{ title: "No data", description: "No evidence matches these filters." }}
            columns={[
              { key: "t", header: "Type", render: (s) => <><div className="cell-primary">{humanize(s.signal_type)}</div><div className="cell-secondary">{humanize(s.sector)}</div></> },
              { key: "r", header: "Reading", numeric: true, render: (s) => (s.reading === null || s.reading === undefined ? <span className="t-muted">Not given</span> : String(s.reading)) },
              { key: "s", header: "Source", render: (s) => humanize(s.source_id) },
              { key: "k", header: "Kind", render: (s) => SOURCE_KIND[s.source_type] ?? humanize(s.source_type) },
              { key: "o", header: "Observed", render: (s) => <Time iso={s.observed_at} now={now} /> },
              { key: "v", header: "Received", render: (s) => <Time iso={s.received_at} now={now} /> },
              { key: "f", header: "Freshness", numeric: true, render: (s) => (s.stale ? <Badge status="decayed" dot>{`Stale · ${pct(s.freshness)}`}</Badge> : <Meter value={s.freshness} width={48} />) },
            ]}
          />
        </div>
      </Section>
    </div>
  );
}
