# ADR-0001: Web 基盤は FastAPI + React + ローカル PostgreSQL + native systemd

- 状態: 提案（実装は本 ADR に従う）
- 日付: 2026-11-02

## 背景

隣接プロジェクト（ACCC / Development Dispatcher / RSP）は、FastAPI + React + ローカル PostgreSQL + native systemd + Cloudflare Tunnel/Access で運用されている。Neon は廃止済み、Docker は使わない方針がユーザー規則として定着している。

## 決定

RIHRP Research Studio も同じ基盤を採用する。

- API: FastAPI（Python 3.12）+ SQLAlchemy 2 + Alembic
- Web: React 18 + TypeScript + Vite。ビルド成果物を API が同一オリジンで配信
- DB: ローカル PostgreSQL 16（`rihrp` / `rihrp_test*`）
- 配備: systemd user unit + uvicorn。Cloudflare は本番のみ Tunnel / Access を前段に置く

## 理由

- 既存運用と監視・バックアップ・配備手順を再利用できる。
- 単一オリジンで CORS と Cookie の取り扱いが単純になり、CSRF 対策が明確になる。
- Docker を挟まないことで、ホストの PostgreSQL と systemd の権限・監査がそのまま使える。

## 影響

- 本番公開には Cloudflare Tunnel の設定が必要（Approval PR）。
- フロントのビルドを配備手順に含める必要がある（`deploy.sh` が実行）。

## 代替案

- Next.js フルスタック: 既存 API 規約（OpenAPI 再生成、pytest 実 DB）と揃わないため不採用。
- Cloudflare Workers + D1: ローカル PostgreSQL 原則と監査要件に合わないため不採用。
