"use client";

import { ChevronRight } from "lucide-react";

import { DataTable } from "@/components/DataTable";
import { Badge, ErrorNotice, Kpi, Kpis, Notice, PageHeader, Section, SkeletonRows, SECTOR_ORDER, humanize, pct, sectorName } from "@/components/ui";
import { useApi } from "@/lib/hooks";

interface Pack {
  sector_id: string;
  sector_name: string;
  half_life_hours: number;
  model_route: string;
  validation_thresholds: { trusted: number; provisional: number; conflicted: number; decay_freshness_floor: number };
  escalation_rules: { id: string; when: string; priority: string; role: string | null; sla_minutes: number | null; description: string }[];
  escalation_routing: Record<string, { role: string; sla_minutes: number }>;
}
interface Config {
  config_hash: string;
  profile: {
    manifest: { name: string; version: string; source_reliability: Record<string, number>; default_source_reliability: number };
    packs: Record<string, Pack>;
  };
}

const ROUTE: Record<string, string> = {
  default: "Cloud or on-premises model",
  sovereign: "On-premises model only",
  rules_only: "Built-in rules only",
};

export default function RulesPage() {
  const cfg = useApi<Config>("/v1/admin/config");
  const c = cfg.data;
  const packs = c ? SECTOR_ORDER.map((s) => c.profile.packs[s]).filter((p): p is Pack => !!p) : null;
  const ruleCount = packs?.reduce((a, p) => a + p.escalation_rules.length, 0) ?? 0;

  return (
    <div className="page">
      <PageHeader title="Rules & configuration" description="The thresholds, weights and escalation rules every decision is evaluated against." />
      <ErrorNotice error={cfg.error} />
      {!c || !packs ? <div className="card"><SkeletonRows rows={6} /></div> : (
        <>
          <Kpis count={4}>
            <Kpi label="Rules version" value={c.profile.manifest.version} context={c.profile.manifest.name} />
            <Kpi label="Sectors" value={packs.length} context="Sector packs in force" />
            <Kpi label="Escalation rules" value={ruleCount} context="Conditions that call a person" />
            <Kpi label="Rules fingerprint" value={<span style={{ fontSize: 20 }}>{c.config_hash.slice(0, 10)}</span>} context="Recorded with every decision" />
          </Kpis>

          <Notice tone="info">Rules are changed only by the sovereign authority, with a written rationale. Every change is recorded and earlier decisions keep the rules they were made under.</Notice>

          <div className="layout-main">
            <Section title="Sector thresholds" description="Confidence needed for each evidence result.">
              <div className="card">
                <DataTable caption="Sector thresholds" rows={packs} rowKey={(p) => p.sector_id} empty={{ title: "No sectors" }}
                  columns={[
                    { key: "s", header: "Sector", render: (p) => <span className="cell-primary">{sectorName(p.sector_name)}</span> },
                    { key: "h", header: "Half-life", numeric: true, render: (p) => `${p.half_life_hours} h` },
                    { key: "t", header: "Trusted from", numeric: true, render: (p) => pct(p.validation_thresholds.trusted) },
                    { key: "p", header: "Provisional from", numeric: true, render: (p) => pct(p.validation_thresholds.provisional) },
                    { key: "b", header: "Blocked below", numeric: true, render: (p) => pct(p.validation_thresholds.conflicted) },
                    { key: "m", header: "Advice from", render: (p) => ROUTE[p.model_route] ?? humanize(p.model_route) },
                  ]} />
              </div>
            </Section>
            <Section title="Source reliability" description="Starting weight given to each kind of source.">
              <div className="card">
                <DataTable caption="Source reliability" rowKey={(r) => r[0]} empty={{ title: "None" }}
                  rows={Object.entries(c.profile.manifest.source_reliability).sort((a, b) => b[1] - a[1])}
                  columns={[
                    { key: "k", header: "Kind of source", render: (r) => humanize(r[0]) },
                    { key: "v", header: "Reliability", numeric: true, render: (r) => pct(r[1]) },
                  ]} />
              </div>
            </Section>
          </div>

          <Section title="Escalation rules" description="When a person must review a decision, by sector.">
            <div className="stack-sm">
              {packs.map((p) => (
                <details key={p.sector_id} className="disclosure">
                  <summary><ChevronRight size={16} strokeWidth={1.5} aria-hidden />{sectorName(p.sector_name)} <span className="t-small t-muted">· {p.escalation_rules.length} rules</span></summary>
                  <div className="disclosure-body" style={{ padding: 0 }}>
                    <DataTable caption={`${p.sector_name} escalation rules`} rows={p.escalation_rules} rowKey={(r) => r.id} empty={{ title: "No sector-specific rules" }}
                      columns={[
                        { key: "d", header: "Condition", render: (r) => <><div className="cell-primary">{r.description}</div><div className="cell-secondary t-mono">{r.when}</div></> },
                        { key: "p", header: "Priority", render: (r) => <Badge status={r.priority} /> },
                        { key: "r", header: "Assigned to", render: (r) => humanize(r.role ?? p.escalation_routing[r.priority]?.role) },
                        { key: "t", header: "Response time", numeric: true, render: (r) => `${r.sla_minutes ?? p.escalation_routing[r.priority]?.sla_minutes} min` },
                      ]} />
                  </div>
                </details>
              ))}
            </div>
          </Section>

          <details className="disclosure">
            <summary><ChevronRight size={16} strokeWidth={1.5} aria-hidden />Technical record</summary>
            <div className="disclosure-body"><pre className="json">{JSON.stringify(c, null, 2)}</pre></div>
          </details>
        </>
      )}
    </div>
  );
}
