# 本番受入証跡 — コミット別リリース移行（2026-11-03）

## 判定と対象

- **CONDITIONAL GO**: アプリ切替と技術的受入は完了。認証後の本番6ステップ実操作、実機/SR、長期安定性は未確認。
- data_class: `observed`。evidence_id: `rihrp-production-82e6648-20261103T132408Z`。
- 依頼: 本番デプロイに向けて10項目ずつ順次対応。公開/認証/secret/保持方針は変更しない。
- release: `82e664867479cd8c9b6ecdabab4529457342c958`（[PR#13](https://github.com/Kensan196948G/RIHRP-Research-Studio/pull/13) squash merge）。
- runtime manifest SHA-256: `a2e96fa720b42926ab58d82074d32564956f71bab6cc41082ddc78aa558d6af9`。
- 本番URL: https://research.mirai-dx-platform.com （既存Cloudflare Access保護）。
- 本番unit: `rihrp.service`、127.0.0.1:18110、native systemd --user。

## 第1組・第2組の到達点

- 第1組: 現状/条件/配備リスク/backup/復元/DB/認証/監視/品質/判定を実施。[PR#12](https://github.com/Kensan196948G/RIHRP-Research-Studio/pull/12) = `084a3e8`。
- 第2組: release配置、SHA/CI、排他、分離build、固定依存、manifest、runtime識別、切替/復旧、隔離受入、PR/本番判定の10項目を完了。
- 旧deploy.shは使わず、新方式で配備。DBmigration/downgradeは今回0回。

## CI・レビュー・依存

| 証跡 | 対象 | 結果 |
|---|---|---|
| local全量 | PR#13初期版 | 333 passed / 1 skipped、Vitest10、lint/format/OpenAPI/tsc/build成功 |
| 追加回帰 | 最終修正版 | backup非依存rollback、CIrouting固定、実systemdparser、knownmigrationbytepinを追加。build/activate111件成功 |
| PR最終CI | head `6d5f1dd` / run41641355750 | API/Web/Secret scan 3/3 success |
| 手動E2E | head `c70de20` / run41639555720 | 29 passed（1.4分）。最終headの代用として扱わず、下のmergedrelease実受入と区別 |
| main CI | merged82e6648 / run41642451636 | 3/3 success |
| 正式独立レビュー | head6d5f1dd | pass、critical0/high0/medium1/low1。mediumの起動方式差は本番と同じuvicornラッパーの実隔離起動で検証 |
| 正規マージゲート | 同head | 20/20 PASS、MERGED/remote branch削除/tree一致を確認 |
| 固定依存監査 | hash付きruntime requirements | 既知脆弱性なし。実release psycopg3.3.7、pytest/ruff無し |

GitHubのrun番号は実測値。API/Web/secretの成功はCI画面とwatch exit0で確認。CIworkflowのRuff範囲にtoolsが含まれない制約は残り、localCIでは全release*.pyを検査する。

## 実buildと隔離受入

1. main=origin/main=82e6648、clean、main push CI successを確認。
2. builderをexactSHA指定で実行し、`~/.local/share/rihrp/releases/82e6648…/`へarchive/venv/hashsync/npm build。**exit0**。
3. 旧checkout .venv/dist、稼働PID2387641は変更されないことを確認。
4. 新releaseの **`.venv/bin/uvicorn`**（本番unitと同じラッパー）を専用18113/専用`rihrp_test*` DBで起動。
5. **E2E29 passed（1.6分）**、新venv依存・API・Webを通して実行。`release.sha`、manifest hash、配信JS/CSSのbyte一致を確認。
   独立監査でcount付きログの保持不足を指摘されたため、同じrelease/起動ラッパーで再実行して **29 passed/exit0** を再確認。
   log SHA-256 = `146bf6d9d615e30a09656f13bea8508209d4571abbf35b1df02254c95463393b`。
   ローカル証跡: `tmp/production-readiness-batch2/isolated-e2e-final.log` と同名 `.json` にrelease SHA・manifest SHA・port・DB範囲を束縛。
6. 初回の隔離configはmodule設定不足で起動前に失敗した。tmpのESM設定を修正して再実行し成功。失敗を成功に含めない。

## 実systemdの失敗/復旧訓練

- 本番とは別unit `rihrp-release-acceptance.service`、18114/18115、専用testDBを使用。
- 旧専用unitを18114で起動しready確認。候補を意図的に18115へ起動して期待healthを失敗させた。
- activationの復旧処理が旧unit bytes/pointerを復元して再起動。旧専用release ready、pendingなし、unit bytes一致を確認。
- 専用PID903842→908037。本番PID2387641/起動17:42:48は訓練中不変。
- 訓練後に専用unitを停止・削除・daemon-reload。これは初回legacy相当の失敗復旧であり、本番manualrollbackを実行した証拠ではない。

## 配備直前の復旧地点

- backup: `rihrp_production-20261103T132218703528-910688.dump`、対応sha256/manifest、0600。
- 一意の復元DB `rihrp_restore_release_20261103_2223` が不存在であることを確認して実復元。
- 11テーブル件数、checksum、manifest、migration0004一致。users2/projects4/audit31、その他8表0。
- audit immutable/no-truncate triggerが2本ともenabled。復元先名を再確認後、このDBだけ削除。
- 復元成功後にowner0600の `release-restore-evidence-20261103T1323.json` をリポジトリ外へ記録し、dump hashと時刻を束縛。
- 旧unit bytesをリポジトリ外に保存（SHA-256 `c460bef5b9fe6efda8b2235a3f8989886e38d0033d61d090b4897d7db90c3238`）。transition historyにも保存。

## 本番切替・直後受入

- 切替日時: **2026-11-03 22:24:08 JST**。
- before: PID2387641、CWD=開発checkout、起動17:42:48。
- after: PID924746、CWD/ExecStartはrelease82e6648の絶対パス、**active**。
- 設定/公開/認証は既存ファイルのまま。EnvironmentFile mandatory。ProtectSystem=strict、ProtectHome=read-only、ReadWritePaths=/tmp。
- `current` = `releases/82e6648…`、transition-result=succeeded、pending=false、履歴1件。
- `/healthz` 200 ok、`/readyz` 200 ready/migration0004、両方release SHA一致。
- JS SHA-256 = `00862d675a5970a9aa039b20c67086759a02392ab3f2c61b01e3fc08a2d5ffa2`。
- CSS SHA-256 = `3fcf5f32cf3c8e3e0277abeb4f30567ce6f0a1ff05e3979b95f82145d5276c19`。双方ディスクとbyte一致。
- local `/api/auth/me`、`/api/projects`、Assertion無し`/api/auth/access` = **401**。
- public `/`、`/studio`、`/api/auth/me`、`/readyz` = **302**（Access）。
- DB版0004、users2/projects4不変。audit31→32は受入のAssertion無し拒否1件による増加、トリガー2本enabled。
- healthcheck手動再確認22:24:55と定時22:30:03 = Result success/exit0。22:30時点NRestarts=0、切替後priority errのアプリjournalなし。
- 独立受入監査22:28:45: runtime/live asset/manifest全41ファイル再計算一致、判定CONDITIONAL GO。本番Access後操作と長期安定性は未検証と独立に確認。

## 保証しない項目・残条件

- 本番Accessログイン後の通し操作は今回未実施。OTPログイン成功の過去確認と隔離E2Eを本番業務受入の代替にしない。
- 実機/SRは後日。通知なし/外部監視なしの既存決定は維持。
- 同一ホストでの論理backup復元。別ホスト復旧、ホスト喪失、RPO/RTO合否、構成/秘密復旧は未検証。
- manifestはlocalowner信頼・起動時検査であって署名/WORM/起動後常時監視ではない。venv依存コードはmanifest hash対象外。
- 初回移行なので新方式previousは未作成。旧unit bytesは保持するが、本番manualrollbackの実試行はしていない。
- 稼働確認は切替直後の観測。長期安定性や無停止保証を主張しない。

## rollback/次回

通常の新方式間では[手順](../runbooks/immutable-release.md)どおりpreviousへ切戻す。初回旧checkoutへ戻す必要があれば、保存unitと旧checkout/venv/distを照合して手動復旧（本番DBをdowngradeしない）。この証跡PRは文書だけなので再配備しない。
