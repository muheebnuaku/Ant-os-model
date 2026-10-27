"use client";

import {
  ChevronDown,
  FileCheck2,
  FilePlus2,
  HelpCircle,
  Inbox,
  KeyRound,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  Monitor,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Radio,
  Search,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  Sun,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";

import { useCrumbState, type Crumb } from "@/lib/crumbs";
import { useApi } from "@/lib/hooks";
import { CAN, useSession } from "@/lib/session";
import { applyDensity, applyTheme, readDensity, readTheme, type Density, type ThemeChoice } from "@/lib/theme";
import type { Escalation, NodeStatus } from "@/lib/types";

import { CommandPalette } from "./CommandPalette";
import { relative, Segmented, who } from "./ui";

/* The application frame (§4.1): sidebar, header bar, content, footer. */

type NavItem = { href: string; label: string; icon: typeof Inbox; need: readonly string[] | null; count?: boolean };

const NAV: { group: string; items: NavItem[] }[] = [
  { group: "Overview", items: [{ href: "/", label: "Briefing", icon: LayoutDashboard, need: CAN.situation }] },
  {
    group: "Operations",
    items: [
      { href: "/escalations", label: "Review queue", icon: Inbox, need: null, count: true },
      { href: "/decisions", label: "Decisions", icon: ListChecks, need: CAN.readDecisions },
      { href: "/decisions/new", label: "New decision", icon: FilePlus2, need: CAN.decide },
    ],
  },
  { group: "Evidence", items: [{ href: "/signals", label: "Signals", icon: Radio, need: CAN.signals }] },
  { group: "Assurance", items: [{ href: "/audit", label: "Records & verification", icon: FileCheck2, need: CAN.audit }] },
  {
    group: "Administration",
    items: [
      { href: "/admin/rules", label: "Rules & configuration", icon: Settings2, need: CAN.configRead },
      { href: "/admin/access", label: "Access & keys", icon: KeyRound, need: CAN.manageKeys },
    ],
  },
];

/** "G" then a letter jumps to a section (shown in Help). */
export const SHORTCUTS: Record<string, string> = {
  b: "/", r: "/escalations", d: "/decisions", n: "/decisions/new", s: "/signals", a: "/audit",
};

const PATH_LABELS: Record<string, Crumb[]> = {
  "/": [{ label: "Briefing" }],
  "/escalations": [{ label: "Review queue" }],
  "/decisions": [{ label: "Decisions" }],
  "/decisions/new": [{ label: "Decisions", href: "/decisions" }, { label: "New decision" }],
  "/signals": [{ label: "Signals" }],
  "/audit": [{ label: "Records & verification" }],
  "/admin/rules": [{ label: "Administration" }, { label: "Rules & configuration" }],
  "/admin/access": [{ label: "Administration" }, { label: "Access & keys" }],
  "/help": [{ label: "Help" }],
};

export function Shell({ children }: { children: ReactNode }) {
  const { me, ready, can, signOut } = useSession();
  const pathname = usePathname();
  const pageCrumbs = useCrumbState();
  const [palette, setPalette] = useState(false);
  const [menu, setMenu] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [theme, setTheme] = useState<ThemeChoice>("system");
  const menuRef = useRef<HTMLDivElement>(null);
  const signedIn = ready && !!me && pathname !== "/login";
  const queue = useApi<Escalation[]>(signedIn ? "/v1/escalations?status=open" : null, { pollMs: 30_000 });
  const node = useApi<NodeStatus>(signedIn ? "/v1/node" : null, { pollMs: 60_000 });

  const router = useRouter();
  const search = useSearchParams();
  const [navigating, setNavigating] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const firstRoute = useRef(true);

  const [density, setDensity] = useState<Density>("standard");
  useEffect(() => {
    setTheme(readTheme());
    setDensity(readDensity());
    try { setCollapsed(localStorage.getItem("antos.sidebar") === "collapsed"); } catch { /* default */ }
  }, []);

  // Route change finished: stop the progress bar, close mobile nav, and move
  // focus to the new page's title so keyboard and screen-reader users arrive there.
  useEffect(() => {
    setNavigating(false);
    setNavOpen(false);
    if (firstRoute.current) { firstRoute.current = false; return; }
    const id = requestAnimationFrame(() => {
      const h1 = document.querySelector<HTMLElement>("main h1");
      if (h1) { h1.tabIndex = -1; h1.focus({ preventScroll: true }); }
    });
    return () => cancelAnimationFrame(id);
  }, [pathname, search]);

  // Route change started: any same-origin link click to a different page.
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as HTMLElement).closest("a[href]");
      const href = a?.getAttribute("href");
      if (!a || !href?.startsWith("/") || a.getAttribute("target") === "_blank") return;
      if (href.split("#")[0] !== `${window.location.pathname}${window.location.search}`) setNavigating(true);
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);
  useEffect(() => {
    if (!navigating) return;
    const id = setTimeout(() => setNavigating(false), 8000);
    return () => clearTimeout(id);
  }, [navigating]);

  useEffect(() => {
    let pendingG = 0;
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((p) => !p);
        return;
      }
      if (e.key === "Escape") setMenu(false);
      const el = e.target as HTMLElement;
      if (e.metaKey || e.ctrlKey || e.altKey || el.closest("input, textarea, select, [contenteditable='true']")) return;
      const k = e.key.toLowerCase();
      if (k === "g") { pendingG = Date.now(); return; }
      if (Date.now() - pendingG < 1200 && SHORTCUTS[k]) {
        pendingG = 0;
        e.preventDefault();
        setNavigating(true);
        router.push(SHORTCUTS[k]);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router]);

  function toggleCollapsed() {
    setCollapsed((c) => {
      try { localStorage.setItem("antos.sidebar", c ? "expanded" : "collapsed"); } catch { /* not remembered */ }
      return !c;
    });
  }
  useEffect(() => {
    if (!menu) return;
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenu(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [menu]);

  if (pathname === "/login") return <>{children}</>;
  if (!ready || !me) return <div className="login"><p className="t-muted">Checking your session…</p></div>;

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : href === "/decisions" ? pathname === "/decisions" || /^\/decisions\/(?!new)/.test(pathname) : pathname.startsWith(href);
  const crumbs = pageCrumbs ?? PATH_LABELS[pathname] ?? [];
  const n = node.data;
  const sealed = !!n?.last_anchor_at;
  const name = who(me.subject);
  const roles = me.roles.map((r) => r.replace(/_/g, " ")).join(", ");

  function chooseTheme(t: ThemeChoice) {
    applyTheme(t);
    setTheme(t);
  }

  function chooseDensity(d: Density) {
    applyDensity(d);
    setDensity(d);
  }

  return (
    <div className="app" data-collapsed={collapsed}>
      <div className="route-progress" data-active={navigating} aria-hidden />
      <aside className="sidebar" data-open={navOpen} aria-label="Main navigation">
        <div className="wordmark">
          <span className="brand-mark" aria-hidden>Ω</span>
          <span className="wordmark-text">
            <strong>ANT-OS Ω</strong>
            <span>{me.nation_id === "GH" ? "Ghana" : me.nation_id ?? "All nations"} · AFRICA-OS Ω</span>
          </span>
        </div>
        <nav>
          {NAV.map(({ group, items }) => {
            const visible = items.filter((i) => i.need === null || can(i.need));
            if (!visible.length) return null;
            return (
              <div key={group} className="nav-group">
                <div className="nav-group-label">{group}</div>
                {visible.map(({ href, label, icon: Icon, count }) => (
                  <Link key={href} href={href} className="nav-item" aria-current={isActive(href) ? "page" : undefined} title={label}>
                    <Icon size={20} strokeWidth={1.5} aria-hidden />
                    <span className="nav-label">{label}</span>
                    {count && queue.data?.length ? <span className="nav-count" aria-label={`${queue.data.length} waiting`}>{queue.data.length}</span> : null}
                  </Link>
                ))}
              </div>
            );
          })}
        </nav>
        <div className="sidebar-foot">
          <Link href="/help" className="nav-item" aria-current={pathname === "/help" ? "page" : undefined} title="Help">
            <HelpCircle size={20} strokeWidth={1.5} aria-hidden />
            <span className="nav-label">Help</span>
          </Link>
          <button type="button" className="nav-item collapse-toggle" onClick={toggleCollapsed}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} title={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
            {collapsed ? <PanelLeftOpen size={20} strokeWidth={1.5} aria-hidden /> : <PanelLeftClose size={20} strokeWidth={1.5} aria-hidden />}
            <span className="nav-label">Collapse sidebar</span>
          </button>
          <div className="sidebar-user" title={`${name} · ${roles}`}>
            <span className="avatar" aria-hidden>{name.slice(0, 2).toUpperCase()}</span>
            <span className="sidebar-user-text">
              <strong>{name}</strong>
              <span>{roles}</span>
            </span>
          </div>
        </div>
      </aside>
      {navOpen ? <div className="scrim" style={{ zIndex: 39 }} onClick={() => setNavOpen(false)} /> : null}

      <div className="main">
        <header className="header">
          <button type="button" className="icon-button menu-toggle" aria-label="Open navigation" onClick={() => setNavOpen(true)}>
            <Menu size={20} strokeWidth={1.5} />
          </button>
          <nav className="breadcrumb" aria-label="Breadcrumb">
            {crumbs.map((c, i) => (
              <Fragment key={`${c.label}${i}`}>
                {i > 0 ? <span className="breadcrumb-sep" aria-hidden>/</span> : null}
                {i === crumbs.length - 1 ? <span aria-current="page">{c.label}</span> : c.href ? <Link href={c.href}>{c.label}</Link> : <span>{c.label}</span>}
              </Fragment>
            ))}
          </nav>
          <div className="header-spacer" />
          <button type="button" className="search-button" onClick={() => setPalette(true)} aria-label="Search (Ctrl+K)">
            <Search size={16} strokeWidth={1.5} aria-hidden />
            <span className="search-label">Search decisions, sectors, records…</span>
            <kbd>Ctrl K</kbd>
          </button>
          {n ? (
            <Link href={can(CAN.audit) ? "/audit" : "/help"} className="node-status" title={sealed ? `Last sealed ${relative(n.last_anchor_at!)} · ${n.entries_since_anchor} records since` : "Records have not been sealed yet"}>
              {sealed ? <ShieldCheck size={16} strokeWidth={1.5} style={{ color: "var(--good)" }} aria-hidden /> : <ShieldAlert size={16} strokeWidth={1.5} style={{ color: "var(--warning)" }} aria-hidden />}
              <span className="node-label">{sealed ? `Records verified · sealed ${relative(n.last_anchor_at!)}` : "Records not yet sealed"}</span>
            </Link>
          ) : null}
          <div ref={menuRef} style={{ position: "relative" }}>
            <button type="button" className="user-button" aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>
              <span className="avatar" aria-hidden>{name.slice(0, 2).toUpperCase()}</span>
              <ChevronDown size={16} strokeWidth={1.5} aria-hidden />
              <span className="sr-only">Account menu</span>
            </button>
            {menu ? (
              <div className="menu" role="menu">
                <div style={{ padding: "8px 12px" }}>
                  <div className="t-strong">{name}</div>
                  <div className="t-caption t-muted" style={{ textTransform: "capitalize" }}>{roles}</div>
                </div>
                <hr className="divider" style={{ margin: "4px 0" }} />
                <div className="menu-label">Appearance</div>
                {([["system", "Match device", Monitor], ["light", "Light", Sun], ["dark", "Dark", Moon]] as const).map(([v, t, Icon]) => (
                  <button key={v} type="button" role="menuitemradio" aria-checked={theme === v} className="menu-item" onClick={() => chooseTheme(v)}>
                    <Icon size={16} strokeWidth={1.5} aria-hidden /> {t}
                    {theme === v ? <span style={{ marginLeft: "auto" }} aria-hidden>✓</span> : null}
                  </button>
                ))}
                <hr className="divider" style={{ margin: "4px 0" }} />
                <div className="menu-label">Density</div>
                <div style={{ padding: "4px 8px 8px" }}>
                  <Segmented<Density> label="Density" value={density} onChange={chooseDensity}
                    options={[{ value: "compact", label: "Compact" }, { value: "standard", label: "Standard" }, { value: "comfortable", label: "Comfortable" }]} />
                </div>
                <hr className="divider" style={{ margin: "4px 0" }} />
                <button type="button" role="menuitem" className="menu-item" onClick={signOut}>
                  <LogOut size={16} strokeWidth={1.5} aria-hidden /> Sign out
                </button>
              </div>
            ) : null}
          </div>
        </header>

        <main className="content" id="main">
          <div key={pathname} className="page-enter">{children}</div>
        </main>

        <footer className="footer">
          <span>ANT-OS Ω / AFRICA-OS Ω, the VPF and the 24-Hour Africa Economy Policy are the work of Dr. David King Boison.</span>
          <span>{n ? `Engine ${n.engine_version} · Rules ${n.manifest_version} · Node ${n.node_id}` : null}</span>
        </footer>
      </div>

      <CommandPalette open={palette} onOpenChange={setPalette} onTheme={chooseTheme} />
    </div>
  );
}
