# 2026-11-12 Anthropic（Claude Opus 5.5）実呼び出しスモーク

- 実行: 2026-11-12 19:5x JST（隔離 API `127.0.0.1:18120` / DB `rihrp_test_ai_20261112`）
- 目的: サーバー側 AI 下書きが、Anthropic の実キーで動くことを 1 回だけ確認する。
- 本番: 無変更（稼働中リリース `bfe717d` は AI 下書き以前。外部通信なし）

## 1. 設定の確認（値は表示しない）

| 項目 | 結果 |
|---|---|
| ファイル権限 | `0600` |
| 重複キー | なし |
| `RIHRP_LLM_PROVIDER` | `anthropic` |
| `RIHRP_LLM_BASE_URL` | `https://api.anthropic.com/v1` |
| `RIHRP_LLM_MODEL` | `claude-opus-5-5` |
| `RIHRP_LLM_API_KEY` | 設定済み（108 文字、`sk-ant-` 接頭辞。値は非表示） |
| `RIHRP_LLM_TIMEOUT_SECONDS` | `60` |
| 上限系 | 未設定（既定 8 候補 / 12,000 文字 / 5 回/分） |

Anthropic `GET /v1/models` は **200**、一覧に `claude-opus-5-5` が存在。

## 2. 実呼び出し

| 段階 | 結果 |
|---|---|
| 初回 | **502**（上流 400）。上流理由: `temperature is deprecated for this model.` |
| 修正 | Anthropic 経路から `temperature` を削除。`max_tokens` を 8192 に |
| 再実行 | **200**、所要 **3.9 秒**、候補 3 件・**valid 3 件** |
| meta | `provider=anthropic` / `model=claude-opus-5-5` |
| 応答の鍵 | 含まれない |
| 監査 | `ai.draft_requested` 1 件。`details` は provider/model/候補数/有効数/所要のみで、プロンプト・鍵なし |

生成された候補（例）:

- 「2026年の観測値は42.5%であった。」← 引用「2026年の観測値は 42.5% であった。」（一致）
- 「対象期間は2019年から2023年である。」← 引用一致

## 3. 費用の実測基準

同一内容の直接呼び出しで `usage = {input_tokens: 80, output_tokens: 166（うち thinking 112）}`。
実運用の 12,000 文字入力では入力が数千トークン規模になる。単価は $4/MTok（入力）・$20/MTok（出力）。

再実行の保存証跡: `docs/verification/2026-11-12-real-ai/production_ai_smoke.json`
（本番複製 DB・本番リリース・本番設定。200 / 4.9 秒 / 2 候補）。初回 3.9 秒は会話ログ由来。

## 4. 判定

- サーバー側 AI 下書きは **Anthropic Opus 5.5 で実動作**する。
- キーは応答・監査・画面に出ない。
- 本番へ反映するには、まず新リリース（AI 下書きを含む main）への切替が必要。
