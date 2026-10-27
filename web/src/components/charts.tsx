"use client";

import { useCallback, useState, type FocusEvent, type MouseEvent, type ReactNode } from "react";

import { pct, statusLabel } from "./ui";

/* Charts (§8): thin marks, hairline chrome, one accent hue for single series,
   status colors only for status, a legend wherever more than one color carries
   meaning, a tooltip on hover and keyboard focus, and a table equivalent. */

function hhmm(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

export function useTooltip() {
  const [tip, setTip] = useState<{ x: number; y: number; content: ReactNode } | null>(null);
  const show = useCallback((e: MouseEvent | FocusEvent, content: ReactNode) => {
    if ("clientX" in e) setTip({ x: e.clientX, y: e.clientY, content });
    else {
      const r = (e.target as HTMLElement).getBoundingClientRect();
      setTip({ x: r.left + r.width / 2, y: r.bottom, content });
    }
  }, []);
  const hide = useCallback(() => setTip(null), []);
  const node = tip ? (
    <div className="tooltip" role="tooltip" style={{ left: Math.min(tip.x + 12, window.innerWidth - 300), top: tip.y + 12 }}>
      {tip.content}
    </div>
  ) : null;
  return { show, hide, node };
}

/* Five results folded into three colour classes: in a grid every cell can
   neighbour every other, and only three hues stay distinguishable for all
   readers (validated all-pairs, both themes). Tooltips and the table view
   still give each cell's exact result. */
const STATE_FILL: Record<string, string> = {
  trusted: "var(--heat-ok)",
  provisional: "var(--heat-ok)",
  decayed: "var(--heat-care)",
  conflicted: "var(--heat-care)",
  blocked: "var(--heat-blocked)",
};

const HEAT_CLASSES = [
  { fill: "var(--heat-ok)", label: "Trusted or provisional" },
  { fill: "var(--heat-care)", label: "Decayed or conflicted" },
  { fill: "var(--heat-blocked)", label: "Blocked" },
];

// ── Sparkline: one series, named by its label ───────────────

export function Sparkline({ values, starts, what, height = 32 }: { values: number[]; starts: string[]; what: string; height?: number }) {
  const { show, hide, node } = useTooltip();
  const [hover, setHover] = useState<number | null>(null);
  const w = 200;
  const max = Math.max(1, ...values);
  const step = w / Math.max(1, values.length - 1);
  const y = (v: number) => height - 2 - (v / max) * (height - 6);
  const points = values.map((v, i) => `${(i * step).toFixed(1)},${y(v).toFixed(1)}`).join(" ");

  function onMove(e: MouseEvent<SVGSVGElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    const i = Math.max(0, Math.min(values.length - 1, Math.round(((e.clientX - r.left) / r.width) * (values.length - 1))));
    setHover(i);
    show(e, <><div className="t-head">{starts[i] ? hhmm(starts[i]) : what}</div><div className="t-row">{what} <b>{values[i]}</b></div></>);
  }

  return (
    <>
      <svg viewBox={`0 0 ${w} ${height}`} width="100%" height={height} preserveAspectRatio="none" role="img"
        aria-label={`${what}: ${values.reduce((a, b) => a + b, 0)} in the window`}
        onMouseMove={onMove} onMouseLeave={() => { setHover(null); hide(); }} style={{ display: "block", overflow: "visible" }}>
        <line x1="0" x2={w} y1={height - 2} y2={height - 2} stroke="var(--grid)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        <polyline points={points} fill="none" stroke="var(--chart-1)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
        {hover !== null ? (
          <circle cx={hover * step} cy={y(values[hover] ?? 0)} r="4" fill="var(--chart-1)" stroke="var(--surface)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
        ) : null}
      </svg>
      {node}
    </>
  );
}

// ── Activity heatmap ───────────────────────────────────────

export interface HeatRow {
  key: string;
  label: string;
  buckets: { start: string; signals: number; decisions: number; worst_state: string | null }[];
}

/** The heatmap's legend, for placing in a section header. */
export function HeatLegend() {
  return (
    <div className="legend" aria-label="Legend">
      {HEAT_CLASSES.map((c) => <span key={c.label}><i className="swatch" style={{ background: c.fill }} />{c.label}</span>)}
      <span><i className="swatch" style={{ background: "var(--heat-signals)" }} />Evidence only</span>
      <span><i className="swatch" style={{ background: "var(--heat-empty)", boxShadow: "inset 0 0 0 1px var(--border)" }} />No activity</span>
    </div>
  );
}

export function ActivityHeatmap({ rows, bucketMinutes, onRowClick, showLegend = true }: { rows: HeatRow[]; bucketMinutes: number; onRowClick?: (key: string) => void; showLegend?: boolean }) {
  const { show, hide, node } = useTooltip();
  const [asTable, setAsTable] = useState(false);
  const axis = rows[0]?.buckets ?? [];
  const fill = (b: HeatRow["buckets"][number]) => (b.worst_state ? STATE_FILL[b.worst_state] : b.signals ? "var(--heat-signals)" : undefined);
  const tip = (r: HeatRow, b: HeatRow["buckets"][number]) => (
    <>
      <div className="t-head">{r.label} · {hhmm(b.start)}</div>
      <div className="t-row">Evidence received <b>{b.signals}</b></div>
      <div className="t-row">Decisions <b>{b.decisions}</b></div>
      {b.worst_state ? <div className="t-row">Weakest result <b>{statusLabel(b.worst_state)}</b></div> : null}
    </>
  );

  return (
    <div className="stack">
      <div className="between" style={{ flexWrap: "wrap" }}>
        {showLegend ? <HeatLegend /> : <span />}
        <button type="button" className="btn btn-tertiary btn-compact" onClick={() => setAsTable((t) => !t)}>
          {asTable ? "View as chart" : "View as table"}
        </button>
      </div>

      {asTable ? (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Sector</th><th>Period starting</th><th className="num">Evidence</th><th className="num">Decisions</th><th>Weakest result</th></tr></thead>
            <tbody>
              {rows.flatMap((r) => r.buckets.filter((b) => b.signals || b.decisions).map((b) => (
                <tr key={`${r.key}${b.start}`}>
                  <td data-label="Sector">{r.label}</td>
                  <td data-label="Period starting">{hhmm(b.start)}</td>
                  <td data-label="Evidence" className="num">{b.signals}</td>
                  <td data-label="Decisions" className="num">{b.decisions}</td>
                  <td data-label="Weakest result">{b.worst_state ? statusLabel(b.worst_state) : "No decisions"}</td>
                </tr>
              )))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="heat" role="grid" aria-label="Activity by sector and time">
          {rows.map((r) => (
            <div key={r.key} role="row" style={{ display: "contents" }}>
              <button type="button" className="heat-label" onClick={() => onRowClick?.(r.key)}>{r.label}</button>
              <div className="heat-row">
                {r.buckets.map((b) => (
                  <button key={b.start} type="button" role="gridcell" className="heat-cell"
                    style={fill(b) ? { background: fill(b) } : undefined}
                    aria-label={`${r.label}, ${hhmm(b.start)}: ${b.signals} evidence, ${b.decisions} decisions${b.worst_state ? `, weakest ${statusLabel(b.worst_state)}` : ""}`}
                    onMouseMove={(e) => show(e, tip(r, b))} onFocus={(e) => show(e, tip(r, b))} onMouseLeave={hide} onBlur={hide} />
                ))}
              </div>
            </div>
          ))}
          <span />
          <div className="heat-axis" aria-hidden>{axis.map((b, i) => <span key={b.start}>{i % 6 === 0 ? hhmm(b.start) : ""}</span>)}</div>
          <span />
          <span className="t-caption t-muted">Each cell covers {bucketMinutes} minutes.</span>
        </div>
      )}
      {node}
    </div>
  );
}

// ── Confidence breakdown: C = Σ Wi·xi − W6·P ──────────────────

const COMPONENTS = [
  { key: "evidence_strength", name: "Evidence quality", hint: "How measurable, cited and traceable the evidence is" },
  { key: "signal_freshness", name: "Freshness", hint: "How recently the sources observed it" },
  { key: "source_reliability", name: "Source reliability", hint: "How dependable the reporting sources are" },
  { key: "cross_signal_consistency", name: "Agreement", hint: "How well independent sources agree" },
  { key: "domain_stability_modifier", name: "Sector stability", hint: "How stable this sector usually is" },
];

export function ConfidenceBreakdown({ inputs, weights, confidence }: { inputs: Record<string, number>; weights: Record<string, number>; confidence: number }) {
  const { show, hide, node } = useTooltip();
  const [asTable, setAsTable] = useState(false);
  const rows = [
    ...COMPONENTS.map((c) => ({ ...c, negative: false, input: inputs[c.key] ?? 0, weight: weights[c.key] ?? 0 })),
    { key: "contradiction_penalty", name: "Disagreement penalty", hint: "Deducted when sources contradict each other", negative: true,
      input: inputs.contradiction_penalty ?? 0, weight: weights.contradiction_penalty ?? 0 },
  ].map((r) => ({ ...r, value: r.input * r.weight }));
  const scale = Math.max(0.3, ...rows.map((r) => r.value));

  return (
    <div className="stack">
      <div className="between" style={{ flexWrap: "wrap" }}>
        <div className="legend">
          <span><i className="swatch" style={{ background: "var(--chart-1)" }} />Adds confidence</span>
          <span><i className="swatch" style={{ background: "var(--chart-negative)" }} />Deducted</span>
        </div>
        <button type="button" className="btn btn-tertiary btn-compact" onClick={() => setAsTable((t) => !t)}>
          {asTable ? "View as chart" : "View as table"}
        </button>
      </div>
      {asTable ? (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Component</th><th className="num">Score</th><th className="num">Weight</th><th className="num">Contribution</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key}>
                  <td data-label="Component">{r.name}</td>
                  <td data-label="Score" className="num">{pct(r.input, 1)}</td>
                  <td data-label="Weight" className="num">{r.weight.toFixed(3)}</td>
                  <td data-label="Contribution" className="num">{r.negative ? "−" : "+"}{pct(r.value, 1)}</td>
                </tr>
              ))}
              <tr><td data-label="Component" className="t-strong">Confidence</td><td /><td /><td data-label="Contribution" className="num t-strong">{pct(confidence, 1)}</td></tr>
            </tbody>
          </table>
        </div>
      ) : (
        <div className="stack-sm">
          {rows.map((r) => {
            const content = (
              <>
                <div className="t-head">{r.name}</div>
                <div className="t-row">{r.hint}</div>
                <div className="t-row">Score <b>{pct(r.input, 1)}</b></div>
                <div className="t-row">Weight <b>{r.weight.toFixed(3)}</b></div>
              </>
            );
            return (
              <div key={r.key} tabIndex={0} style={{ display: "grid", gridTemplateColumns: "160px minmax(0, 1fr) 64px", gap: 16, alignItems: "center", minHeight: 32 }}
                onMouseMove={(e) => show(e, content)} onFocus={(e) => show(e, content)} onMouseLeave={hide} onBlur={hide}>
                <span className="t-small">{r.name}</span>
                <div style={{ height: 8, background: "var(--surface-subtle)", borderRadius: 4 }}>
                  <div style={{ width: `${(r.value / scale) * 100}%`, height: "100%", borderRadius: 4, background: r.negative ? "var(--chart-negative)" : "var(--chart-1)" }} />
                </div>
                <span className="t-small t-num" style={{ textAlign: "right" }}>{r.negative ? "−" : "+"}{pct(r.value, 1)}</span>
              </div>
            );
          })}
          <hr className="divider" style={{ margin: "8px 0" }} />
          <div className="between"><span className="t-strong">Confidence</span><span className="t-strong t-num">{pct(confidence, 1)}</span></div>
        </div>
      )}
      {node}
    </div>
  );
}
