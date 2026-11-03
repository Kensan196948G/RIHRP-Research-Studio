# 本番準備 第1組10項目 — 2026-11-03

## 範囲・判定

- 依頼: 本番デプロイへ向けて10項目ずつ提示し、順次対応する。
- 開始時: `main=origin/main=4f40dfbad0f744b10e18d59f026d0a791543279e`、clean。
- **現行サービスの継続稼働: CONDITIONAL GO**（観測時health/readiness正常、既存の通知なし・実機確認保留を維持）。
- **旧方式による次回コード配備: NO-GO**。稼働ツリーへの依存更新/ビルドと切戻しの不備を解消してから進める。
- この変更は事前検査と手順/証跡のみ。本番サービスの再起動・依存更新・migration・公開設定変更・本番データ削除は行わない。

## 10項目の結果

| # | 項目 | 観測/対応 | 判定 |
|---|---|---|---|
| 1 | 現状確認 | 20:10 JSTにrihrp.service/Tunnel active。サービス起動17:42:48、WorkingDirectoryは開発checkoutと同じ。readyz migration0004 | 観測済み。runtime SHAは未識別 |
| 2 | リリース条件 | 許可2名、監査削除timer有効、タグ作成済みなのに旧記載が残存。[release](../runbooks/release.md)/[operations](../runbooks/operations.md)を是正 | 文書更新 |
| 3 | 配備手順 | 独立レビューでSHA固定/clean/排他/原子的配置/自動切戻し/事前バックアップが強制されないことを確認。旧方式の使用停止を文書化 | 次回コード配備NO-GO |
| 4 | バックアップ | 20:12 JSTに新規dump+sha256+manifest取得。既存バックアップ削除なし。ファイル名は後述 | PASS |
| 5 | 復元訓練 | 一意の隔離DB `rihrp_restore_release_20261103_2013` へ復元。SHA/manifest/11テーブル件数/migration一致、監査トリガー2本有効。検査後このDBだけ削除 | PASS |
| 6 | DB/migration | 本番0004、app superuser=false/createdb=false/schema CREATE=false。audit DELETE権限はあるがimmutableトリガー有効。admin/editor各1、有効ユーザー2 | 読み取り観測済み |
| 7 | 認証/公開境界 | local保護API401、public4経路はcurlで302。Cloudflare policyは個別email2件のみ。実プロセスのallowlistも2件 | 負の境界PASS。値同一性/認証後通し操作は別確認 |
| 8 | 監視/保守 | 5timer enabled/active。backup/restore/maintenance/audit-purge/healthcheckの直近Result success。アプリ起動後priority errのjournalなし | 観測済み。初回日次定時到来は翌日 |
| 9 | 品質 | 基準main CI41624543437 success、PR#11 E2E41623804832=29 passed。新規事前検査32 unit pass（PRレビュー後に組同一性の回帰1件追加）、最終全量180 passed/1 skipped・Vitest10・ruff/format/OpenAPI/tsc/build成功、専用DBのE2E29 passed（1.6分） | 検証中 |
| 10 | 受入と記録 | 独立再レビューblockingなし。通常PR・CI・正規ゲートによるマージ後に第2組へ進む | ローカル受入済み・PR待ち |

## 本番の詳細観測

- `/healthz` = `ok`、`/readyz` = `ready` / `0004_research_documents`。
- `/`、`/studio`、`/login` = 200（ローカルシェル）。`/api/auth/me`、`/api/projects`、Assertion無し`/api/auth/access` = 401。
- 公開 `/`、`/studio`、`/api/auth/me`、`/readyz` = 302（curl、リダイレクト追跡なし）。Python urllib経由では403が返ったため、クライアント差として記録する。いずれも認証前に業務本文が公開されないことだけを確認し、403の原因は断定しない。
- 配信JS `index-DVHMzgdV.js` SHA-256 = `00862d675a5970a9aa039b20c67086759a02392ab3f2c61b01e3fc08a2d5ffa2`。
- 配信CSS `index-0NYY7o4j.css` SHA-256 = `3fcf5f32cf3c8e3e0277abeb4f30567ce6f0a1ff05e3979b95f82145d5276c19`。
- 配信物とディスクのdistはbyte一致。ただしcheckoutのHEADやdist一致だけでPython実プロセスのcommitを証明したことにはしない。
- 実プロセス設定: production / Secure Cookie=true / demo seed=false / Access信頼=true / 自動provision=false / allowlist_count=2。
- Cloudflare（GETのみ）: アプリは対象hostnameのself_hosted、session 24h。allow policy1件、email rule2、domain/everyone等なし。
- 通知先は未設定。ユーザーが既に「通知なし・外部監視なし」を選択済みなので、勝手に変更しない。

