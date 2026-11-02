# 要件トレーサビリティ

- 対象: 要件 [`docs/requirements/01-requirements.md`](../requirements/01-requirements.md) v0.1
- 日付: 2026-11-02
- 「テスト」列は `tests/` の自動テスト、または実測記録を示す。

## 機能要件

| 要件 | 実装 | テスト / 実測 | 状態 |
|---|---|---|---|
| FR-1.1 ログイン | `apps/api/rihrp/routers/auth.py::login` | `test_login_and_me` | ✅ |
| FR-1.2 セッション Cookie | `auth.py::_set_cookies`（HttpOnly / SameSite=Lax / Secure） | `test_login_and_me`、実測 | ✅ |
| FR-1.3 CSRF | `auth.py::get_principal`（`X-CSRF-Token`） | `test_csrf_required_for_writes`、`csrf probe 403` | ✅ |
| FR-1.4 ログイン失敗の統一・レート制限 | `auth.py::check_login_rate` | `test_login_rejects_wrong_password`、`test_login_rate_limit` | ✅ |
| FR-1.5 ログアウト失効 | `auth.py::logout` | `test_logout_revokes_session` | ✅ |
| FR-2.1 テーマ CRUD（UI・削除含む） | `routers/projects.py`、テーマ編集モーダル | `test_main_flow_end_to_end`、`test_project_update_and_archive`、UI 実測（削除は管理者のみ表示） | ✅ |
| FR-2.2 要対応件数 | `services.py::project_stats` | `test_main_flow_end_to_end`、UI 実測 | ✅ |
| FR-2.3 テーマ詳細 | `routers/projects.py::get_project` + 各一覧 API | UI 実測 | ✅ |
| FR-2.4 テーマ検索 | ダッシュボードのクライアント検索 | UI 実測（1 件 / 該当なし） | ✅ |
| FR-3.1 出典の kind/origin/title | `routers/sources.py::create_source` | `test_main_flow_end_to_end` | ✅ |
| FR-3.2 本文の SHA-256 | `services.py::sha256_text` | `test_main_flow_end_to_end`（export に sha を含む） | ✅ |
| FR-3.3 同一内容の重複拒否 | `sources.py::create_source`（409） | `test_duplicate_source_rejected` | ✅ |
| FR-3.4 読み出し時の改竄検知 | `services.py::source_to_dict`（再計算） | `test_tampered_snapshot_blocks_approval` | ✅ |
| FR-3.5 本文 1 MiB 上限 | `schemas.py::SourceIn` | （Pydantic のバリデーション） | ✅ |
| FR-4.1 主張の作成・編集 | `routers/claims.py`、主張詳細モーダル | `test_main_flow_end_to_end`、`test_claim_update_resets_verdict`、UI 実測 | ✅ |
| FR-4.2 根拠の紐付け | `claims.py::add_evidence` | `test_main_flow_end_to_end` | ✅ |
| FR-4.3 引用の実在確認（422） | `claims.py::add_evidence` | `test_quote_must_exist` | ✅ |
| FR-4.4 検証 API と保存 | `services.py::verify_claim_row` | `test_main_flow_end_to_end` | ✅ |
| FR-5.1 決定論的 4 判定 | `apps/api/rihrp/verify.py` | `tests/unit/test_verification.py` 7 件 | ✅ |
| FR-5.2 判定の内訳 | `verify.py::verify_claim`（details） | 同上 | ✅ |
| FR-5.3 一括 / レポート検証 | `claims.py::verify_project_claims`、`reports.py::verify_report` | `test_main_flow_end_to_end` | ✅ |
| FR-5.4 検証履歴 | `report_verifications` | `test_main_flow_end_to_end` | ✅ |
| FR-6.1 レポート content | `routers/reports.py` | `test_main_flow_end_to_end` | ✅ |
| FR-6.2 版とシール | `services.py::make_version`、版履歴モーダル | `test_main_flow_end_to_end`（versions）、UI 実測 | ✅ |
| FR-6.3 提出 | `reports.py::submit_report` | `test_main_flow_end_to_end` | ✅ |
| FR-6.7 同時編集の競合検知 | `reports.py::update_report`（`expected_version`） | `test_report_save_rejects_stale_version` | ✅ |
| FR-6.4 承認 / 差し戻し（矛盾ゼロ） | `reports.py::review_report` | `test_tampered_snapshot_blocks_approval`、`test_review_requires_comment_for_changes` | ✅ |
| FR-6.5 提出者本人の承認拒否 | `reports.py::review_report`（403） | `test_self_approval_forbidden` | ✅ |
| FR-6.6 Markdown エクスポート | `services.py::render_markdown` | `test_main_flow_end_to_end`、実測 | ✅ |
| FR-7.1 監査対象 | `audit.py::write_audit` 各ルータ | `test_main_flow_end_to_end`（actions） | ✅ |
| FR-7.2 同一 Tx / fail closed | 各ルータで `db.commit()` 前に監査 | `test_main_flow_end_to_end` | ✅ |
| FR-7.3 更新・削除不可 | ルータなし | `test_audit_is_not_mutable` | ✅ |
| FR-7.4 最近の活動 | ダッシュボード（reviewer/admin のみ） | UI 実測 | ✅ |
| FR-9.1 セッション保守 | `rihrp/maintenance.py` | `test_purge_sessions_removes_only_expired` | ✅ |
| FR-8.1 利用者管理（作成・ロール変更・無効化） | `routers/admin.py`、利用者画面 | `test_admin_can_list_users`、`test_admin_cannot_demote_self`、UI 実測 | ✅ |
| FR-8.3 パスワード変更 | `routers/auth.py::change_password`、設定画面 | `test_change_password`、UI 実測 | ✅ |
| FR-8.2 デモ seed | `seed.py`（`RIHRP_SEED_PASSWORD` 必須） | 実測（ローカル） | ✅ |

