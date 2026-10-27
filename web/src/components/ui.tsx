"use client";

import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  Info,
  OctagonX,
  ShieldAlert,
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, type ReactNode } from "react";

/* Shared components per docs/UI_MASTER_PROMPT.md §6. */

// ── Status (§5.2): fixed tone, icon and label for every state ──

export type Tone = "good" | "warning" | "serious" | "critical" | "neutral" | "info";

const TONE_ICON: Record<Tone, LucideIcon> = {
  good: CheckCircle2,
  warning: AlertTriangle,
  serious: ShieldAlert,
  critical: OctagonX,
  neutral: CircleDashed,
  info: Info,
};

const STATUS: Record<string, { tone: Tone; label: string }> = {
  trusted: { tone: "good", label: "Trusted" },
  provisional: { tone: "info", label: "Provisional" },
  decayed: { tone: "warning", label: "Decayed" },
  conflicted: { tone: "serious", label: "Conflicted" },
  blocked: { tone: "critical", label: "Blocked" },
  stable: { tone: "good", label: "Stable" },
  attention: { tone: "warning", label: "Attention" },
  critical: { tone: "critical", label: "Critical" },
  no_data: { tone: "neutral", label: "No data" },
  not_assessed: { tone: "neutral", label: "Not assessed" },
  high: { tone: "serious", label: "High" },
  medium: { tone: "warning", label: "Medium" },
  low: { tone: "neutral", label: "Low" },
  proceed: { tone: "good", label: "Proceed" },
  defer: { tone: "neutral", label: "Defer" },
  investigate: { tone: "warning", label: "Investigate" },
  escalate: { tone: "serious", label: "Escalate" },
  block: { tone: "critical", label: "Block" },
  open: { tone: "warning", label: "New" },
  acknowledged: { tone: "info", label: "In progress" },
  resolved: { tone: "good", label: "Resolved" },
  passed: { tone: "good", label: "Passed" },
  concern: { tone: "warning", label: "Concern" },
  failed: { tone: "critical", label: "Failed" },
  overdue: { tone: "critical", label: "Overdue" },
  revoked: { tone: "neutral", label: "Revoked" },
  active: { tone: "good", label: "Active" },
};

export function toneOf(status: string | null | undefined): Tone {
  return (status && STATUS[status]?.tone) || "neutral";
}

export function statusLabel(status: string | null | undefined): string {
  if (!status) return "Not assessed";
  return STATUS[status]?.label ?? humanize(status);
}

export function Badge({ status, tone, children, large = false }: { status?: string | null; tone?: Tone; children?: ReactNode; large?: boolean }) {
  const t = tone ?? toneOf(status);
  const Icon = TONE_ICON[t];
  return (
    <span className={`badge${large ? " badge-lg" : ""}`} data-tone={t}>
      <Icon size={large ? 16 : 14} strokeWidth={1.75} aria-hidden />
      {children ?? statusLabel(status)}
    </span>
  );
}

export function ToneIcon({ tone, size = 16 }: { tone: Tone; size?: number }) {
  const Icon = TONE_ICON[tone];
  const color = tone === "info" ? "var(--accent)" : tone === "neutral" ? "var(--text-muted)" : `var(--${tone})`;
  return <Icon size={size} strokeWidth={1.75} style={{ color }} aria-hidden />;
}

// ── Formatting (§9) ────────────────────────────────────────

