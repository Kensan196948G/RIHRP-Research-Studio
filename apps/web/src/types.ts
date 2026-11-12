export type Role = "admin" | "editor" | "reviewer" | "viewer";
export type Verdict = "verified" | "unverified" | "contradicted" | "insufficient";

export interface User {
  id: string;
  email: string;
  name: string;
  role: Role;
  is_active: boolean;
  created_at: string | null;
}

export interface Stats {
  sources: number;
  claims: number;
  reports: number;
  verified: number;
  unverified: number;
  contradicted: number;
  insufficient: number;
  unchecked: number;
  review_pending: number;
  changes_requested: number;
}

export interface Project {
  id: string;
  title: string;
  summary: string;
  status: "active" | "archived";
  owner_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  stats: Stats;
}

export interface Source {
  id: string;
  project_id: string;
  title: string;
  kind: "url" | "doi" | "text";
  origin: string;
  content?: string;
  content_sha256: string;
  tampered: boolean;
  used_by_claims?: number;
  created_at: string | null;
}

export interface Evidence {
  id: string;
  claim_id: string;
  source_id: string;
  source_title: string | null;
  source_origin: string | null;
  quote: string;
  note: string;
  quote_found: boolean | null;
  created_at: string | null;
}

export interface Claim {
  id: string;
  project_id: string;
  text: string;
  last_verdict: Verdict | null;
  last_verified_at: string | null;
  last_details: {
    reasons?: string[];
    evidence?: { source_id: string; title: string; digest_ok: boolean; quote_found: boolean | null }[];
    numbers?: { value: string; found: boolean }[];
    missing_numbers?: string[];
  } | null;
  evidence_count: number;
  evidence?: Evidence[];
  created_at: string | null;
  updated_at: string | null;
}

export interface Paragraph {
  id: string;
  text: string;
  claimIds: string[];
}

export interface Section {
  id: string;
  heading: string;
  paragraphs: Paragraph[];
}

export interface ReportContent {
  sections: Section[];
}

export interface VerificationSummary {
  total_claims: number;
  referenced_claim_ids: string[];
  missing_claim_ids: string[];
  verified: number;
  unverified: number;
  contradicted: number;
  insufficient: number;
  issues: { claim_id: string; verdict: Verdict; reasons: string[]; text: string }[];
  checked_at: string;
}

export interface Review {
  id: string;
  decision: "approved" | "changes_requested";
  comment: string;
  version: number;
  reviewer_name: string | null;
  created_at: string | null;
}

export interface ReportIntegrity {
  verified: number;
  unverified: number;
  contradicted: number;
  insufficient: number;
  unchecked: number;
  referenced: number;
  needs_reapproval: boolean;
}

export interface Report {
  id: string;
  project_id: string;
  title: string;
  content: ReportContent;
  status: "draft" | "in_review" | "changes_requested" | "approved";
  version: number;
  ai_assisted: boolean;
  submitted_by: string | null;
  submitted_by_name: string | null;
  submitted_at: string | null;
  approved_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  integrity?: ReportIntegrity;
  latest_verification?: {
    summary: VerificationSummary;
    version: number;
    created_at: string | null;
  };
  reviews?: Review[];
}

export interface AuditEvent {
  id: string;
  actor_id: string | null;
  actor_name: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  project_id: string | null;
  details: Record<string, unknown>;
  created_at: string | null;
}
