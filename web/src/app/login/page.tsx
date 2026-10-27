"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Notice } from "@/components/ui";
import { useSession } from "@/lib/session";

export default function LoginPage() {
  const { signIn } = useSession();
  const router = useRouter();
  const [key, setKeyValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(key.trim());
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message.replace(/^\d+: /, "") : String(err));
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <div className="card login-card">
        <div className="wordmark" style={{ padding: 0 }}>
          <span className="brand-mark" aria-hidden>Ω</span>
          <span className="wordmark-text">
            <strong>ANT-OS Ω</strong>
            <span>AFRICA-OS Ω decision intelligence</span>
          </span>
        </div>
        <h1 style={{ fontSize: 20, lineHeight: "28px" }}>Sign in to ANT-OS</h1>
        <form className="stack" onSubmit={submit}>
          <label className="field">
            <span>Access key</span>
            <input className="control" type="password" autoComplete="off" spellCheck={false} value={key} onChange={(e) => setKeyValue(e.target.value)} required autoFocus />
          </label>
          {error ? <Notice tone="critical">{error}</Notice> : null}
          <button className="btn btn-primary" type="submit" disabled={busy || !key.trim()} aria-busy={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
        <p className="t-caption t-muted">Your key is kept only in this browser tab and cleared when you close it.</p>
      </div>
    </main>
  );
}
