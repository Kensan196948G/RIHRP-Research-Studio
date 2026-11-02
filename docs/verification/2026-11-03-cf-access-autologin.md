# 検証記録 — 2026-11-03 Cloudflare Access 自動ログイン（JWT 検証）

対象: `/api/auth/access` とフロントの自動サインイン。実装は `feat/cf-access-autologin`。

## 1. 目的

- Cloudflare Access で認証済みの利用者が、アプリ側のパスワードを入力せずにサインインできるようにする。
- ログインできる利用者を Cloudflare Access の 1 アカウント（`RIHRP_CF_ACCESS_ALLOWED_EMAILS`）に限定する。

## 2. 変更

| 層 | 内容 |
|---|---|
| 設定 | `RIHRP_TRUST_CF_ACCESS`（有効化）/ `RIHRP_CF_ACCESS_TEAM_DOMAIN` / `RIHRP_CF_ACCESS_AUD` / `RIHRP_CF_ACCESS_ALLOWED_EMAILS` / `RIHRP_CF_ACCESS_LOOPBACK_ONLY` / `RIHRP_CF_ACCESS_PROVISION` / `RIHRP_CF_ACCESS_DEFAULT_ROLE` |
| 検証 | `apps/api/rihrp/cf_access.py`: `Cf-Access-Jwt-Assertion` を RS256 署名・`iss`・`aud`・`exp`/`iat` まで検証。公開鍵は `https://<team>/cdn-cgi/access/certs` から取得して 5 分キャッシュ（取得失敗時は直前の鍵、鍵が無ければ拒否）。 |
| API | `GET /api/auth/access`: JWT 検証 → email allowlist → `users` と照合 → セッション + CSRF Cookie を発行（`Cache-Control: no-store`）。ループバック限定は任意（既定 false）。**すべての拒否**を監査 `auth.access_denied` に、成功を `auth.login`（`via=cloudflare_access`）に記録。 |
| フロント | `AuthProvider` が `/api/auth/me` の 401 後に `/api/auth/access` を試す。ログイン画面に状態表示と「Cloudflare Access でサインイン」ボタン。明示ログアウト直後は同一タブで自動サインインを繰り返さない（`sessionStorage`）。 |
| 依存 | `pyjwt[crypto]` を追加（RS256 検証）。 |
| ドキュメント | ADR-0004 を JWT 検証方式へ更新、README / Runbook / Architecture / Traceability を更新。 |

## 3. 確認したこと（自動テスト・静的検査）

| 項目 | 結果 |
|---|---|
| `pytest -q` | **85 passed / 1 skipped**（Access 関連 26 件を追加: unit 16 / integration 10） |
| `ruff check` / `ruff format --check` | pass |
| `python infra/db/export_openapi.py --check` | pass（`/api/auth/access` を反映） |
| `vitest run` | **8 passed**（`auth.test.tsx` 3 件: 自動サインイン / 無効時のフォールバック / ログアウト直後の抑止） |
| `tsc -b` / `vite build` | pass |

integration テストで確認した境界:

- `RIHRP_TRUST_CF_ACCESS=false` → **404** `access_login_disabled`
- Assertion 無し → **401** `access_assertion_missing`
- 署名が一致しないトークン → **401** `access_assertion_invalid`
- allowlist 外の email → **403** `access_email_not_allowed`（監査 `auth.access_denied`）
- 未登録ユーザー → **403** `access_user_not_found`（`PROVISION=true` のときだけ `viewer` で作成）
- ループバック外の接続（`LOOPBACK_ONLY=true` を明示した場合）→ **403** `access_origin_rejected`（監査に記録）
- 正常トークン → **200**（`Cache-Control: no-store`）、`/api/auth/me` が同じセッションで 200、監査 `auth.login`（`via=cloudflare_access`）
- allowlist が空 → **403**（全拒否）、ループバック外 → **403**（監査 `auth.access_denied` に `reason` と `source` を記録）

unit テストで確認した境界:

- 正常な RS256 トークン / `aud` 不一致 / `iss` 不一致 / 期限切れ / 署名偽造（別鍵）/ 未知の `kid`
- `alg=none` / `HS256` 混同 / `exp`・`iat` 欠落 / 未来の `iat`（いずれも **401**）
- 設定不足（team domain / aud 未設定）→ **503** `access_not_configured`
- JWKS 取得失敗（キャッシュ無し）→ **503**、不正な JWKS → **503**
- 鍵取得失敗時: キャッシュが `JWKS_STALE_MAX_SECONDS`（3600 秒）以内なら継続、超過なら **503**
- allowlist のカンマ区切りパース

## 4. 本番設定

`~/.config/rihrp/rihrp.conf`（リポジトリ外）:

```ini
RIHRP_TRUST_CF_ACCESS=true
RIHRP_CF_ACCESS_TEAM_DOMAIN=winter-lake-f4c9.cloudflareaccess.com
RIHRP_CF_ACCESS_AUD=<Access アプリの AUD>
RIHRP_CF_ACCESS_ALLOWED_EMAILS=<単一の email>
RIHRP_CF_ACCESS_LOOPBACK_ONLY=false
RIHRP_CF_ACCESS_PROVISION=false
```

Cloudflare Access 側: アプリ「RIHRP Research Studio」の allow policy を **単一 email のみ**に絞る（ドメイン許可は削除）。

### 4.1 設計の修正（実測に基づく）

- 配備前の実測で、uvicorn は proxy headers を既定で信頼し、Tunnel 経由の `request.client.host` が
  **利用者の実 IP**（例 `2001:268:...`）になることを確認した（`journalctl -u rihrp.service`）。
- そのため `RIHRP_CF_ACCESS_LOOPBACK_ONLY` の既定を **false** にした。この判定は uvicorn を
  `--no-proxy-headers` で動かす場合の追加防御として残す。境界は **JWT 検証 + email allowlist** が担う。

## 5. 実測（配備後）

- `GET http://127.0.0.1:18110/api/auth/access`（Assertion 無し）→ **401**（自動ログイン有効）
- 署名の合わない JWT を付与 → **401**
- `GET https://research.mirai-dx-platform.com/` → **302**（Access。変わらず）
- `/healthz` `/readyz` → 200
- 監査: **すべての拒否**（Assertion 欠落 / 署名・aud・iss・期限の検証失敗 / email 欠落 / allowlist 外 / 未登録 / 無効 / 送信元拒否）が `auth.access_denied` に、成功が `auth.login`（`via=cloudflare_access`）に残る（integration テストで確認）

## 6. 未検証

- **実際の Cloudflare Access ログイン（OTP/SSO）を通したブラウザ確認**: AI は Access の資格情報を持たないため未実施。利用者による確認が必要。
- Cloudflare Access のポリシー変更（email 絞り込み）の反映確認は API の読み戻しで行う。

## 7. 切り戻し

1. `RIHRP_TRUST_CF_ACCESS=false` にして `systemctl --user restart rihrp.service`（自動ログイン停止。パスワードログインは継続）。
2. Access ポリシーを元の include（email + 許可ドメイン）に戻す。
3. コードを戻す場合は該当 PR を revert して `infra/native/deploy.sh`。
