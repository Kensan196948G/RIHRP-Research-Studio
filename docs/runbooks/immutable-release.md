# Nativeコミット別リリース配備

> **2026-11-03 22:24 JSTに本番切替・技術受入済み（CONDITIONAL GO）**。実行releaseは `82e664867479cd8c9b6ecdabab4529457342c958`。
> 実build、同じuvicornラッパーでの隔離E2E29件、専用unitの実失敗/復旧、直前backup実復元を確認した。
> 証跡と残条件は[本番受入記録](../verification/2026-11-03-production-acceptance.md)。
> この版はDB migration `0005_reports_ai_assisted`（`reports.ai_assisted` の追加のみ）に対応する。
downgradeは行わない。切戻し時も追加列は残す（旧コードは無視する）。

## 配置と信頼境界

- `~/.local/share/rihrp/releases/<40桁SHA>/`: ソースのgit archive、最終絶対パスのvenv、Web dist、migration、hash付き依存lock、manifest。
- `current` / `previous`: `releases/<SHA>` への相対symlink。unitの起動先はsymlinkではなくリリースの絶対パスを使い、稼働旧プロセスのdist参照を新currentへ追従させない。
- 完成markerは `manifest.json`。API/migrations（Python cache除外）/distとlock類の全ファイル一覧とSHA-256を含む。起動時に一覧の欠落・追加・改竄を検出する。
- `.venv` と `node_modules` はファイルhash対象外。依存はcommit済みuv.lock由来のhash付きrequirementsで新venvへ同期し、本番の旧venvを変更しない。
- manifestはローカル所有者を信頼するもので、電子署名/外部attestationではない。同一所有者がmanifestとコードを同時改竄すれば判別できない。起動後の継続的なファイル改竄監視でもない。
- 本番プロセスにはrepo書込みを与えず、systemdのProtectSystem/ProtectHomeでreleaseをreadonlyにする。所有者によるメンテナンスは可能なのでOSレベルのWORMとは異なる。

## 1. Build（本番サービスには触れない）

1. 対象がmainへマージ済みでCI成功・独立レビューのSHAが一致することを確認。
2. `git fetch origin` し、cleanなcheckoutで対象HEADとorigin/mainを一致させる。
3. `python3 tools/release_build.py --expect-sha <40桁SHA>`。

builderは同一SHAのCI成功をリモート照合し、release rootの排他ロックを取る。既存releaseを上書きしない。
依存同期/Webビルドは別release内のみで行い、失敗したディレクトリには完成manifestを作らず調査用に残す。
venvのshebangに絶対パスが入るため、ビルド後にreleaseディレクトリをrename/moveしてはならない。

## 2. 隔離起動と受入

本番confを流用せず、専用 `rihrp_test*` DB・専用loopbackポートで起動する。
`RIHRP_RELEASE_SHA` と `RIHRP_RELEASE_DIR` を両方指定すると起動時整合性検証が有効になる。
`RIHRP_WEB_DIST` もreleaseの実パスを指定する。builder出力の `api_command` と `api_environment` はセットで使い、コマンドだけではlegacyモードになる。
片方だけ・別パス・不一致hashは起動失敗。
従来の開発/テストでは両変数未指定に限り互換動作する。認証/Access処理のテスト用バイパスは追加しない。

- `/healthz` / `/readyz` の `release.sha` と `manifest_sha256` を確認。
- migration0005・asset本文hash・認証前401・主要業務E2Eを検証。
- fake Operationsの正常/失敗/rollbackテストに加え、実systemd切替前に隔離環境で受入する。

## 3. Backupと復元証跡

配備直前に最新バックアップを取得し、一意の専用DBへ実復元してhash・manifest・11表件数・migrationを検証する。
`restore-evidence` は所有者が実測直後に作成する0600のJSONで、以下を含む。

```json
{
  "source_db": "rihrp_production",
  "backup_sha256": "<dumpのSHA-256>",
  "migration": "0005_reports_ai_assisted",
  "restored": true,
  "restored_at": "<UTCのRFC3339時刻>"
}
```

これはローカル運用証跡で、署名付きの第三者証明ではない。未実施の復元をtrueにしない。
activatorは最新manifestとの対応・hash・鮮度（24時間）を検査し、証跡不在/不一致なら切り替えない。

## 4. Activate（隔離検証とマージ後のみ）

```bash
python3 tools/release_activate.py activate --expect-sha <対象の40桁SHA> \
  --backup-manifest <最新のmanifest絶対パス> \
  --restore-evidence <実復元後に作成したJSON絶対パス>
```

- CI/main/clean、manifest inventory、既存本番設定、読取専用DB migration確認を先行。
- 設定ファイルは既存の0600ファイルを使い、秘密の変更・コピーをしない。
- 旧unit bytesと旧current/previousを保存し、current/previous・unitを更新してdaemon-reload/restart。
- 期待SHAのreadinessを期限内に確認できなければ旧unitとpointerを復旧し、1回だけ再起動・旧health確認。
- rollback自体が失敗した場合は自動再試行をせず停止し、手動介入を報告する。

## 5. Rollback

新方式間では `rollback --expect-sha <previousのSHA>` を使う。保持済みprevious成果物の整合性・同じ0005 migrationを確認する。
DBを変更しないアプリ切戻しを妨げないため、rollbackにbackup鮮度/restore証跡/CI/mainのゲートは要求しない。
新規activateでは従来どおり最新backup/restore証跡を必須とする。
旧unitへの初回移行中の例外失敗は自動復旧する。
**0005 へ上げた後に 0004 リリースへ戻すと readyz は `migration_pending` で 503 になる**（旧コードの期待 migration と DB が不一致）。切戻しは 0005 対応リリースへの再 activate か、DB バックアップ復元を伴うものに限る。電源断/強制終了はpending markerを残し、再実行を拒否して手動調査へ回す（自動resumeしない）。
`transitions/` に毎回の旧unit/pointerを保持する。`transition-pending.json` がある場合は保存stateと実unit/pointer/processを照合して復旧し、再受入後にpendingを解除する。
初回の成功後は `previous` に旧checkout版が存在しないため、
旧方式へ手動復旧する場合は保存したunit bytesと当時のcheckout/venv/distの状態を別途確認する。
単にcheckoutを過去へ戻して再ビルドする手順ではない。

## 未確定事項

初回本番切替・隔離起動・隔離unitでのrollback受入は完了。新方式間の本番manualrollback、別ホスト復旧、長期安定性、認証後本番6ステップ実操作は今回未実施。
公開DNS・認証方式・秘密・本番DB削除が必要なら通常配備とは分離して承認を求める。
