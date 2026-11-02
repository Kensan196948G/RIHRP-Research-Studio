# ADR-0005: 監査ログは業務トランザクション内で append-only に書く

- 状態: 提案
- 日付: 2026-11-02

## 背景

「操作は成功したが監査が残っていない」「監査だけ残って操作は失敗した」という状態は、監査の意味を壊す。ACCC / DD でも同じ方針（append-only・同一 Tx）を採っている。

## 決定

- `audit_events` への INSERT は、業務操作と同じ DB トランザクションで行う。
- 監査の書き込みに失敗した場合、業務操作も失敗させる（fail closed）。
- `audit_events` に対する UPDATE / DELETE の API を提供しない。
- DB トリガー `trg_audit_immutable`（migration `0002_audit_immutable`）で UPDATE / DELETE を例外にする。アプリのバグや手作業 SQL でも履歴を書き換えられない。
- 記録項目: actor_id、action、entity_type、entity_id、project_id、details（秘密は入れない）、created_at、request_id。

## 理由

- 監査と状態の不整合を原理的に作らない。
- 追記専用にすることで、事後の改竄を難しくする。

## 影響

- 監査対象の操作では 1 Tx あたり 1 INSERT 増える。性能影響は軽微。
- 保持期間（既定 365 日）を過ぎた行の削除は、運用ジョブとして別途定義する（MVP では未実装、Runbook に記載）。
