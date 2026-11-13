# AI 限定パイロット 本番配備記録（2026-11-13）

- 決定: [判断ブリーフ](2026-11-13-ai-enablement-decision-brief.md) の **B（限定パイロット）**。
  所有者の承認（番号選択 1）に基づき、対象 1 プロジェクト・既定 OFF・allowlist で配備した。
- 手順: [AI 限定パイロット運用](../operations/ai-pilot-runbook.md) / [Native コミット別リリース](../runbooks/immutable-release.md)
- 実施: 2026-11-13 16:05〜16:20 JST

## 0. 対象と環境

| 項目 | 値 |
|---|---|
| 対象 SHA | `25f352366ed04cc497de7abd04c888ee892b5554`（main・CI success） |
| 直前の稼働 | `e3f59c6af47a9f2625123944b8b925e9a2e9a1b2` |
| 差分 | 30 コミット（Phase 3 B/C・トークン計測・allowlist・docs）。**migration 追加なし** |
| 対象プロジェクト | `68489ee7a6ee4d1999d07719673d81fd`（「護岸の洗掘抑制」） |
| 制限 | `RIHRP_LLM_ALLOWED_PROJECTS=68489ee7a6ee4d1999d07719673d81fd`（03/04/05 のみ。AI 下書きは対象外） |

## 1. 事前確認（読み取り専用）

- 本番 `/healthz` / `/readyz` 200・release `e3f59c6a`・migration `0005_reports_ai_assisted`。
- `rihrp.service` active。最新 backup は 03:30 のもの。ディスク空き 112G。
- 対象プロジェクトの存在を本番 DB で確認（`projects.id` 一致、title「護岸の洗掘抑制」）。

## 2. ビルド（本番無影響）

`tools/release_build.py --expect-sha 25f3523…` → 成功。

- release: `~/.local/share/rihrp/releases/25f352366ed04cc497de7abd04c888ee892b5554`
- manifest SHA-256: `2cc38a784bc197fbf2bc478535a5874762d173f8278c00b3ca096fddd3fff776`

## 3. 隔離受入（本番とは別ポート・隔離 DB）

- 18121 で新 release を起動（`rihrp_test_ai_20261113`、`RIHRP_LLM_ALLOWED_PROJECTS=__other_project__`）。
- `/healthz` / `/readyz` 200・release `25f3523` / manifest 一致、`/` 200。
- 非許可プロジェクトの討論 API → **403 `ai_not_allowed`**（allowlist が効くことを実測）。
- 受入後に停止。

## 4. バックアップと復元証跡

- 新規 backup: `rihrp_production-20261113T071634695878-1129393.dump`（16:16 JST、`rihrp-backup.service` success）。
- dump SHA-256: `d83d3cc8af0eb83da0a00f2e34f2ce46f41510801016cfd0c3cc1422d3671567`。
- `rihrp-restore-check.service` success: checksum OK、11 テーブル件数一致（users 2 / projects 8 /
  research_documents 5 / audit_events 185 ほか）、restore check OK。
- 復元証跡: `~/.local/state/rihrp/restore-evidence-25f3523.json`（0600、`restored=true`・
  `restored_at=2026-11-13T07:17:04Z`・migration `0005_reports_ai_assisted`）。

## 5. allowlist 設定

- `~/.config/rihrp/rihrp.conf`（0600）に `RIHRP_LLM_ALLOWED_PROJECTS=68489ee7a6ee4d1999d07719673d81fd` を 1 行追加。
  - 既存の `RIHRP_LLM_*`（AI 下書き用）は変更せず、秘密の値は表示・保存していない。
  - **activate より前に設定**（順序を誤ると全プロジェクトで利用可能な窓ができるため）。
- 起動後、本番プロセスの環境に allowlist が入っていることを確認（値は対象プロジェクト ID のみ）。

## 6. Activate

`tools/release_activate.py activate --expect-sha 25f3523… --backup-manifest … --restore-evidence …` → 成功。

- `current` → `releases/25f3523…`、`previous` → `releases/e3f59c6a…`。
- 停止時間: activate の切替のみ（数秒〜十数秒）。

## 7. 配備後の確認

| 項目 | 結果 |
|---|---|
| `/healthz` / `/readyz` | 200・release `25f3523`・manifest 一致・migration `0005_reports_ai_assisted` |
| `/` / `/login` | 200 |
| `/api/auth/me` | 401（未認証） |
| service | active・NRestarts 0・ExecMainStatus 0 |
| journal（5 分・err） | エラーなし |
| allowlist | 本番プロセスの env に `RIHRP_LLM_ALLOWED_PROJECTS=68489ee7…` を確認 |

## 8. 切戻し

- アプリ: `tools/release_activate.py rollback --expect-sha e3f59c6af47a9f2625123944b8b925e9a2e9a1b2`
  （previous の成果物・同じ 0005 migration）。
- 新機能だけ止める: `RIHRP_LLM_ALLOWED_PROJECTS=__disabled__` にして再起動（AI 下書きは不変）。
- DB migration は追加していないため、DB 復元は不要。

## 9. 残り（所有者の確認・観測）

- **UI での確認**: 対象プロジェクト「護岸の洗掘抑制」で 03/04/05 が動き、
  他のプロジェクトでは 403 の案内（ボタン押下時）になること。
- 観測: 期間・週次担当は未確定（パイロット手順 §9 P2/P3）。
- Anthropic Console で tokens/実額を照合（04/05 の実測は input 1,666 / output 4,741、03 は代表 517/1,699）。
- 停止条件に該当した場合は §8 に従う。
