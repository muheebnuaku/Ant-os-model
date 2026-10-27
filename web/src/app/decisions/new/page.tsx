"use client";

import { Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState, type FormEvent, type ReactNode } from "react";

import { ErrorNotice, PageHeader, Segmented, SkeletonRows, humanize, sectorName } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { ResolveBody, Sector, StoredDecision } from "@/lib/types";

const SOURCE_TYPES = [
  ["formal_institution", "Official institution"], ["api_feed", "Automated data feed"], ["satellite", "Satellite"],
  ["informal_operator", "Informal operator"], ["community_source", "Community report"], ["manual_entry", "Entered by hand"],
] as const;

const HAE = [
  ["worker_dignity_preserved", "Protects workers' dignity and safety"],
  ["data_sovereignty_preserved", "Keeps data under national control"],
  ["intra_african_value_creation", "Creates value within Africa"],
  ["informal_actor_inclusion", "Includes informal businesses"],
  ["dependency_reduction", "Reduces outside dependency"],
] as const;

const LOCAL_FIT = [
  ["institutional_alignment", "Fits how the institutions work"],
  ["linguistic_appropriateness", "Available in the right languages"],
  ["infrastructure_feasibility", "Infrastructure can support it"],
  ["cultural_safety", "Culturally appropriate"],
  ["regulatory_grounding", "Lawful under local regulation"],
  ["resource_realism", "Resources are realistic"],
] as const;

type Tri = "unknown" | "yes" | "no";
interface Row { id: number; type: string; reading: string; source: string; kind: (typeof SOURCE_TYPES)[number][0]; observed: string; ref: string }

