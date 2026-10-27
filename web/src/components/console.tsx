"use client";

import { ArrowLeft, CircleDashed, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, type ReactNode } from "react";

/* Split-panel console: a list pane and a detail pane on one screen.
 * The selection lives in the URL so it survives reloads and can be shared. */

export function SplitView({ hasSelection, wideList = false, stackOnMobile = false, children }: {
  hasSelection: boolean; wideList?: boolean;
  /** On phones, show both panes stacked (detail first) until something is selected. */
  stackOnMobile?: boolean; children: ReactNode;
}) {
  return (
    <div className="split" data-has-selection={hasSelection} data-wide-list={wideList} data-stack={stackOnMobile}>
      {children}
    </div>
  );
}

export function Pane({ kind, title, count, actions, toolbar, back, label, children }: {
  kind: "list" | "detail"; title?: ReactNode; count?: number | null; actions?: ReactNode; toolbar?: ReactNode;
  /** On narrow screens the detail pane covers the list; this link returns to it. */
  back?: string; label?: string; children: ReactNode;
}) {
  const Heading = kind === "list" ? "h1" : "h2";
  return (
    <section className={`pane pane-${kind}`} aria-label={label ?? (typeof title === "string" ? title : undefined)}>
      {title !== undefined || actions ? (
        <header className="pane-head">
          <div className="row" style={{ gap: 8, minWidth: 0 }}>
            {back ? <Link href={back} className="icon-button pane-back" aria-label="Back to list"><ArrowLeft size={16} strokeWidth={1.5} /></Link> : null}
            <Heading>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{title}</span>
              {count !== undefined && count !== null ? <span className="count">{count}</span> : null}
            </Heading>
          </div>
          {actions ? <div className="row" style={{ gap: 6, flex: "none" }}>{actions}</div> : null}
        </header>
      ) : null}
      {toolbar ? <div className="pane-toolbar" role="region" aria-label="Filters">{toolbar}</div> : null}
      <div className="pane-body">{children}</div>
    </section>
  );
}

/** A selectable row in a list pane. Keeps itself scrolled into view when selected. */
export function ListItem({ href, selected, title, aside, meta, bar }: {
  href: string; selected: boolean; title: ReactNode; aside?: ReactNode; meta?: ReactNode; bar?: ReactNode;
}) {
  const ref = useRef<HTMLAnchorElement>(null);
  useEffect(() => {
    if (selected) ref.current?.scrollIntoView({ block: "nearest" });
  }, [selected]);
  return (
    <li>
      <Link ref={ref} href={href} scroll={false} className="list-item" aria-current={selected ? "true" : undefined}>
        <span className="li-title">{title}</span>
        <span className="li-aside">{aside}</span>
        {meta ? <span className="li-meta">{meta}</span> : null}
        {bar ? <span className="li-bar">{bar}</span> : null}
      </Link>
    </li>
  );
}

export function ListSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="list-item" style={{ cursor: "default" }}>
          <div className="skeleton" style={{ width: `${80 - (i % 3) * 14}%` }} />
          <span />
          <div className="skeleton" style={{ width: "40%", height: 10, gridColumn: "1 / -1" }} />
        </div>
      ))}
    </div>
  );
}

export function DetailEmpty({ icon: Icon = CircleDashed, title, children }: { icon?: LucideIcon; title: string; children?: ReactNode }) {
  return (
    <div className="detail-empty">
      <div>
        <span className="empty-icon" aria-hidden><Icon strokeWidth={1.5} /></span>
        <div className="t-strong" style={{ color: "var(--text)" }}>{title}</div>
        {children ? <p className="t-small" style={{ marginTop: 4, maxWidth: "40ch" }}>{children}</p> : null}
      </div>
    </div>
  );
}

/** Builds links that change one query parameter and keep the rest (filters, tab). */
export function useSelectHref(name: string, path?: string) {
  const params = useSearchParams();
  const pathname = usePathname();
  return useCallback(
    (value: string | null, drop: string[] = []) => {
      const next = new URLSearchParams(params.toString());
      if (value === null) next.delete(name);
      else next.set(name, value);
      for (const d of drop) next.delete(d);
      const qs = next.toString();
      const base = path ?? pathname;
      return qs ? `${base}?${qs}` : base;
    },
    [params, pathname, name, path],
  );
}
