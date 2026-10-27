"use client";

import {
  FileCheck2,
  FilePlus2,
  HelpCircle,
  Inbox,
  KeyRound,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Monitor,
  Moon,
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

import { useApi } from "@/lib/hooks";
import { CAN, useSession } from "@/lib/session";
import { applyDensity, applyTheme, readDensity, readTheme, type Density, type ThemeChoice } from "@/lib/theme";
import type { Escalation, NodeStatus } from "@/lib/types";

import { CommandPalette } from "./CommandPalette";
import { relative, Segmented, who } from "./ui";

/* The console frame: charcoal icon rail, workspace, status bar. */

type NavItem = { href: string; label: string; icon: typeof Inbox; need: readonly string[] | null; count?: boolean };

const NAV: NavItem[][] = [
  [{ href: "/", label: "Briefing", icon: LayoutDashboard, need: CAN.situation }],
  [
    { href: "/escalations", label: "Review queue", icon: Inbox, need: null, count: true },
    { href: "/decisions", label: "Decisions", icon: ListChecks, need: CAN.readDecisions },
    { href: "/decisions/new", label: "New decision", icon: FilePlus2, need: CAN.decide },
    { href: "/signals", label: "Signals", icon: Radio, need: CAN.signals },
    { href: "/audit", label: "Records & verification", icon: FileCheck2, need: CAN.audit },
  ],
  [
    { href: "/admin/rules", label: "Rules & configuration", icon: Settings2, need: CAN.configRead },
    { href: "/admin/access", label: "Access & keys", icon: KeyRound, need: CAN.manageKeys },
  ],
];

/** "G" then a letter jumps to a section (shown in Help). */
export const SHORTCUTS: Record<string, string> = {
  b: "/", r: "/escalations", d: "/decisions", n: "/decisions/new", s: "/signals", a: "/audit",
};

export function Shell({ children }: { children: ReactNode }) {
  const { me, ready, can, signOut } = useSession();
  const pathname = usePathname();
  const [palette, setPalette] = useState(false);
  const [menu, setMenu] = useState(false);
  const [theme, setTheme] = useState<ThemeChoice>("system");
  const menuRef = useRef<HTMLDivElement>(null);
  const signedIn = ready && !!me && pathname !== "/login";
  const queue = useApi<Escalation[]>(signedIn ? "/v1/escalations?status=open" : null, { pollMs: 30_000 });
  const node = useApi<NodeStatus>(signedIn ? "/v1/node" : null, { pollMs: 60_000 });

  const router = useRouter();
  const search = useSearchParams();
  const [navigating, setNavigating] = useState(false);
  const firstRoute = useRef(true);

  const [density, setDensity] = useState<Density>("standard");
  useEffect(() => {
    setTheme(readTheme());
    setDensity(readDensity());
  }, []);

  // Route change finished: stop the progress bar and move focus to the new
  // page's title so keyboard and screen-reader users arrive there.
  useEffect(() => {
    setNavigating(false);
    setMenu(false);
    if (firstRoute.current) { firstRoute.current = false; return; }
    const id = requestAnimationFrame(() => {
      const h1 = document.querySelector<HTMLElement>("main h1");
      if (h1) { h1.tabIndex = -1; h1.focus({ preventScroll: true }); }
    });
    return () => cancelAnimationFrame(id);
  }, [pathname]);

  // A selection change inside a split view only stops the progress bar.
  useEffect(() => setNavigating(false), [search]);

  // Route change started: any same-origin link click to a different page.
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as HTMLElement).closest("a[href]");
      const href = a?.getAttribute("href");
      if (!a || !href?.startsWith("/") || a.getAttribute("target") === "_blank") return;
      if (new URL(href, window.location.origin).pathname !== window.location.pathname) setNavigating(true);
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
  const n = node.data;
  const sealed = !!n?.last_anchor_at;
  const name = who(me.subject);
  const roles = me.roles.map((r) => r.replace(/_/g, " ")).join(", ");
  const waiting = queue.data?.length ?? 0;

  function chooseTheme(t: ThemeChoice) {
    applyTheme(t);
    setTheme(t);
  }

  function chooseDensity(d: Density) {
    applyDensity(d);
    setDensity(d);
  }

  const groups = NAV.map((items) => items.filter((i) => i.need === null || can(i.need))).filter((g) => g.length);

  return (
    <div className="app">
      <div className="route-progress" data-active={navigating} aria-hidden />
      <nav className="rail" aria-label="Main navigation">
        <Link href="/" className="rail-mark" aria-label="ANT-OS Ω home" title="ANT-OS Ω · AFRICA-OS Ω">Ω</Link>
        {groups.map((items, gi) => (
          <Fragment key={gi}>
            {gi > 0 ? <span className="rail-sep" aria-hidden /> : null}
            {items.map(({ href, label, icon: Icon, count }) => (
              <Link key={href} href={href} className="rail-item" data-tip={label} aria-label={label}
                aria-current={isActive(href) ? "page" : undefined}>
                <Icon strokeWidth={1.5} aria-hidden />
                {count && waiting ? <span className="rail-badge" aria-label={`${waiting} waiting`}>{waiting > 99 ? "99+" : waiting}</span> : null}
              </Link>
            ))}
          </Fragment>
        ))}
        <span className="rail-spacer" />
        <button type="button" className="rail-item" data-tip="Search  Ctrl K" aria-label="Search (Ctrl+K)" onClick={() => setPalette(true)}>
          <Search strokeWidth={1.5} aria-hidden />
        </button>
        <Link href="/help" className="rail-item" data-tip="Help" aria-label="Help" aria-current={pathname === "/help" ? "page" : undefined}>
          <HelpCircle strokeWidth={1.5} aria-hidden />
        </Link>
        <div ref={menuRef}>
          <button type="button" className="rail-item" data-tip={menu ? undefined : name} aria-haspopup="menu" aria-expanded={menu}
            aria-label="Account menu" onClick={() => setMenu((m) => !m)}>
            <span className="avatar" aria-hidden>{name.slice(0, 2).toUpperCase()}</span>
          </button>
          {menu ? (
            <div className="menu rail-menu" role="menu">
              <div style={{ padding: "8px 12px" }}>
                <div className="t-strong">{name}</div>
                <div className="t-caption t-muted" style={{ textTransform: "capitalize" }}>{roles}</div>
                <div className="t-caption t-muted">{me.nation_id === "GH" ? "Ghana" : me.nation_id ?? "All nations"} · AFRICA-OS Ω</div>
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
      </nav>

      <div className="main">
        <main className="workspace" id="main">
          <div key={pathname} className="page-enter content">{children}</div>
        </main>

        <footer className="statusbar">
          <span className="grow">ANT-OS Ω / AFRICA-OS Ω, the VPF and the 24-Hour Africa Economy Policy are the work of Dr. David King Boison.</span>
          {n ? (
            <Link href={can(CAN.audit) ? "/audit" : "/help"} title={sealed ? `Last sealed ${relative(n.last_anchor_at!)} · ${n.entries_since_anchor} records since` : "Records have not been sealed yet"}>
              {sealed ? <ShieldCheck strokeWidth={1.5} style={{ color: "var(--good)" }} aria-hidden /> : <ShieldAlert strokeWidth={1.5} style={{ color: "var(--warning)" }} aria-hidden />}
              {sealed ? `Sealed ${relative(n.last_anchor_at!)}` : "Not yet sealed"}
            </Link>
          ) : null}
          {n ? <span className="hide-sm">Engine {n.engine_version} · Rules {n.manifest_version} · Node {n.node_id}</span> : null}
        </footer>
      </div>

      <CommandPalette open={palette} onOpenChange={setPalette} onTheme={chooseTheme} />
    </div>
  );
}
