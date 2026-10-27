// Thin client for the ANT-OS API (proxied at /api by next.config.ts).
//
// Sign-in is by API key for now, held in sessionStorage so it is cleared when
// the tab closes. Keycloak (OIDC + PKCE, client "antos-web") replaces this
// before any deployment beyond the pilot.

const KEY_STORAGE = "antos.apiKey";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`${status}: ${detail}`);
  }
}

export function getKey(): string | null {
  try {
    return sessionStorage.getItem(KEY_STORAGE);
  } catch {
    return null;
  }
}

export function setKey(key: string): void {
  try {
    sessionStorage.setItem(KEY_STORAGE, key);
  } catch {
    // Storage blocked: the key lives only for this page view.
  }
}

export function clearKey(): void {
  try {
    sessionStorage.removeItem(KEY_STORAGE);
  } catch {
    /* nothing to clear */
  }
}

function describe(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d: { loc?: unknown[]; msg?: string }) =>
          [d.loc?.slice(1).join("."), d.msg].filter(Boolean).join(": "),
        )
        .join("; ");
    }
  }
  return fallback;
}

export async function api<T>(
  path: string,
  init: { method?: string; body?: unknown; key?: string } = {},
): Promise<T> {
  const key = init.key ?? getKey();
  const res = await fetch(`/api${path}`, {
    method: init.method ?? (init.body === undefined ? "GET" : "POST"),
    headers: {
      ...(init.body === undefined ? {} : { "Content-Type": "application/json" }),
      ...(key ? { "X-API-Key": key } : {}),
    },
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
    cache: "no-store",
  });
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, describe(body, res.statusText));
  }
  return (await res.json()) as T;
}
