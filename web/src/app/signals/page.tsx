"use client";

import { Radio } from "lucide-react";
import { Suspense, useEffect, useState } from "react";

import { DetailEmpty, ListItem, ListSkeleton, Pane, SplitView, useSelectHref } from "@/components/console";
import { Badge, ErrorNotice, Kpi, Kpis, Meter, Section, Time, absolute, humanize, pct, sectorName } from "@/components/ui";
import { useApi, useNow, useQueryState } from "@/lib/hooks";
import type { Sector, SignalRow, SignalsResponse } from "@/lib/types";

const SOURCE_KIND: Record<string, string> = {
  formal_institution: "Official institution", api_feed: "Automated feed", satellite: "Satellite",
  informal_operator: "Informal operator", community_source: "Community report", manual_entry: "Entered by hand",
};

const WINDOWS = [
  { value: "6", label: "6 hours" },
  { value: "24", label: "24 hours" },
  { value: "72", label: "3 days" },
  { value: "168", label: "7 days" },
  { value: "720", label: "30 days" },
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
  const [selectedId] = useQueryState("sig", "");
  const hrefFor = useSelectHref("sig");
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
  const rows = list.data?.signals ?? [];
  const selected = rows.find((s) => s.signal_id === selectedId) ?? null;

  return (
    <SplitView hasSelection={!!selected}>
      <Pane kind="list" title="Signals" count={list.data ? rows.length : null}
        toolbar={<>
          <input className="control" style={{ flex: "1 1 100%" }} aria-label="Source" placeholder="Filter by source, e.g. ghs_dhims2" value={source} onChange={(e) => setSource(e.target.value)} />
          <select className="control" aria-label="Sector" value={sector} onChange={(e) => setSector(e.target.value)}>
            <option value="">All sectors</option>
            {sectors.data?.map((s) => <option key={s.sector_id} value={s.sector_id}>{sectorName(s.sector_name)}</option>)}
          </select>
          <select className="control" aria-label="Signal type" value={activeType} onChange={(e) => setType(e.target.value)} disabled={!sector}>
            <option value="">{sector ? "All types" : "Pick a sector for types"}</option>
            {types.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
          </select>
          <select className="control" aria-label="Time" value={hours} onChange={(e) => setHours(e.target.value)}>
            {WINDOWS.map((w) => <option key={w.value} value={w.value}>{w.label}</option>)}
          </select>
        </>}>
        <ErrorNotice error={list.error} />
        {!list.data ? <ListSkeleton /> : rows.length ? (
          <ul className="list" aria-label="Signals">
            {rows.map((s) => (
              <ListItem key={s.signal_id} href={hrefFor(s.signal_id)} selected={s.signal_id === selectedId}
                title={<>{humanize(s.signal_type)}{s.reading !== null && s.reading !== undefined ? <span className="t-num" style={{ color: "var(--text-2)", fontWeight: 400 }}> · {String(s.reading)}</span> : null}</>}
                aside={<Time iso={s.observed_at ?? s.received_at} now={now} />}
                meta={<>
                  <span>{humanize(s.sector)}</span>
                  <span>{humanize(s.source_id)}</span>
                  {s.stale ? <Badge status="decayed" dot>Stale</Badge> : null}
                </>}
              />
            ))}
          </ul>
        ) : <p className="list-empty">No evidence matches these filters.</p>}
      </Pane>

      {selected ? <SignalDetail s={selected} now={now} back={hrefFor(null)} /> : (
        <Pane kind="detail" title="Evidence overview" label="Evidence overview">
          <div className="pane-detail-inner">
            <Kpis count={4}>
              <Kpi label="Received" value={sum ? sum.received.toLocaleString() : "…"} context={list.data?.truncated ? "Showing the latest 300" : `Last ${WINDOWS.find((w) => w.value === hours)?.label}`} />
              <Kpi label="Sources" value={sum ? sum.sources : "…"} context="Distinct reporting sources" />
              <Kpi label="Mean freshness" value={sum ? (sum.mean_freshness === null ? "No data" : pct(sum.mean_freshness)) : "…"} context="Weight remaining after ageing" />
              <Kpi label="Stale" value={sum ? sum.stale : "…"} context={sum?.stale ? <Badge status="decayed">Below sector minimum</Badge> : "None below sector minimum"} />
            </Kpis>
            <DetailEmpty icon={Radio} title="Select a signal">
              Newest observation first. Pick one to see where it came from and how much weight it still carries.
            </DetailEmpty>
          </div>
        </Pane>
      )}
    </SplitView>
  );
}

function SignalDetail({ s, now, back }: { s: SignalRow; now: number; back: string }) {
  return (
    <Pane kind="detail" back={back} label="Signal" title={<>{humanize(s.sector)} <span className="count">{SOURCE_KIND[s.source_type] ?? humanize(s.source_type)}</span></>}>
      <div className="pane-detail-inner">
        <header className="detail-head">
          <span className="eyebrow">From {humanize(s.source_id)} · received <Time iso={s.received_at} now={now} /></span>
          <h2>{humanize(s.signal_type)}</h2>
        </header>

        <div className="kpis" style={{ ["--n" as string]: 2 }}>
          <Kpi label={s.reading_field ? humanize(s.reading_field) : "Reading"} value={s.reading === null || s.reading === undefined ? "Not given" : String(s.reading)} />
          <Kpi label="Freshness" value={s.freshness === null ? "No data" : pct(s.freshness)}
            context={s.stale ? <Badge status="decayed">Below sector minimum</Badge> : "Weight remaining after ageing"} />
        </div>

        <Section title="Provenance">
          <div className="card card-pad stack">
            <dl className="kv">
              <dt>Source</dt><dd>{humanize(s.source_id)} <span className="t-muted t-mono">{s.source_id}</span></dd>
              <dt>Kind of source</dt><dd>{SOURCE_KIND[s.source_type] ?? humanize(s.source_type)}</dd>
              <dt>Sector</dt><dd>{humanize(s.sector)}</dd>
              <dt>Observed</dt><dd>{s.observed_at ? absolute(s.observed_at) : <span className="t-muted">Not given</span>}</dd>
              <dt>Received</dt><dd>{absolute(s.received_at)}</dd>
              <dt>Signal ID</dt><dd className="t-mono">{s.signal_id}</dd>
            </dl>
            {s.freshness !== null ? <div className="stack-sm"><span className="kpi-label">Freshness</span><Meter value={s.freshness} width={240} /></div> : null}
          </div>
        </Section>
      </div>
    </Pane>
  );
}
