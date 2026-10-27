"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "./api";

/* Data loading with a stale-while-revalidate cache: a page shows the last data
   it had immediately (no loading flash when navigating back) and refreshes in
   the background. Changing filters keeps the previous result on screen, dimmed,
   until the new one arrives. */

const cache = new Map<string, unknown>();

export function clearApiCache(): void {
  cache.clear();
}

export interface Loaded<T> {
  data: T | null;
  error: ApiError | Error | null;
  loading: boolean;
  /** Loading while older data is still shown. */
  refreshing: boolean;
  reload: () => void;
}

export function useApi<T>(path: string | null, opts: { pollMs?: number; body?: unknown } = {}): Loaded<T> {
  const { pollMs } = opts;
  const bodyKey = opts.body === undefined ? undefined : JSON.stringify(opts.body);
  const key = path === null ? null : `${path}|${bodyKey ?? ""}`;
  const [data, setData] = useState<T | null>(() => (key ? ((cache.get(key) as T | undefined) ?? null) : null));
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const [tick, setTick] = useState(0);
  const latest = useRef(0);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    if (path === null || key === null) return;
    const cached = cache.get(key) as T | undefined;
    if (cached !== undefined) setData(cached);
    const call = ++latest.current;
    setLoading(true);
    api<T>(path, bodyKey === undefined ? {} : { body: JSON.parse(bodyKey) as unknown })
      .then((d) => {
        cache.set(key, d);
        if (call === latest.current) {
          setData(d);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (call === latest.current) setError(e instanceof Error ? e : new Error(String(e)));
      })
      .finally(() => {
        if (call === latest.current) setLoading(false);
      });
  }, [path, key, bodyKey, tick]);

  useEffect(() => {
    if (!pollMs || path === null) return;
    const id = setInterval(() => {
      if (document.visibilityState === "visible") reload();
    }, pollMs);
    return () => clearInterval(id);
  }, [pollMs, path, reload]);

  return { data, error, loading, refreshing: loading && data !== null, reload };
}

/** Re-render every `ms` so relative times (deadlines) stay current. */
export function useNow(ms = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(id);
  }, [ms]);
  return now;
}

/** A piece of page state kept in the URL, so Back, refresh and shared links
 *  return to the same view. The default value is left out of the URL. */
export function useQueryState<T extends string = string>(name: string, fallback: NoInfer<T>): [T, (v: T) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const value = (params.get(name) as T | null) ?? fallback;
  const set = useCallback(
    (v: T) => {
      const next = new URLSearchParams(params.toString());
      if (v === fallback) next.delete(name);
      else next.set(name, v);
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, router, pathname, name, fallback],
  );
  return [value, set];
}
