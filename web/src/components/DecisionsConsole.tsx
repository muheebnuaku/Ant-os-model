"use client";

import { ListChecks, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { DetailEmpty, ListItem, ListSkeleton, Pane, SplitView, useSelectHref } from "@/components/console";
import { DecisionView } from "@/components/DecisionView";
import { Badge, ErrorNotice, Meter, Time, humanize, sectorName } from "@/components/ui";
import { useApi, useNow, useQueryState } from "@/lib/hooks";
import { CAN, useSession } from "@/lib/session";
import type { DecisionSummary, Sector } from "@/lib/types";

const RANGES = [
  { value: "1", label: "24 hours" },
  { value: "7", label: "7 days" },
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
];

/** Decisions list beside the selected decision. `selected` comes from ?ref= or the route. */
export function DecisionsConsole({ selected }: { selected: string | null }) {
  const { can } = useSession();
  const now = useNow(60_000);
  const [q, setQ] = useQueryState("q", "");
  const [query, setQuery] = useState(q);
  const [sector, setSector] = useQueryState("sector", "");
  const [result, setResult] = useQueryState("result", "");
  const [outcome, setOutcome] = useQueryState("outcome", "");
  const [days, setDays] = useQueryState("range", "30");
  const hrefFor = useSelectHref("ref", "/decisions");
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
    <SplitView hasSelection={!!selected}>
      <Pane kind="list" title="Decisions" count={list.data ? rows.length : null}
        actions={can(CAN.decide) ? <Link className="btn btn-primary btn-compact" href="/decisions/new"><Plus size={14} strokeWidth={1.5} aria-hidden />New</Link> : null}
        toolbar={<>
          <label className="search-field">
            <Search size={14} strokeWidth={1.5} aria-hidden />
            <input className="control" type="search" placeholder="Search decisions" aria-label="Search decisions" value={query} onChange={(e) => setQuery(e.target.value)} />
          </label>
          <select className="control" aria-label="Sector" value={sector} onChange={(e) => setSector(e.target.value)}>
            <option value="">All sectors</option>
            {sectors.data?.map((s) => <option key={s.sector_id} value={s.sector_id}>{sectorName(s.sector_name)}</option>)}
          </select>
          <select className="control" aria-label="Result" value={result} onChange={(e) => setResult(e.target.value)}>
            <option value="">Any result</option>
            {["trusted", "provisional", "conflicted", "blocked", "decayed"].map((r) => <option key={r} value={r}>{humanize(r)}</option>)}
          </select>
          <select className="control" aria-label="Outcome" value={outcome} onChange={(e) => setOutcome(e.target.value)}>
            <option value="">Any outcome</option>
            <option value="ready">Cleared to act</option>
            <option value="person">Needs a person</option>
            <option value="hold">On hold</option>
          </select>
          <select className="control" aria-label="Date range" value={days} onChange={(e) => setDays(e.target.value)}>
            {RANGES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </>}>
        <ErrorNotice error={list.error} />
        {!list.data ? <ListSkeleton /> : rows.length ? (
          <ul className="list" aria-label="Decisions">
            {rows.map((d) => (
              <ListItem key={d.audit_ref} href={hrefFor(d.audit_ref, ["tab"])} selected={d.audit_ref === selected}
                title={d.objective ?? d.decision_id}
                aside={<Time iso={d.created_at} now={now} />}
                meta={<>
                  <span>{humanize(d.sector)}</span>
                  <Badge status={d.validation_state} dot />
                  <Badge status={d.action} dot />
                  {d.human_escalation_required ? <span>Needs a person</span> : null}
                </>}
                bar={<Meter value={d.confidence} width={96} />}
              />
            ))}
          </ul>
        ) : <p className="list-empty">No decisions match. Try a wider date range or fewer filters.</p>}
      </Pane>

      {selected ? <DecisionView key={selected} auditRef={selected} back={hrefFor(null, ["tab"])} /> : (
        <section className="pane pane-detail" aria-label="Decision">
          <DetailEmpty icon={ListChecks} title="Select a decision">
            The advice, the evidence behind it, and its sealed record appear here.
          </DetailEmpty>
        </section>
      )}
    </SplitView>
  );
}
