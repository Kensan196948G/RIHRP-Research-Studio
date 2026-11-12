# 05. AI 開発・検証の全自動化（3層）

- 版: v0.1（2026-11-12）
- 対象: ①Skill の自動適用 ②Agent Team の自動編成 ③スタジオの AI 化／全自動実行
- 非目的: 承認の自動化、決定論的検証（ADR-0002）の置換

## Phase 1: Skill の自動適用

### 拡張点（実測）

DSH の `agent/pre-step` waterfall に prepend し、下流のメッセージを見た後に
plugin メッセージを追加できる（既存 `harness/plugins/memory-recall.mjs` と同型）。
`ctx.skills` は Skill カタログ、`system-prompt/assemble` はプロンプトへの寄与点。

### 設計

- ユーザー発話のキーワード → Skill の対応表（既定は AI 機能・テスト記録・Skill 作成）。
- 一致した Skill の `SKILL.md` 本文を **1セッション1回**だけ plugin メッセージとして注入。
- 上限: 最大2 Skill / 各2,000文字 / 合計4,000文字。
- 既定 **OFF**（`DSH_AUTO_SKILL=1` で有効）。読取失敗・不一致は素通し（fail-open）。
- 注入は `<!-- auto-skill:<name> -->` マーカー付きで、重複注入を防ぐ。
- 監査: セッションログに plugin メッセージとして残る（モデル可視＝記録）。

### PoC 実測（2026-11-12）

- DSH の worktree ブランチ `auto/auto-skill`（commit `952ec62`）に実装。既定 OFF。
- 単体テスト **9 件 pass**（規則5・ハンドラ4）。
- 隔離 `DSH_HOME` + `--patch`: `--dump-config` で plugin 登録を確認。
- 隔離 `headless`: **MISSING_CREDENTIAL** で停止（plugin ではなく、headless の provider 資格情報が
  隔離ホームへ移植できないため）。plugin の欠陥ではない。
- **実ホーム + 一時 patch（プロファイル非変更）**で headless を1回実行:
  - セッションログ（zstd 解凍）に `auto-skill:ai-feature-testing` と
    `AUTO-SKILL] llm-hallucination-testing` を**各1回**確認。
  - 出力は Skill の内容を参照した回答になった。
- 受入: 「1セッション1回」「ログから再構成」「無効/失敗時の素通し」を確認。
- 残: 隔離ホームでの実測は、API キーまたは grant の移植を前提とする（別手順）。

### 実装完了（2026-11-12）

- DSH 本体へマージ済み: PR #144（`6805b69`）+ PR #145（`fefe37b`）。
- テストを `tests/node/` へ移し、`npm test` の対象に含めた（CI 回帰）。
- 検証: `npm test` 769 / pass 736 / fail 0 / skip 33、`npm run validate` OK、
  `./start.sh compatibility` PASS、Required Checks 5/5 pass。
- **既定 OFF**。有効化は `DSH_AUTO_SKILL=1` と `--patch`（またはプロファイル登録）。

### 誤検知の修正（2026-11-12）

- Phase 2 PoC の実測中に、`agent/pre-step` が実ユーザー発話の後ろへ追加する
  skill catalog を発話として読んでいたため、**無関係な発話でも Skill が注入される**
  ことを確認した（「今日の天気を教えて」で `ai-feature-testing` /
  `llm-hallucination-testing` を注入）。
- 修正: `source.kind=user` の実ユーザー発話だけを判定対象にした（PR #147、`833edd5`）。
- 実測: 無関係発話→注入なし / 「AI機能のテスト設計」→2 Skill 注入。
- 本節の受入（「キーワードを含む発話で注入」）は、修正後に成立する。

### 受入

- キーワードを含む発話で、対象 Skill の本文が1回だけ注入される。
- 2回目の発話では再注入されない。
- 無効時・読取失敗時にセッションが止まらない。
- 注入メッセージがセッションログから再構成できる。

## Phase 2: Agent Team の自動編成

### 現状

`team_task_*` と `spawn_teammate` は**モデルが呼ぶツール**であり、イベントではない。
プラグインから直接「自動で spawn」することはできない。

### 設計（案）

- `agent/pre-step` で QA/実装タスクを検知し、「Agent Team を使う手順」を Phase 1 と同様に注入する（プロンプト誘導）。
- より強い自動化は、`workflow` ツールのスクリプトを雛形として用意し、定型タスクを1コマンドでファンアウトする。
- 上限: 同時メンバー3、タスク数10、書込みスコープを分離。承認・本番変更は自動化しない。

### 設計（詳細）

**トリガー**: 「実装して」「テストして」「検証して」「並列で」等の語を含む発話。

**注入するプレイブック（Phase 1 と同じ `agent/pre-step`）**:

1. 役割を決める（実装 / 独立検証 / レビュー。最大3名）。
2. `team_task_create` で作業単位を作る。各タスクに `write_scopes`（書込み範囲）と完了条件を書く。
3. `spawn_teammate` を fresh で起動し、各プロンプトに
   「task を get → claim → 指定 Skill をロード → 作業 → complete → send_message」を固定する。
4. Lead は完了を待ち、diff・テスト・CI を確認してから統合する。
5. 完了後にメンバーを停止し、未完了タスクを整理する。

**上限**: 同時3名 / タスク10件 / 書込みスコープは重複させない。
本番変更・secret 参照・承認は自動化しない。