## 非機能要件

| 要件 | 実装 | テスト / 実測 | 状態 |
|---|---|---|---|
| NFR-1 ローカル PostgreSQL | `config.py` / `db.py` | `pytest`（`rihrp_test`） | ✅ |
| NFR-2 応答 300ms | インデックス、集計クエリ | 実測 n=100: p95 14.9〜24.8ms | ✅ |
| NFR-3 統一エラー形式 | `errors.py` | 各テストで `error.code` を確認 | ✅ |
| NFR-4 秘密をログに出さない | `security.py`、監査 details | コードレビュー | ✅ |
| NFR-9 本文サイズ上限 | `main.py`（2 MiB、413） | `test_oversized_body_rejected` | ✅ |
| NFR-10 Cookie 属性 | `auth.py::_set_cookies` | `test_session_cookie_flags` | ✅ |
| NFR-11 パスワード変更時のセッション失効 | `auth.py::change_password` | `test_password_change_revokes_other_sessions` | ✅ |
| NFR-12 一覧の N+1 回避 | `claims.py`（`GROUP BY`） | `test_claim_list_reports_evidence_count` | ✅ |
| NFR-5 監査 append-only | `audit.py`、API なし | `test_audit_is_not_mutable` | ✅ |
| NFR-6 Node 22 / Python 3.12 / Docker なし | systemd unit | 実測 | ✅ |
| NFR-7 migration 未適用で 503 | `routers/health.py` | `test_health_and_ready` | ✅ |
| NFR-8 キーボード / フォーカス | CSS `:focus-visible`、スキップリンク | Playwright 実測（2px ティール、Tab→本文へ移動） | ✅ |

## 追加要件（実運用で発見）

| 要件 | 実装 | テスト | 状態 |
|---|---|---|---|
| 承認後の根拠変更を検知 | `services.py::report_integrity` | `test_approved_report_flags_post_approval_tamper` | ✅ |
| 承認拒否時も検証結果を残す | `reports.py::review_report`（commit 後に 409） | `test_blocked_approval_persists_verification` | ✅ |
| モバイルでの可読性 | カード表示 / 表の横スクロール | Playwright 実測（390px） | ✅ |
