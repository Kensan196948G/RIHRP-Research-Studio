# ADR-0004: 認証はサーバーセッション + CSRF、本番は Cloudflare Access を前段に置く

- 状態: 採用（2026-11-03 に Cloudflare Access の JWT 検証方式へ更新）
- 日付: 2026-11-02（更新: 2026-11-03）

## 背景

ローカル PostgreSQL を正とし、Cloudflare から DB へ直接接続しない構成（要件）では、認証はアプリ側で完結させる必要がある。将来の本番公開では Cloudflare Access を前段に置く。

## 決定

- アプリ内認証: メール + パスワード（Argon2id）。セッションは DB 保存、Cookie は HttpOnly / SameSite=Lax / Secure（production）。
- 状態変更 API は CSRF トークン（Cookie + `X-CSRF-Token`）を必須とする。
- ログイン試行は IP 単位でレート制限する。
- 本番は Cloudflare Access を前段に置く。`RIHRP_TRUST_CF_ACCESS=true` のとき `/api/auth/access` が
  `Cf-Access-Jwt-Assertion` を **RS256 署名・iss・aud・有効期限まで検証**し、email クレームが
  `RIHRP_CF_ACCESS_ALLOWED_EMAILS` に一致する利用者にだけアプリのセッションを発行する（自動ログイン）。
- 信頼の境界:
  - アプリは 127.0.0.1:18110 でのみ待ち受け、外部からは Tunnel + Access 経由でのみ到達できる。
  - `RIHRP_CF_ACCESS_LOOPBACK_ONLY=true`（既定）では、ループバック以外からの `/api/auth/access` を拒否する。
  - **`Cf-Access-Authenticated-User-Email` のような平文ヘッダーは信頼しない**（JWT 検証を必須にする）。
  - 許可 email が空のときは全拒否（fail closed）。未登録ユーザーの自動作成は既定で無効。
- パスワードログイン（`/api/auth/login`）は開発・フォールバック用に残すが、本番の入口は Cloudflare Access とする。
- 認証方式・認可モデルの変更は高リスク変更として Approval PR に分離する。

## 理由

- セッションを DB に置くことで、ログアウト・失効・監査が確実になる。
- SameSite=Lax だけでは同一サイト内の CSRF を防げないため、トークンを二重化する。
- 平文ヘッダーを信頼すると、ローカルプロセスや Tunnel を迂回した直接アクセスでなりすましが成立する。JWT の署名・aud・iss を検証し、ループバック限定と allowlist を重ねる。

## 影響

- セッションテーブルの増加。期限切れの定期削除が必要（Runbook に記載）。
- Access 連携時は、アプリのユーザー（users.email）と Access の email を一致させる運用が必要。新規利用者は先にアプリへ登録するか、`RIHRP_CF_ACCESS_PROVISION=true` を明示的に使う。
- Access の公開鍵は `https://<team domain>/cdn-cgi/access/certs` から取得して 5 分キャッシュする。取得失敗時は直前の鍵を使い、鍵が無い場合は自動ログインを拒否する（fail closed）。