let seq = 1;
function nowLocal(): string {
  const d = new Date();
  d.setSeconds(0, 0);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
const blank = (): Row => ({ id: seq++, type: "", reading: "", source: "", kind: "formal_institution", observed: nowLocal(), ref: "" });

function FormSection({ n, title, description, children }: { n: number; title: string; description: string; children: ReactNode }) {
  return (
    <section className="card card-pad stack" aria-labelledby={`s${n}`}>
      <div className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap", gap: 12 }}>
        <span className="step-number" aria-hidden>{n}</span>
        <div><h2 id={`s${n}`}>{title}</h2><p className="t-small t-muted">{description}</p></div>
      </div>
      {children}
    </section>
  );
}

export default function NewDecisionPage() {
  const { me } = useSession();
  const router = useRouter();
  const sectors = useApi<Sector[]>("/v1/sectors");
  const [sectorId, setSectorId] = useState("");
  const [objective, setObjective] = useState("");
  const [serious, setSerious] = useState(false);
  const [rows, setRows] = useState<Row[]>([blank()]);
  const [hae, setHae] = useState<Record<string, Tri>>({});
  const [fit, setFit] = useState<Record<string, Tri>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [touched, setTouched] = useState(false);

  const sector = useMemo(() => sectors.data?.find((s) => s.sector_id === sectorId), [sectors.data, sectorId]);
  const types = sector ? Object.keys(sector.signal_types) : [];
  const set = (id: number, patch: Partial<Row>) => setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  const missing = (v: string) => touched && !v.trim();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!sector || !objective.trim() || rows.some((r) => !r.type || !r.source.trim())) return;
    setBusy(true);
    setError(null);
    const known = (m: Record<string, Tri>, keys: readonly (readonly [string, string])[]) =>
      Object.fromEntries(keys.map(([k]) => [k, m[k] ?? "unknown"]).filter(([, v]) => v !== "unknown").map(([k, v]) => [k, v === "yes"]));
    const body: ResolveBody = {
      objective: objective.trim(),
      sector: sector.sector_id,
      nation_id: me?.nation_id ?? "GH",
      high_consequence: serious,
      signals: rows.map((r) => {
        const field = sector.signal_types[r.type] ?? "value";
        return {
          signal_type: r.type, source_id: r.source.trim(), source_type: r.kind,
          observed_at: new Date(r.observed).toISOString(),
          payload: { ...(r.reading.trim() ? { [field]: Number(r.reading) } : {}), ...(r.ref.trim() ? { source_ref: r.ref.trim() } : {}) },
        };
      }),
    };
    const h = known(hae, HAE);
    if (Object.keys(h).length) body.hae = h;
    const f = known(fit, LOCAL_FIT);
    if (Object.keys(f).length) body.local_fit = f;
    try {
      const out = await api<StoredDecision>("/v1/decisions/resolve", { body });
      router.push(`/decisions/${out.audit_ref}`);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      setBusy(false);
    }
  }

  const tri = (value: Tri, onChange: (v: Tri) => void, label: string) => (
    <Segmented<Tri> label={label} value={value} onChange={onChange}
      options={[{ value: "unknown", label: "Unknown" }, { value: "yes", label: "Yes" }, { value: "no", label: "No" }]} />
  );

  return (
    <div className="page" style={{ maxWidth: 880 }}>
      <PageHeader title="New decision" description="Describe the decision and the evidence. ANT-OS checks the evidence, advises, and calls a person when required." />
      {!sectors.data ? <div className="card"><SkeletonRows /></div> : (
        <form className="stack" style={{ gap: 24 }} onSubmit={submit} noValidate>
          <FormSection n={1} title="Decision" description="What needs to be decided, and in which sector.">
            <div className="field-grid" style={{ gridTemplateColumns: "minmax(0, 1fr) minmax(0, 2fr)" }}>
              <label className="field">
                <span>Sector</span>
                <select className="control" value={sectorId} aria-invalid={missing(sectorId)} onChange={(e) => { setSectorId(e.target.value); setRows([blank()]); }}>
                  <option value="">Select a sector</option>
                  {sectors.data.map((s) => <option key={s.sector_id} value={s.sector_id}>{sectorName(s.sector_name)}</option>)}
                </select>
                {missing(sectorId) ? <span className="field-hint" style={{ color: "var(--critical)" }}>Select a sector.</span> : null}
              </label>
              <label className="field">
                <span>Decision</span>
                <input className="control" value={objective} aria-invalid={missing(objective)} onChange={(e) => setObjective(e.target.value)} placeholder="e.g. Plan oxygen supply for Tamale Teaching Hospital" />
                {missing(objective) ? <span className="field-hint" style={{ color: "var(--critical)" }}>Describe the decision in one sentence.</span> : null}
              </label>
            </div>
            <label className="checkbox t-small">
              <input type="checkbox" checked={serious} onChange={(e) => setSerious(e.target.checked)} />
              This decision has serious consequences. A person must always review it.
            </label>
          </FormSection>

          <FormSection n={2} title="Evidence" description={sector ? `Evidence for ${sectorName(sector.sector_name)} loses half its weight every ${sector.half_life_hours} hours.` : "Select a sector first."}>
            {sector ? (
              <div className="stack">
                {rows.map((r, i) => (
                  <fieldset key={r.id} className="stack" style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 16, margin: 0 }}>
                    <legend className="t-caption t-muted" style={{ padding: "0 4px" }}>Evidence {i + 1}</legend>
                    <div className="field-grid">
                      <label className="field">
                        <span>What it measures</span>
                        <select className="control" value={r.type} aria-invalid={missing(r.type)} onChange={(e) => set(r.id, { type: e.target.value })}>
                          <option value="">Select</option>
                          {types.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
                        </select>
                      </label>
                      <label className="field">
                        <span>Reading{r.type && sector.signal_types[r.type] ? ` (${humanize(sector.signal_types[r.type]).toLowerCase()})` : ""}</span>
                        <input className="control" type="number" step="any" value={r.reading} onChange={(e) => set(r.id, { reading: e.target.value })} />
                      </label>
                      <label className="field">
                        <span>Reported by</span>
                        <input className="control" value={r.source} aria-invalid={missing(r.source)} onChange={(e) => set(r.id, { source: e.target.value })} placeholder="e.g. Ghana Health Service" />
                      </label>
                      <label className="field">
                        <span>Kind of source</span>
                        <select className="control" value={r.kind} onChange={(e) => set(r.id, { kind: e.target.value as Row["kind"] })}>
                          {SOURCE_TYPES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                        </select>
                      </label>
                      <label className="field">
                        <span>Observed at</span>
                        <input className="control" type="datetime-local" value={r.observed} onChange={(e) => set(r.id, { observed: e.target.value })} />
                      </label>
                      <label className="field">
                        <span>Reference (optional)</span>
                        <input className="control" value={r.ref} onChange={(e) => set(r.id, { ref: e.target.value })} placeholder="Report or record number" />
                      </label>
                    </div>
                    {(missing(r.type) || missing(r.source)) ? <span className="field-hint" style={{ color: "var(--critical)" }}>Select what it measures and who reported it.</span> : null}
                    {rows.length > 1 ? (
                      <div><button type="button" className="btn btn-tertiary btn-danger btn-compact" onClick={() => setRows((rs) => rs.filter((x) => x.id !== r.id))}><Trash2 size={16} strokeWidth={1.75} aria-hidden />Remove</button></div>
                    ) : null}
                  </fieldset>
                ))}
                <div className="between" style={{ flexWrap: "wrap" }}>
                  <button type="button" className="btn" onClick={() => setRows((rs) => [...rs, blank()])}><Plus size={16} strokeWidth={1.75} aria-hidden />Add evidence from another source</button>
                  <span className="t-small t-muted">Two independent sources that agree are far more trustworthy than one.</span>
                </div>
              </div>
            ) : null}
          </FormSection>

          <FormSection n={3} title="Context (optional)" description="Unknown is the default and is never treated as yes or no.">
            <div className="grid-2">
              <div className="stack-sm">
                <h3>24-hour economy</h3>
                {HAE.map(([k, t]) => (
                  <div key={k} className="between" style={{ borderBottom: "1px solid var(--border)", padding: "8px 0" }}>
                    <span className="t-small">{t}</span>{tri(hae[k] ?? "unknown", (v) => setHae((m) => ({ ...m, [k]: v })), t)}
                  </div>
                ))}
              </div>
              <div className="stack-sm">
                <h3>Local fit</h3>
                {LOCAL_FIT.map(([k, t]) => (
                  <div key={k} className="between" style={{ borderBottom: "1px solid var(--border)", padding: "8px 0" }}>
                    <span className="t-small">{t}</span>{tri(fit[k] ?? "unknown", (v) => setFit((m) => ({ ...m, [k]: v })), t)}
                  </div>
                ))}
              </div>
            </div>
          </FormSection>

          <ErrorNotice error={error} />
          <div className="form-footer">
            <Link className="btn" href="/decisions">Cancel</Link>
            <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? "Evaluating…" : "Evaluate decision"}</button>
          </div>
        </form>
      )}
    </div>
  );
}
