"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export interface Crumb {
  label: string;
  href?: string;
}

const CrumbsContext = createContext<{ crumbs: Crumb[] | null; set: (c: Crumb[] | null) => void } | null>(null);

export function CrumbsProvider({ children }: { children: ReactNode }) {
  const [crumbs, set] = useState<Crumb[] | null>(null);
  return <CrumbsContext.Provider value={{ crumbs, set }}>{children}</CrumbsContext.Provider>;
}

export function useCrumbState(): Crumb[] | null {
  return useContext(CrumbsContext)?.crumbs ?? null;
}

/** A page declares its breadcrumb trail; the header renders it. */
export function useCrumbs(crumbs: Crumb[]): void {
  const ctx = useContext(CrumbsContext);
  const key = JSON.stringify(crumbs);
  useEffect(() => {
    ctx?.set(JSON.parse(key) as Crumb[]);
    return () => ctx?.set(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
}
