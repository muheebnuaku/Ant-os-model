"use client";

import { Command } from "cmdk";
import {
  FileCheck2,
  FilePlus2,
  Inbox,
  KeyRound,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Moon,
  Radio,
  Search,
  Settings2,
  Sun,
} from "lucide-react";
import { useRouter } from "next/navigation";

import { useApi } from "@/lib/hooks";
import { CAN, useSession } from "@/lib/session";
import type { ThemeChoice } from "@/lib/theme";
import type { DecisionSummary, Sector } from "@/lib/types";

import { sectorName, statusLabel } from "./ui";

/* Global search (§4.1): grouped results — Pages, Sectors, Decisions, Actions. */

export function CommandPalette({ open, onOpenChange, onTheme }: { open: boolean; onOpenChange: (o: boolean) => void; onTheme: (t: ThemeChoice) => void }) {
  const router = useRouter();
  const { can, signOut } = useSession();
  const sectors = useApi<Sector[]>(open ? "/v1/sectors" : null);
  const recent = useApi<DecisionSummary[]>(open && can(CAN.readDecisions) ? "/v1/decisions?limit=20" : null);

  const go = (path: string) => {
    onOpenChange(false);
    router.push(path);
  };
  const icon = { size: 16, strokeWidth: 1.75, "aria-hidden": true } as const;

  const pages = [
    { href: "/", label: "Briefing", Icon: LayoutDashboard, need: CAN.situation },
    { href: "/escalations", label: "Review queue", Icon: Inbox, need: null },
    { href: "/decisions", label: "Decisions", Icon: ListChecks, need: CAN.readDecisions },
    { href: "/decisions/new", label: "New decision", Icon: FilePlus2, need: CAN.decide },
    { href: "/signals", label: "Signals", Icon: Radio, need: CAN.signals },
    { href: "/audit", label: "Records & verification", Icon: FileCheck2, need: CAN.audit },
    { href: "/admin/rules", label: "Rules & configuration", Icon: Settings2, need: CAN.configRead },
    { href: "/admin/access", label: "Access & keys", Icon: KeyRound, need: CAN.manageKeys },
  ].filter((p) => p.need === null || can(p.need));

  return (
    <Command.Dialog open={open} onOpenChange={onOpenChange} label="Search" className="command" loop>
      <div className="command-input">
        <Search size={18} strokeWidth={1.75} aria-hidden />
        <Command.Input placeholder="Search decisions, sectors, records…" autoFocus />
      </div>
      <Command.List>
        <Command.Empty>No results.</Command.Empty>
        <Command.Group heading="Pages">
          {pages.map(({ href, label, Icon }) => (
            <Command.Item key={href} value={`page ${label}`} onSelect={() => go(href)}>
              <Icon {...icon} /> {label}
            </Command.Item>
          ))}
        </Command.Group>
        {can(CAN.situation) && sectors.data ? (
          <Command.Group heading="Sectors">
            {sectors.data.map((s) => (
              <Command.Item key={s.sector_id} value={`sector ${s.sector_name}`} onSelect={() => go(`/?sector=${s.sector_id}`)}>
                <LayoutDashboard {...icon} /> {sectorName(s.sector_name)}
                <span className="hint">Sector</span>
              </Command.Item>
            ))}
          </Command.Group>
        ) : null}
        {recent.data?.length ? (
          <Command.Group heading="Decisions">
            {recent.data.map((d) => (
              <Command.Item key={d.audit_ref} value={`decision ${d.objective ?? ""} ${d.sector} ${d.audit_ref}`} onSelect={() => go(`/decisions/${d.audit_ref}`)}>
                <ListChecks {...icon} />
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.objective ?? d.decision_id}</span>
                <span className="hint">{statusLabel(d.validation_state)}</span>
              </Command.Item>
            ))}
          </Command.Group>
        ) : null}
        <Command.Group heading="Actions">
          <Command.Item value="action light appearance" onSelect={() => { onTheme("light"); onOpenChange(false); }}>
            <Sun {...icon} /> Use light appearance
          </Command.Item>
          <Command.Item value="action dark appearance" onSelect={() => { onTheme("dark"); onOpenChange(false); }}>
            <Moon {...icon} /> Use dark appearance
          </Command.Item>
          <Command.Item value="action sign out" onSelect={() => { onOpenChange(false); signOut(); }}>
            <LogOut {...icon} /> Sign out
          </Command.Item>
        </Command.Group>
      </Command.List>
    </Command.Dialog>
  );
}
