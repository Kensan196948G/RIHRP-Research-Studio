# RIHRP Research Studio — アーキテクチャ

- 版: v0.1（提案ドラフト）
- 日付: 2026-11-02

## 1. 全体構成

```
[Browser]──HTTPS/HTTP──>[FastAPI (uvicorn) :18110]──SQL──>[Local PostgreSQL 16]
                              │
                              ├─ /api/*     JSON API
                              ├─ /assets/*  React build
                              └─ /           SPA fallback
[Cloudflare Tunnel / Access]（本番の前段。research.mirai-dx-platform.com で稼働中）
```

- **単一オリジン**: API が React のビルド成果物を配信する。CORS を開けない。
- **ステートレス API + サーバーセッション**: セッションは DB（`sessions`）に保存し、Cookie はランダムトークンのみ。
- **ネイティブ配備**: systemd user unit。Docker / Neon は使わない（ADR-0001）。

## 2. ディレクトリ

| パス | 内容 |
|---|---|
| `apps/api/rihrp/` | FastAPI アプリ（models / db / auth / verify / api ルータ） |
| `apps/web/` | React + TypeScript + Vite |
| `infra/migrations/` | Alembic |
| `infra/db/` | DB bootstrap / backup / restore 検証 |
| `infra/native/` | systemd unit、deploy / health check |
| `tests/` | 実 PostgreSQL を使う結合テスト |
| `docs/` | 要件・設計・ADR・Runbook・OpenDesign 設計 |

## 3. データモデル

```text
users(id, email uniq, name, role, password_hash, is_active, created_at)
sessions(id, user_id FK, token_hash uniq, csrf_token, expires_at, created_at, revoked_at)
projects(id, title, summary, status, owner_id, created_at, updated_at)

sources(id, project_id FK, title, kind, origin, content, content_sha256, created_by, created_at)
  UNIQUE(project_id, content_sha256)

claims(id, project_id FK, text, created_by, last_verdict, last_verified_at, last_details jsonb, created_at, updated_at)
claim_evidence(id, claim_id FK, source_id FK, quote, note, created_at)

reports(id, project_id FK, title, content jsonb, status, version, created_by, created_at, updated_at)
report_versions(id, report_id FK, version, content jsonb, seal_sha256, created_by, created_at, note)
report_verifications(id, report_id FK, version, summary jsonb, created_by, created_at)
reviews(id, report_id FK, version, reviewer_id, decision, comment, created_at)

audit_events(id, actor_id, action, entity_type, entity_id, project_id, details jsonb, created_at)
```

- `content_sha256`: 本文 UTF-8 バイト列の SHA-256（小文字 hex）。
- `report_versions.seal_sha256`: content をキー順固定で正規化した JSON の SHA-256。
- `audit_events` は追記のみ。更新・削除 API を持たない。

## 4. 検証アルゴリズム（決定論）

入力: claim.text、根拠（source.content, source.content_sha256, quote）。

1. 各根拠の `digest_ok = (sha256(source.content) == source.content_sha256)`。
2. 各根拠の `quote_found`:
   - quote が空 → `null`
   - 空白正規化後に quote が content に含まれる → `true` / 含まれない → `false`
3. 主張から数値トークンを抽出（`\d+(?:[.,]\d+)*%?`）。各数値について、いずれかの根拠本文（正規化済み）に同一表記が含まれるか。
4. 判定:
   - 根拠 0 → `insufficient`
   - `digest_ok=false` が 1 件以上 → `contradicted`（理由: `evidence_tampered`）
   - `quote_found=false` が 1 件以上 → `contradicted`（理由: `quote_not_found`）
   - 数値のうち 1 つでも未発見 → `unverified`（理由: `number_not_found`）
   - quote があり、数値がすべて発見済み → `verified`
   - quote が無く数値も無い → `insufficient`（理由: `no_anchor`）
   - 上記以外（quote 無し・数値あり・数値発見済み）→ `verified`（数値アンカーあり）

決定論を保つため、判定に LLM を使わない。将来 LLM 補助を足す場合も、この判定を上書きしない（ADR-0002）。

## 5. 認証・認可

- パスワード: Argon2id（argon2-cffi）。
- セッション: 32 バイト乱数 → SHA-256 を `sessions.token_hash` に保存。Cookie `rihrp_session` は HttpOnly / SameSite=Lax / Path=/。
- CSRF: ログイン時に `rihrp_csrf` Cookie（JS 可読）とセッション行の `csrf_token` を発行。状態変更は `X-CSRF-Token` と Cookie の一致を検証。
- 認可: ルータ依存で `require_role(...)`。プロジェクト単位の分離は MVP では行わず、組織内の全テーマを共有する（要件 FR-8 の範囲）。
- 本番: Cloudflare Access を前段に置き、アプリは Access 済みリクエストのみ受ける（`RIHRP_TRUST_CF_ACCESS=true` のときのみ `Cf-Access-Authenticated-User-Email` を信頼）。

## 6. エラーと監査

- エラー形式: `{"error": {"code": "...", "message": "...", "details": {...}}}`。
- 主要コード: `unauthorized` / `forbidden` / `not_found` / `validation_error` / `conflict` / `approval_blocked` / `rate_limited`。
- 監査: `write_audit(session, ...)` を業務 Tx 内で呼ぶ。Tx 失敗時は監査もロールバックされ、操作自体が失敗する。

## 7. 障害時の考え方

| 障害 | 挙動 |
|---|---|
| DB 接続不可 | `/healthz` は 200（プロセス生存）、`/readyz` は 503。UI はエラーバナー。 |
| スナップショット改竄 | 検証で contradicted。承認は 409。レポートに [矛盾] マーカー。 |
| セッション期限切れ | 401 → ログイン画面へ遷移。 |
| migration 未適用 | 起動時に検出し `/readyz` 503、ログに理由。 |

## 8. 配備

- `infra/native/rihrp.service`（user unit）: `uvicorn rihrp.main:app --host 127.0.0.1 --port 18110`。
- `infra/native/deploy.sh <commit>`: 依存同期 → migration → ビルド済み web を配置 → restart → health check。
- 本番公開は Cloudflare Tunnel（`rihrp-cloudflared.service`）+ Cloudflare Access で構成済み（`docs/verification/2026-11-03.md`）。
- 公開 DNS・custom domain・Access の変更は高リスク変更として Approval PR + ユーザーの明示 Y/N とする。