**自動化の境界（正直な制約）**: `spawn_teammate` は**モデルが呼ぶツール**であり、
プラグインから直接起動できない。したがって Phase 2 の「自動」は
**プレイブック注入による誘導**まで。完全自動 spawn には harness 側の新ツールが必要（別承認）。

### PoC 実測（2026-11-12）

- DSH の worktree ブランチ `auto/auto-team` に実装（PR #146）。
- 単体テスト **7 件 pass**（純関数 3・ハンドラ 4）。
  - 1セッション1回・無効時/不一致/中断時の素通しを確認。
  - `agent/pre-step` が実発話の後ろに追加する context メッセージではなく、
    実ユーザー発話（`source.kind=user`）だけで判定する。
  - 追記メッセージにだけトリガー語がある場合は注入しない（回帰テスト）。
- `npm test`: 776 tests / pass 743 / fail 0 / skip 33。`npm run validate` OK。
- 隔離 `DSH_HOME` + `--patch`: `--dump-config` で alias `auto-team` の登録を確認。
- **実ホーム + 一時 patch（プロファイル非変更）**で headless を1回実行:
  - セッションログに `source.kind: plugin:auto-team` と `<!-- auto-team -->` の
    plugin メッセージを確認（注入成立）。
- 残（canary）: headless プロファイルは Agent Team ツール（`team_task_*` /
  `spawn_teammate`）を持たないため、「2件以上の team_task と1名以上の spawn」の
  行動受容は web プロファイルで確認する。
- 環境注記: headless のツール実行時に
  `Cannot read properties of undefined (reading 'prepare')` が出るが、
  **patch なしでも再現**する環境側の事象で、本 plugin の欠陥ではない。

### 実装完了（2026-11-12）

- DSH 本体へマージ済み: PR #146（`28e3f09`）。
- テストは `tests/node/` にあり `npm test` の対象（CI 回帰）。
- 検証: `npm test` 776 / pass 743 / fail 0 / skip 33、`npm run validate` OK、
  Required Checks 5/5 pass。
- **既定 OFF**。有効化は `DSH_AUTO_TEAM=1` と `--patch`（またはプロファイル登録）。

### 受入

- プレイブック注入後、定型タスクで **2件以上の team_task と1名以上の spawn** が行われる。
- 証跡: セッションイベントと team_task ボードで確認できる。
- 失敗時・中断時に、孤児メンバーと未完了タスクが残らない。

## Phase 3: スタジオ

### 決定（2026-11-13）

| 案 | 内容 | 判断 |
|---|---|---|
| A. 自動実行 | 01〜06 をワンクリックで通す（UI のみ） | **採用・実装**（本節） |
| B. AI 化 | ルールベースを LLM に置換 | 未着手。コスト・非決定・オフライン前提の変更を伴うため別承認 |

### 実装（A案）

- 01 の「▶ ワンクリックで 01〜06 を実行」（02 にも同ボタン）で開始。
- 02 → 03（討論の再生完了を待つ）→ 04 → 05 → 06 を自動で切り替え、各ステップは最低 0.9 秒表示する。
- 承認待ちでは 02 に戻って停止し、「承認待ちのため一時停止中」を表示する。**自動承認はしない**。
  研究者の承認後に同じ段階から再開する。
- ツアーバーの「停止」で自動進行と実行を停止する。手動ナビ時は自動進行のみ解除し、タスクは継続する。
- 完了時は 06 へ遷移してトーストを出す。再読込でツアー状態は復元しない（セッション内 UI）。
- 実装: `apps/web/src/studio/engine.js`（`RT.tour` / `RT.tourStage` と 300ms の専用タイマー）。
  プロトタイプ HTML は変更しない。詳細仕様は `docs/design/02-offline-studio-spec.md` §3.7 / §5.3。

### 受入

- 01 からワンクリックで開始し、02〜06 を順に通って 06 に到達する。
- 承認待ちで自動進行が止まり、承認後に再開する（承認の自動化はない）。
- ツアーの停止で実行が止まり、進行タイマー・未処理の自動移動が残らない。
- 既存の手動操作（研究フロー開始・実行開始・全体を再実行）が従来どおり動く。

### 実測（2026-11-13）

- `P3-01`（Playwright / Chromium）: 01 から開始して 02〜05 を通過、verify / evaluate の
  承認待ちで停止表示、承認後に 06 到達。**14.2 秒 / PASS**。
- `P3-02`: ツアーバーの「停止」でバーが消え、02 が「停止中」になる。**0.94 秒 / PASS**。
- 全体: `npx playwright test` **43 passed / 1 skipped / 0 failed**（スタジオ spec 28 件を含む）、
  `npm run build` OK、vitest **10 件 PASS**。
- 詳細: [02-detailed-test-spec.md](02-detailed-test-spec.md) §14。
- 残: B案（LLM 置換）は未着手（別承認）。

## リスク

- 誤適用によるトークン消費・指示の混入
- プロンプトインジェクション（Skill 本文以外を注入しない）
- 自動化の広がりによるコスト・権限の増大
- 監査不能な自動判断（承認は自動化しない）

## ロールアウト

既定 OFF → 隔離 DSH_HOME で PoC → 1プロファイルで canary → 既定 ON。
各段階で受入証跡を残す。
