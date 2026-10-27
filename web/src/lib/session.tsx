"use client";

import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { api, ApiError, clearKey, getKey, setKey } from "./api";
import { clearApiCache } from "./hooks";
import type { Me } from "./types";

// Permissions each screen needs (any one suffices); mirrors services/api app.py.
export const CAN = {
  situation: ["review_escalations", "strategic_mode_control", "audit_mode", "run_analysis"],
  decide: ["run_analysis", "trigger_allowed_prompts", "approve_sector_actions"],
  readDecisions: [
    "inspect_trails",
    "view_assigned_outputs",
    "inspect_sector_audits",
    "inspect_cross_sector_trails",
    "audit_mode",
  ],
  audit: ["audit_mode", "audit_review", "inspect_sector_audits"],
  signals: [
    "submit_signals", "submit_market_signals", "submit_research_signals",
    "inspect_trails", "view_assigned_outputs", "inspect_sector_audits",
    "inspect_cross_sector_trails", "audit_mode",
  ],
  configRead: ["config_management", "policy_threshold_control", "audit_review"],
  manageKeys: ["role_assignment"],
} as const;

interface Session {
  me: Me | null;
  ready: boolean;
  can: (perms: readonly string[]) => boolean;
  signIn: (key: string) => Promise<void>;
  signOut: () => void;
}

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!getKey()) {
      setReady(true);
      return;
    }
    api<Me>("/v1/me")
      .then(setMe)
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 401) clearKey();
      })
      .finally(() => setReady(true));
  }, []);

  useEffect(() => {
    if (ready && !me && pathname !== "/login") router.replace("/login");
  }, [ready, me, pathname, router]);

  const signIn = useCallback(async (key: string) => {
    const who = await api<Me>("/v1/me", { key });
    clearApiCache();
    setKey(key);
    setMe(who);
  }, []);

  const signOut = useCallback(() => {
    clearKey();
    clearApiCache();
    setMe(null);
    router.replace("/login");
  }, [router]);

  const can = useCallback(
    (perms: readonly string[]) => !!me && perms.some((p) => me.permissions.includes(p)),
    [me],
  );

  return (
    <SessionContext.Provider value={{ me, ready, can, signIn, signOut }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): Session {
  const s = useContext(SessionContext);
  if (!s) throw new Error("useSession must be used inside SessionProvider");
  return s;
}
