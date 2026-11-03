# 本番準備 第2組 — コミット別リリース・切戻し（検証中）

## 境界

- 基準main: `084a3e820994a2380c734ed813b3b39b47e08cce`（第1組PR#12、main CI41630924462 success）。
- 本番は旧checkout構成で継続稼働。現段階ではrestart・unit更新・本番migration/公開/認証/secret変更なし。
- DBは0004のままのみ対応。DB自動migration/downgradeは行わない。
- コミット別releaseは所有者を信頼するlocal integrity機構であり、WORM/署名付きattestationではない。

## 10項目

| # | 内容 | 状態 |
|---|---|---|
| 1 | releases/fullSHAへ配置 | builder実装、既存target上書き拒否 |
| 2 | SHA/clean/CIゲート | HEAD=origin/main=期待SHA、exactSHAのCI successを確認。fetchは直前operator前提 |
| 3 | 排他 | build/activate/rollbackは同じ.release.lockを使用 |
| 4 | 分離ビルド | git archiveを別releaseへ展開、元checkout/.venv/distを変更しない |
| 5 | 固定依存 | uv.lockとhash付きrequirements-production.txtを追加。新venv --copies、dev依存を同期対象外 |
| 6 | manifest | API/migration/dist/locksの全一覧hash、schema1/SHA/0004/built_atを最後に公開 |
| 7 | 実行版 | release mode起動時のhash照合とhealth/readinessのrelease識別子。legacyは互換 |
| 8 | 切替/切戻し | 絶対releaseパスunit、current/previous、旧unit bytes保存、activation失敗時旧状態復旧。rollback失敗は再試行しない |
| 9 | 隔離検証 | fake runner/Operationsとtmpによるbuild/runtime/activate回帰151ケースがumask0022で成功、その後完了journal失敗回帰を加え最新152件成功（activate25件）。最新全量333 passed/1 skipped、Vitest10/build、E2E29 passed（1.6分）。実起動は未実施 |
| 10 | PR/本番判定 | 未PR。レビュー・CI・隔離実起動/切戻し受入後に本番可否を判定 |

## 実装レビュー中の修正

- 中断した生成agentが残したコードを親が読み直して統合。manifest名の不一致、例外dataclassのfrozenでcontextlibがTypeErrorになる欠陥、venv symlink/コピー契約、旧unit bytesのbase64誤復号を修正。
- CIは古いsuccess1件だけでは通さず取得した対象runがすべてsuccessであることを確認。
- runtime/activatorにindex.html、UTC built_at、exact inventoryを要求。snapshot検証は起動時のみ。
- rollback stateは履歴として保存し、pending markerが残った強制終了は再実行を拒否して手動調査へ。自動resumeを保証しない。
- restore-evidenceは所有者0600、最新backup hash/0004/freshnessに対応することを確認。dumpの意味的復元可能性は別実復元の証跡であり、CLIだけでは証明しない。
- directory fsync失敗を握りつぶさず切替前に停止。旧unitのspecial mode bitsをcapture前に拒否。evidence fixtureはumask依存をなくし0600を明示、umask0022でもactivator24件成功。
- activatorがDB確認で使う資格情報は既存0600confから子プロセスだけへ読み込み、出力しない。public route/認証ロジックには変更なし。

## 依存監査

- uv0.12.5でlock/export（本番venvにinstallなし）。`uv lock --check`成功。
- 固定runtime requirementsに対するpip-audit: 既知脆弱性なし。
- 旧venvとの主な差: psycopg/psycopg-binary3.3.6→3.3.7。新release環境で受入が必要。

## 限界・未実施

- fake testsは実systemd/実package install/本番Accessを通すものではない。
- 初回legacy復旧は旧unit/health正常までを確認し、旧runtime SHAは識別不能。
- release manifestの信頼元はローカル所有者。venv内のPython/依存コードは起動hash対象外。
- 既存unit drop-inは観測時なし。新方式移行でdrop-in/実プロセスが期待値どおりか受入で確認する。
- 第1組の「全量180」は33番目の追加回帰前の値（最終headのCIは成功）。過去件数と追加テスト数を混同しない。
- この時点で本番配備済みとは宣言しない。