## 復旧証跡

- backup: `rihrp_production-20261103T111248538677-3735287.dump`（リポジトリ外、0600）。
- 同名 `.sha256` / `.manifest.json` を生成。バックアップ対象DBは `rihrp_production`。
- 復元先は事前に不存在を確認した一意の専用DB。本番/既存の `rihrp_restore_prod` には触れない。
- 件数一致: users2、projects4、audit_events31、その他8表0。
- migration `0004_research_documents`、`trg_audit_immutable` / `trg_audit_no_truncate` = O。
- 復元後も本番readyz正常。専用DBは名前とcurrent_databaseを再確認後に削除。
- これは同一ホストの論理復元訓練。別ホスト復元、ホスト喪失、RPO/RTOの合否、構成/秘密の復旧は保証しない。

## 検証中の失敗と分離

- 初回全量実行はログイン401で8件失敗（164 passed / 1 skipped）。共有 `rihrp_test` の一時干渉を疑ったが、実行後のprocess一覧だけでは原因を確定できないため断定しない。
- 別の `rihrp_test_readiness_20261103_2024` を作成し、この作業だけのDBとして品質検証を再実行する。本番DBへは接続しない。成功した再実行と失敗した初回は区別する。

## 追加する事前検査

[release_preflight.py](../../tools/release_preflight.py) は読み取り専用で、40桁SHA、HEAD/origin/main一致、clean tree、新鮮な本番バックアップのSHA/sidecar/manifest/11表/migrationを検査する。失敗時は非0。
ネットワーク、DB、サービス、本番設定を変更しない。CI成功、独立レビュー、実プロセスのSHA、配備許可そのものは証明しない。origin/mainはローカルremote-tracking refでありリモート鮮度を保証しないため、実配備では直前のfetchとリモートCI照合が別途必須。

- PRレビューmedium2の対応: manifestファイル名と参照dumpの組同一性を強制する回帰1件を追加。ローカルrefの鮮度はネットワークなしCLIの保証外としてrunbookにfetch前提を明記。

- 初回レビューの中2/低3を修正: production名のDB識別不一致を拒否、Git環境変数による別checkout参照を防止、countのbigint上限、JSON/sidecarサイズ・深度・巨大整数の例外、max-age上限を追加。
- `pytest tests/unit/test_release_preflight.py -q`: 初回32 passed、PR指摘後の追加回帰を含め **33 passed**。CLIの正常系・dirty/SHA・stale/future・hash・symlink・最新破損fallback・Git環境汚染・巨大入力を検証。
- 本物のバックアップに対するCLI負の対照: 作業中ツリーだけを失敗として検出し、backup関係6検査は成功。全文・接続文字列・個人情報は出力しない。
- 基準SHAのcleanな一時cloneに対して現行CLIを実行: **9/9検査成功、exit0**。実checkout/本番プロセスは変更しない。

## 第2組（次の10項目、実測後に順次対応）

1. コミット別のリリース配置先と可変データ境界を確定。
2. 配備SHA・clean・CIのゲートを配備入口へ実装。
3. 配備全体の排他ロックと途中失敗記録を追加。
4. 稼働先と分離してPython環境・Web成果物を組み立てる。
5. Python依存の再現可能性と本番dev依存除外を整備。
6. 配備manifestにSHA・成果物hash・migration・バックアップを束縛。
7. current/previous切替とhealth失敗時アプリrollbackを実装。
8. 隔離環境で正常配備・途中失敗・rollbackを回帰検証。
9. 独立レビュー/PR/CI/正規マージ後、本番切替の前提を再確認。
10. 前提が揃えば本番へ段階反映し、SHA・静的asset・認証・監視を受入検証。

高リスクな公開/認証/秘密変更・本番データ削除が必要なら、通常PRと分離して人間の承認を求める。
