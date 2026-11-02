# ADR-0004: 認証はサーバーセッション + CSRF、本番は Cloudflare Access を前段に置く

- 状態: 提案
- 日付: 2026-11-02

## 背景

ローカル PostgreSQL を正とし、Cloudflare から DB へ直接接続しない構成（要件）では、認証はアプリ側で完結させる必要がある。将来の本番公開では Cloudflare Access を前段に置く。

## 決定

- アプリ内認証: メール + パスワード（Argon2id）。セッションは DB 保存、Cookie は HttpOnly / SameSite=Lax / Secure（production）。
- 状態変更 API は CSRF トークン（Cookie + `X-CSRF-Token`）を必須とする。
- ログイン試行は IP 単位でレート制限する。
- 本番は Cloudflare Access を前段に置き、`RIHRP_TRUST_CF_ACCESS=true` のときだけ `Cf-Access-Authenticated-User-Email` を信頼する。それ以外ではヘッダーを無視する。
- 認証方式・認可モデルの変更は高リスク変更として Approval PR に分離する。

## 理由

- セッションを DB に置くことで、ログアウト・失効・監査が確実になる。
- SameSite=Lax だけでは同一サイト内の CSRF を防げないため、トークンを二重化する。
- Access のヘッダーを無条件に信頼すると、Tunnel を迂回した直アクセスでなりすましが成立する。フラグで明示的に有効化する。

## 影響

- セッションテーブルの増加。期限切れの定期削除が必要（Runbook に記載）。
- Access 連携時は、アプリのユーザーと Access のメールを一致させる運用が必要。
