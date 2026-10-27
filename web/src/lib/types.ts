import type { components } from "./api-schema";

// Typed responses come from the API's OpenAPI schema (npm run gen:api).
type S = components["schemas"];
export type SituationRoom = S["SituationRoom"];
export type SectorSummary = S["SectorSummary"];
export type StoredDecision = Omit<S["StoredDecision"], "evidence" | "conflicts"> & {
  evidence: EvidenceItem[];
  conflicts: ConflictItem[];
};
export type ReplayReport = S["ReplayReport"];
export type ResolveBody = S["ResolveBody"];
export type SignalInput = S["SignalInput"];

// Endpoints that return free-form JSON in the API are described here.
export interface Me {
  subject: string;
  roles: string[];
  nation_id: string | null;
  method: "oidc" | "api_key";
  permissions: string[];
}

export interface Sector {
  sector_id: string;
  sector_name: string;
  priority_24hae: string;
  half_life_hours: number;
  model_route: "default" | "sovereign" | "rules_only";
  validation_thresholds: { trusted: number; provisional: number };
  signal_types: Record<string, string | null>;
}

export type Priority = "low" | "medium" | "high" | "critical";

export interface Escalation {
  escalation_id: string;
  decision_id: string | null;
  audit_ref: string | null;
  nation_id: string;
  sector: string;
  objective: string;
  priority: Priority;
  assigned_role: string;
  sla_minutes: number;
  due_at: string;
  reasons: { code: string; priority: Priority; message: string }[];
  status: "open" | "acknowledged" | "resolved";
  breached_at: string | null;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  resolution: string | null;
  created_by: string;
  created_at: string;
}

export interface DecisionSummary {
  audit_ref: string;
  decision_id: string;
  audit_seq: number;
  sector: string;
  nation_id: string;
  objective: string | null;
  validation_state: string;
  confidence: number | null;
  action: string;
  allowed_for_action: boolean;
  human_escalation_required: boolean;
  produced_by: string | null;
  created_at: string;
  created_by: string;
}

export interface AuditEntrySummary {
  seq: number;
  event_type: string;
  ref: string;
  actor: string;
  created_at: string;
  payload_hash: string;
  prev_hash: string;
  entry_hash: string;
  payload_bytes: number;
}

export interface AuditVerify {
  ok: boolean;
  chain: {
    ok: boolean;
    entries_checked: number;
    head_hash: string;
    first_bad_seq: number | null;
    problem: string | null;
  };
  anchors: { ok: boolean; anchors_checked: number; latest_seq: number | null; problems: string[] };
}

export interface EvidenceItem {
  signal_id: string;
  signal_type: string;
  source_id: string;
  source_type: string;
  payload: Record<string, unknown>;
  observed_at: string | null;
  freshness: number | null;
  source_reliability: number | null;
  evidence_strength: number | null;
  timestamp_basis: string | null;
}

export interface ConflictItem {
  signal_a: string;
  signal_b: string;
  signal_type: string;
  field: string;
  value_a: number;
  value_b: number;
  relative_difference: number;
  tolerance: number;
  severity: number;
}

export interface SignalRow {
  signal_id: string;
  sector: string;
  signal_type: string;
  source_id: string;
  source_type: string;
  reading_field: string | null;
  reading: unknown;
  observed_at: string | null;
  received_at: string;
  freshness: number | null;
  stale: boolean;
}

export interface SignalsResponse {
  summary: { received: number; sources: number; mean_freshness: number | null; stale: number };
  signals: SignalRow[];
  truncated: boolean;
}

export interface ApiKeyRow {
  key_id: string;
  name: string;
  roles: string[];
  nation_id: string | null;
  created_by: string;
  created_at: string;
  revoked_at: string | null;
}

export interface NodeStatus {
  node_id: string;
  engine_version: string;
  config_hash: string;
  manifest_version: string;
  audit_head_seq: number | null;
  last_anchor_seq: number | null;
  last_anchor_at: string | null;
  entries_since_anchor: number;
  model_gateway: Record<string, string | null>;
  anchor_signing: boolean;
}

export interface ReplayAll {
  ok: boolean;
  total: number;
  matched: number;
  mismatched: string[];
  errors: Record<string, string>;
}

/** The decision object as recorded (see antos_core.loop.Decision). */
export interface DecisionDetail {
  decision_id: string;
  objective: string;
  sector: string;
  nation_id: string;
  validation_state: string;
  confidence: number;
  contradiction_count: number;
  contradiction_severity: string;
  ecology_state: string;
  ecology_score: number | null;
  inclusion_state: string;
  inclusion_score: number | null;
  hae_alignment_score: number | null;
  recommended_action: {
    action: string;
    primary_recommendation: string;
    secondary_recommendations: string[];
    ubuntu_note: string;
    hae_note: string;
    escalation_suggested: boolean;
    cited_signal_ids: string[];
    produced_by: string;
    note: string;
  };
  human_escalation_required: boolean;
  allowed_for_action: boolean;
  local_fit_passed: boolean | null;
  local_fit_report: {
    dimensions_failed: string[];
    dimensions_not_assessed: string[];
    remediation_actions?: string[];
  };
  guardrail_events: string[];
  audit_ref: string;
}