export function humanize(code: string | null | undefined): string {
  if (!code) return "";
  const s = code.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function pct(x: number | null | undefined, digits = 0): string {
  return x === null || x === undefined ? "Not recorded" : `${(x * 100).toFixed(digits)}%`;
}

export function absolute(iso: string | null | undefined): string {
  if (!iso) return "Not recorded";
  return new Date(iso).toLocaleString("en-GB", {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZoneName: "short",
  });
}

export function relative(iso: string, now: number = Date.now()): string {
  const diff = new Date(iso).getTime() - now;
  const m = Math.round(Math.abs(diff) / 60000);
  const text = m < 1 ? "under a minute" : m < 60 ? `${m} min` : m < 1440 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${Math.floor(m / 1440)} d`;
  return diff >= 0 ? `in ${text}` : `${text} ago`;
}

export function Time({ iso, now }: { iso: string | null | undefined; now?: number }) {
  if (!iso) return <span className="t-muted">Not recorded</span>;
  return <time dateTime={iso} title={absolute(iso)}>{relative(iso, now)}</time>;
}

export function who(subject: string | null | undefined): string {
  return (subject ?? "").replace(/^api_key:[0-9a-f]+:/, "").replace(/^oidc:/, "").replace(/^system:/, "System · ") || "Unknown";
}

/** "Finance, Banking and Capital Markets Sector" → "Finance". */
export function sectorName(name: string): string {
  return name.replace(/ Sector$/, "").split(/,| and /)[0] ?? name;
}

export const SECTOR_ORDER = ["health", "agriculture", "finance", "energy", "transport", "education", "governance", "ports"];

// ── Page template (§4.2) ───────────────────────────────────

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}

export function ContextBar({ children, meta }: { children?: ReactNode; meta?: ReactNode }) {
  return (
    <div className="context-bar" role="region" aria-label="Filters">
      {children}
      {meta ? <div className="context-meta">{meta}</div> : null}
    </div>
  );
}

export function Kpis({ children, count }: { children: ReactNode; count: number }) {
  return (
    <div className="kpis" style={{ ["--n" as string]: count }} role="region" aria-label="Summary">
      {children}
    </div>
  );
}

export function Kpi({ label, value, context }: { label: string; value: ReactNode; context?: ReactNode }) {
  return (
    <div className="kpi">
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">{value}</span>
      {context ? <span className="kpi-context">{context}</span> : null}
    </div>
  );
}

export function Section({ title, description, actions, children, id }: { title: string; description?: ReactNode; actions?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section className="section" aria-labelledby={id ? `${id}-title` : undefined} id={id}>
      <div className="section-head">
        <div>
          <h2 id={id ? `${id}-title` : undefined}>{title}</h2>
          {description ? <p>{description}</p> : null}
        </div>
        {actions ? <div className="row">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}

export function Notice({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <div className="notice" data-tone={tone} role={tone === "critical" ? "alert" : "status"}>
      <ToneIcon tone={tone} />
      <div>{children}</div>
    </div>
  );
}

export function ErrorNotice({ error }: { error: Error | null | undefined }) {
  if (!error) return null;
  return <Notice tone="critical">{error.message.replace(/^\d+: /, "")}</Notice>;
}

export function EmptyState({ icon: Icon = CircleDashed, title, children, action }: { icon?: LucideIcon; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <Icon size={24} strokeWidth={1.75} aria-hidden />
      <span className="t-strong">{title}</span>
      {children ? <span className="t-small t-muted">{children}</span> : null}
      {action ? <div style={{ marginTop: 12 }}>{action}</div> : null}
    </div>
  );
}

export function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="card-pad stack" role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton" style={{ width: `${92 - i * 9}%` }} />)}
    </div>
  );
}

export function Segmented<T extends string | number>({ options, value, onChange, label }: { options: { value: T; label: string }[]; value: T; onChange: (v: T) => void; label: string }) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={String(o.value)} type="button" aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { value: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.value} type="button" role="tab" className="tab" aria-selected={t.value === value} onClick={() => onChange(t.value)}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

function useEscape(onClose: () => void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
}

export function Drawer({ title, eyebrow, status, onClose, children }: { title: string; eyebrow?: string; status?: ReactNode; onClose: () => void; children: ReactNode }) {
  useEscape(onClose);
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={title}>
        <div className="drawer-head">
          <div className="stack-sm">
            {eyebrow ? <span className="t-caption t-muted">{eyebrow}</span> : null}
            <h2>{title}</h2>
            {status ? <div className="row">{status}</div> : null}
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close" autoFocus>
            <X size={20} strokeWidth={1.75} />
          </button>
        </div>
        <div className="drawer-body">{children}</div>
      </aside>
    </>
  );
}

export function Dialog({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEscape(onClose);
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div className="dialog" role="dialog" aria-modal="true" aria-label={title}>
        <h2>{title}</h2>
        {children}
      </div>
    </>
  );
}

export function Meter({ value, tone }: { value: number | null | undefined; tone?: "critical" | "warning" }) {
  if (value === null || value === undefined) return <span className="t-muted">Not recorded</span>;
  return (
    <span className="meter-row">
      <span className="meter" data-tone={tone} style={{ width: 64 }} aria-hidden><span style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} /></span>
      <span className="t-num">{pct(value)}</span>
    </span>
  );
}
