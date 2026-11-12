# Changelog

本プロジェクトの主な変更点を記録する。形式は Keep a Changelog に準拠し、バージョンは
[Semantic Versioning](https://semver.org/lang/ja/) に従う。

## [Unreleased]

### Added

- スタジオのワンクリック実行（01〜06 の自動進行）。承認待ちでは自動承認せず停止し、承認後に再開する。
  プロトタイプ HTML は変更せず、`apps/web` の UI のみの追加。
- 監査ログの保持期間削除（`python -m rihrp.maintenance purge-audit`、dry-run 既定・
  所有者ロール・承認後にタイマー有効化。ADR-0006）。

## [0.1.0] - 2026-11-03

初回の正式リリース。根拠付きリサーチスタジオ（RIHRP）の MVP を本番公開する。

### Added

- 認証・セッション・CSRF・RBAC（admin / editor / reviewer / viewer）と監査ログ（append-only、TRUNCATE 保護）。
- 研究テーマ・出典（SHA-256）・主張・根拠・決定的検証・レポート・版・提出・承認・差し戻し・エクスポート。
- WebUI（Offline Research Studio の 6 ステップ: 研究仮説登録 / AIタスク管理 / 複数AI討論 / 根拠・反証 / 新仮説比較 / 研究報告書）。
- 研究状態のサーバー永続化（`research_documents`、楽観ロック）とオフライン保存失敗からの復帰。
- Cloudflare Access JWT の検証による自動ログイン（単一 email allowlist、拒否監査、fail closed）。
- 320px〜デスクトップのレスポンシブ、キーボード操作、ダークモード、印刷 CSS。
- 運用の自動化: 日次バックアップ、週次復元訓練、日次セッション削除、5 分間隔の外形チェック
  （`infra/native/install_ops_units.sh`）。
- 監査ログの件数確認コマンド `python -m rihrp.maintenance audit-stats`（保持方針の判断材料）。

### Changed

- WebUI をリポジトリ直下の正本 `RIHRP_Offline_Research_Studio.html` に 100% 整合。
- 空候補のナビ表示（「候補 0件」→「未生成」）、320px の横スクロール、報告書の表・検証手法行の折返しを修正。
- E2E を 26 件へ拡張（320px 全 6 ビュー・キーボード・オフライン保存）。
- 同時承認の直列化（NFR-16）を統合テストで追加。

### Security

- 保存型 XSS を正本・アプリ双方で排除（全 sink のエスケープと型・列挙・数値の正規化、サーバー側 422 検証）。
- DB のロール分離（app / owner）と監査テーブルの TRUNCATE トリガー。
- 依存関係の既知脆弱性（dev 依存）を修正し、Dependabot の open critical/high を 0 に維持。

### Operations

- 運用手順（`docs/runbooks/operations.md`）とリリース手順（`docs/runbooks/release.md`）を整備。
- Cloudflare Access ポリシーの実測値（単一 email）に合わせてドキュメントを是正。
