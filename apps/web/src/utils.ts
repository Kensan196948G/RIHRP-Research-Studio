import type { Role, Verdict } from "./types";

export const VERDICT_LABEL: Record<Verdict, string> = {
  verified: "検証済",
  unverified: "未検証",
  contradicted: "矛盾",
  insufficient: "根拠不足",
};

export const VERDICT_HINT: Record<Verdict, string> = {
  verified: "引用または数値が根拠スナップショットに実在します。",
  unverified: "根拠はありますが、主張の数値が根拠に見つかりません。",
  contradicted: "引用が見つからないか、スナップショットが改竄されています。",
  insufficient: "根拠が未登録、または引用・数値のアンカーがありません。",
};

export const ROLE_LABEL: Record<Role, string> = {
  admin: "管理者",
  editor: "リサーチャー",
  reviewer: "レビュアー",
  viewer: "閲覧者",
};

export const REPORT_STATUS_LABEL: Record<string, string> = {
  draft: "下書き",
  in_review: "レビュー中",
  changes_requested: "差し戻し",
  approved: "承認済み",
};

export function verdictOf(claim: { last_verdict: Verdict | null }): Verdict | null {
  return claim.last_verdict;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("ja-JP", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatShortDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("ja-JP", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function shortHash(hash: string | null | undefined): string {
  if (!hash) return "—";
  return `${hash.slice(0, 12)}…`;
}

export function classNames(...values: (string | false | null | undefined)[]): string {
  return values.filter(Boolean).join(" ");
}

export function countUnresolved(stats: { unverified: number; contradicted: number; insufficient: number; unchecked: number }): number {
  return stats.unverified + stats.contradicted + stats.insufficient + stats.unchecked;
}

export function canEdit(role: Role | undefined): boolean {
  return role === "admin" || role === "editor";
}

export function canReview(role: Role | undefined): boolean {
  return role === "admin" || role === "reviewer";
}
