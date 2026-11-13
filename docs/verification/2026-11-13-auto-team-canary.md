# auto-team web canary（2026-11-13）

- 対象: Phase 2「Agent Team の自動編成」の行動受容
- 関連: [05-automation-3layers.md](../testing/05-automation-3layers.md) / [auto-team PR #146](https://github.com/Kensan196948G/Deep-Seek-Harness-Project/pull/146)
- 目的: `agent/pre-step` のプレイブック注入後に、**2件以上の team_task と1名以上の spawn** が行われ、
  完了後に孤児メンバー・未完了タスクが残らないことを確認する。

## 環境

- DSH: repo ローカル `node_modules/.bin/dsh`（`0.2.1-rc.4`）。
  nvm の global `dsh` では後述の `prepare` エラーが再現したため、ローカル dsh を使用した。
- Web: 別ポート **3099**（`127.0.0.1` のみ）。既存の 3080 は停止していない。
- 一時 patch: `bot` を無効化（標準コーディング UI を出す）＋ `auto-team` plugin を insert。
- 環境変数: `DSH_AUTO_TEAM=1`。秘密は systemd の `EnvironmentFile` から渡し、値は扱っていない。
- ワークスペース: `RIHRP-Research-Studio`。作業は read-only。

## 手順

1. 一時 unit で web を起動し、`/` の token URL を取得（journal）。
2. Headless Chromium（Playwright）で UI を開き、ワークスペースを選び、新規セッションを作成。
3. trigger 発話を送信:
   「Agent Team で分担して、次の2つを並行で調べて、3行以内で報告して:
   (1) このワークスペースのファイル数 (2) 空きディスク容量」
4. セッションログ（`~/.dsh/sessions/<cwd>/session-*/session.v4.jsonl.zstd`）で
   `plugin:auto-team`、`team_task_create`、`spawn_teammate`、`wait_agent`、`turn/end` を確認。
5. 2回目の run で 1タスク・1名 spawn の経路も確認。

## 結果

| run | session | 注入 | team_task | spawn | 完了 |
|---|---|---|---|---|---|
| 1 | `321beeb1` | `source.kind: plugin:auto-team` | 2件（task-1 / task-2） | 2名（file-census / disk-free） | `turn/end: completed`、`wait_agent: no-active-peer` |
| 2 | `f37bee37` | 同上 | 1件 | 1名（sleeper） | `turn/end: completed` |

- run1 の最終回答: ファイル数 3,607（`.git` 含む総数 23,619）／空き 113G・使用率 88%。
  いずれも read-only の実測値。
- 両 run とも完了時点で稼働中のメンバーは `lead` のみ。**孤児メンバー・未完了タスクなし**。

## 中断テスト（2026-11-13）

- 手順: 1名に `sleep 60` を任せて spawn させ、spawn 後に UI の `Stop generating` で turn を中断。
  次の turn で `list_agents` / `team_task_list` を実行し、残存状態を確認した。
- 結果（session `9da0f21c`）:
  - 中断前: `team_task_create` 1件、`spawn_teammate` 1名（sleeper）、`wait_agent` 実行中。
  - `turn/end` は `aborted`（reason: user）。
  - 中断直後: **sleeper は `running` のまま残り**、task-1 も未完了（revision 2）で残った。
  - 次の turn で `interrupt_agent(sleeper)` → `inactive`、`team_task_update(release)` →
    task-1 は pending に戻った。**自動ではクリーンアップされない**。
- 1回目の中断試行（session `3d997df3`）は spawn 前に Stop したため、中断テストとしては不成立。
- 対策: プレイブックに復旧手順（次の turn で `list_agents` → `interrupt_agent` → `delete`/`release`）を追加
  （Deep-Seek-Harness-Project PR #148、`90fadce`）。ただし自動クリーンアップではなく、モデルへの誘導。

## 判明した環境事象

1. **global dsh と profile 依存の不一致**: nvm の global `dsh` で起動すると、ツール実行が
   `Cannot read properties of undefined (reading 'prepare')` で失敗する。repo ローカルの
   `node_modules/.bin/dsh` では成功する。canary はローカル dsh を使うこと。
2. **headless の同エラー**: headless でも patch なしの `bash` で再現する。headless 固有の欠陥で、
   Agent Team / auto-team plugin の欠陥ではない。
3. **DS Bot の誤爆**: 初回に DS Bot アプリへテスト発話が入り、同じ `prepare` エラーで失敗した
   （`session-152703fb…`）。canary では `bot` を無効化して標準 UI を使うこと。

## 残課題

- **中断時の自動クリーンアップ**は未実装。手動復旧（interrupt_agent + release/delete）は
  実測済みで、プレイブックに復旧手順を追加した。自動化には harness 側で turn abort 時に
  teammate を停止する仕組みが必要（別承認・将来課題）。
- 承認・本番変更・secret 参照は行っていない。

## 後始末

- 一時 canary web（3099）は停止済み。一時 patch と一時プロファイルは削除済み。
- 既存 3080・本番 DB・secret・プロファイル設定は不変。
