"use client";

import { Copy } from "lucide-react";
import { useState, type FormEvent } from "react";

import { DataTable } from "@/components/DataTable";
import { Badge, CancelButton, Dialog, ErrorNotice, Kpi, Kpis, Notice, PageHeader, Section, Time, humanize, who } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi, useNow } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { useToast } from "@/lib/toast";
import type { ApiKeyRow } from "@/lib/types";

// Mirrors profiles/africa/roles.yaml.
const ROLES = [
  "operator", "analyst", "sector_lead", "regulator", "administrator", "developer",
  "sovereign_admin", "entrepreneur", "university_researcher", "citizen_observer",
];

export default function AccessPage() {
  const { me } = useSession();
  const toast = useToast();
  const now = useNow(60_000);
  const keys = useApi<ApiKeyRow[]>("/v1/admin/api-keys");
  const [issuing, setIssuing] = useState(false);
  const [name, setName] = useState("");
  const [roles, setRoles] = useState<string[]>([]);
  const [issued, setIssued] = useState<{ token: string; name: string } | null>(null);
  const [revoking, setRevoking] = useState<ApiKeyRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [copied, setCopied] = useState(false);

  const list = keys.data ?? [];
  const active = list.filter((k) => !k.revoked_at);

  async function issue(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const out = await api<{ token: string }>("/v1/admin/api-keys", { body: { name: name.trim(), roles, nation_id: me?.nation_id ?? null } });
      setIssued({ token: out.token, name: name.trim() });
      toast(`Access key issued: ${name.trim()}`);
      setIssuing(false);
      setName("");
      setRoles([]);
      keys.reload();
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(k: ApiKeyRow) {
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/admin/api-keys/${k.key_id}/revoke`, { method: "POST" });
      toast(`Access key revoked: ${k.name}`);
      setRevoking(null);
      keys.reload();
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <PageHeader title="Access & keys" description="Access keys for systems and staff. Staff will move to single sign-on before go-live."
        actions={<button type="button" className="btn btn-primary" onClick={() => setIssuing(true)}>Issue access key</button>} />

      <Kpis count={3}>
        <Kpi label="Active keys" value={active.length} />
        <Kpi label="Revoked keys" value={list.length - active.length} />
        <Kpi label="Nation" value={me?.nation_id === "GH" ? "Ghana" : me?.nation_id ?? "All"} context="Keys you issue are bound to it" />
      </Kpis>

      <ErrorNotice error={keys.error ?? error} />

      <Section title="Keys" description="Secrets are never stored or shown again after issue.">
        <div className="card">
          <DataTable caption="Access keys" rows={keys.data} loading={keys.loading} rowKey={(k) => k.key_id}
            empty={{ title: "No keys issued" }}
            columns={[
              { key: "n", header: "Name", render: (k) => <><div className="cell-primary">{k.name}</div><div className="cell-secondary">Issued by {who(k.created_by)}</div></> },
              { key: "r", header: "Roles", render: (k) => k.roles.map(humanize).join(", ") },
              { key: "c", header: "Issued", render: (k) => <Time iso={k.created_at} now={now} /> },
              { key: "s", header: "Status", render: (k) => <Badge status={k.revoked_at ? "revoked" : "active"} /> },
              { key: "a", header: "", render: (k) => (k.revoked_at ? null : <button type="button" className="btn btn-compact btn-danger" onClick={() => setRevoking(k)}>Revoke</button>) },
            ]} />
        </div>
      </Section>

      {issuing ? (
        <Dialog title="Issue access key" onClose={() => setIssuing(false)}>
          <form className="stack" onSubmit={issue}>
            <label className="field"><span>Name</span><input className="control" required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. DHIMS2 adapter" autoFocus /></label>
            <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
              <span>Roles</span>
              <div className="grid-2" style={{ gap: 8 }}>
                {ROLES.map((r) => (
                  <label key={r} className="checkbox t-small">
                    <input type="checkbox" checked={roles.includes(r)} onChange={(e) => setRoles((rs) => (e.target.checked ? [...rs, r] : rs.filter((x) => x !== r)))} />
                    {humanize(r)}
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="dialog-actions">
              <CancelButton />
              <button type="submit" className="btn btn-primary" disabled={busy || !name.trim() || !roles.length}>Issue key</button>
            </div>
          </form>
        </Dialog>
      ) : null}

      {issued ? (
        <Dialog title={`Key issued: ${issued.name}`} onClose={() => { setIssued(null); setCopied(false); }}>
          <Notice tone="warning">Copy this key now. It will not be shown again.</Notice>
          <pre className="json" style={{ whiteSpace: "pre-wrap", wordBreak: "break-all" }}>{issued.token}</pre>
          <div className="dialog-actions">
            <button type="button" className="btn" onClick={() => { void navigator.clipboard.writeText(issued.token); setCopied(true); }}><Copy size={16} strokeWidth={1.75} aria-hidden />{copied ? "Copied" : "Copy key"}</button>
            <CancelButton className="btn btn-primary">Done</CancelButton>
          </div>
        </Dialog>
      ) : null}

      {revoking ? (
        <Dialog title="Revoke access key" onClose={() => setRevoking(null)}>
          <p className="t-secondary">“{revoking.name}” will stop working immediately. This is recorded and cannot be undone.</p>
          <div className="dialog-actions">
            <CancelButton />
            <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void revoke(revoking)}>Revoke key</button>
          </div>
        </Dialog>
      ) : null}
    </div>
  );
}
