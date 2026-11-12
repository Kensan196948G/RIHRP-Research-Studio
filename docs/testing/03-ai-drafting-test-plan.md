# 03. AI 下書き（生成経路）テスト計画

- 版: v1.0（2026-11-12）
- 対象: `POST /api/projects/{id}/ai/draft-claims` と画面の「AI で下書き」
- 関連: [ADR-0006](../adr/0006-ai-drafting.md) / [実AI検証](../verification/2026-11-12-real-ai-verification.md) / [AI機能の変更フロー](04-ai-feature-workflow.md)

## 方針

- 通常の CI は**スタブ**（OpenAI 互換のローカル HTTP）で実行し、実キーを使わない。
- 実キーでの確認は「スモーク 1 回」だけ別途行う（人間の承認後）。CI には入れない。
- 生成物は保存されないこと、鍵がどこにも出ないことを毎回確認する。

## 1. 正常系

| ID | 前提 | 手順 | 期待 |
|---|---|---|---|
| AI-01 | キー設定済み・出典あり | editor が下書き生成 | 200、候補が返る。DB の claims は増えない |
| AI-02 | 同上 | 候補を採用 | claim と evidence が作られ、`verify` が `verified` になる |
| AI-03 | 引用が原文に無い候補 | 生成 | その候補は `valid=false`、UI で採用不可 |
| AI-04 | viewer | 生成 | 403（editor 以上のみ） |

## 2. 設定・失敗系

| ID | 前提 | 期待 |
|---|---|---|
| AI-05 | `RIHRP_LLM_API_KEY` 未設定 | 503 `ai_not_configured`。既存機能は不変 |
| AI-06 | 上流が 401 | 502 `ai_upstream_error`。鍵・本文を応答に出さない |
| AI-07 | 上流がタイムアウト | 504 `ai_timeout` |
| AI-08 | 上流が JSON でない/壊れている | 502 `ai_invalid_output` |
| AI-09 | 入力が上限超 | 413 `source_too_large` |
| AI-10 | 連続実行 | 429 `rate_limited` |
| AI-18 | provider=anthropic | `/messages` へ `x-api-key` で送信し、`content[].text` を解釈する |
| AI-19 | provider が未知の値 | 503 `ai_not_configured`（設定ミスを fail closed） |

## 3. セキュリティ・漏洩

| ID | 確認 | 期待 |
|---|---|---|
| AI-11 | 応答本文・エラー本文 | 鍵文字列を含まない |
| AI-12 | HTML / JS バンドル | 鍵・base URL を含まない（サーバーのみ） |
| AI-13 | 監査ログ | `ai.draft_requested` があり、プロンプト本文・鍵が無い |
| AI-14 | 原文に命令文を混ぜる（プロンプトインジェクション） | 生成物は候補止まり。自動保存されない |

## 4. ブラウザ E2E（スタブ）

| ID | 手順 | 期待 |
|---|---|---|
| AI-15 | ログイン → プロジェクト → 主張タブ → AI 下書き → 出典選択 → 生成 | 候補が表示される |
| AI-16 | 候補を採用 | 主張一覧に追加され、検証で `verified` |
| AI-17 | キー未設定の環境 | 「未設定」表示、生成ボタンで 503 のメッセージ |

## 5. 実キー投入後のスモーク（人間承認後・CI 外）

1. `~/.config/rihrp/rihrp.conf` に `RIHRP_LLM_API_KEY` を 600 で置く。
2. staging を再起動し、`/healthz` と `ai_not_configured` の解消を確認。
3. ブラウザで AI-15/16 を 1 回だけ実行し、所要時間・候補数・有効数を記録。
4. 監査ログと応答に鍵が無いことを確認。
5. 失敗系（鍵を一時的に無効化）は staging でのみ確認し、本番では行わない。
