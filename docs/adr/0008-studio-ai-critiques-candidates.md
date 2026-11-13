# ADR-0008: スタジオ AI による批判・候補の提案（生成のみ・採点は決定論）

- 状態: **採用（PoC）**
- 日付: 2026-11-13（所有者が既定案で実装を承認）
- 関連: [ADR-0002](0002-deterministic-verification.md) / [ADR-0006](0006-ai-drafting.md) / [ADR-0007](0007-studio-ai-debate.md) / [Phase 3 C 設計](../design/04-studio-ai-critiques-candidates.md)

## 背景

Phase 3 B で 03 討論の AI 支援を PoC 実装し、既定 OFF・assist・採用時のみ保存で運用している
（[ADR-0007](0007-studio-ai-debate.md)）。次の拡大候補は 04 根拠・反証の「批判」と、
05 新仮説比較の「候補」である。一方、05 の候補は **スコアと採択** が製品の決定論的な中核で、
AI に採点させると再現性と監査の前提が崩れる。

## 決定

1. **対象は 04 の批判提案と 05 の候補提案（生成のみ）**。検証・スコア・重み・採択・レポートは変更しない。
2. **assist 方式・既定 OFF**。`RIHRP_LLM_*` 未設定なら 503 `ai_not_configured`。既存機能は通常どおり。
3. **生成物は保存しない**。プレビューを確認し「採用」したときだけ研究文書に追加する。
4. **AI は採点しない**。応答に `scores` / `total` / `status` を含めない。採用後に既存の
   `scoreCand()`（決定論）が採点する。AI が返した採点値は破棄する。
5. **批判の重要度（sev）は AI が決めない**。AI は `cat` / `text` / `sug` のみを返し、
   採用時は `sev=低`・`status=未対応` で追加する。重要度は人間が変更する。
6. **候補の `type` は既存 enum に限定**（交互作用 / 閾値 / 代替メカニズム / 複合制御 / 適用範囲 / 分野固有）。
   `vars` は解析済み変数名のみ許可し、未知の変数を含む候補は破棄する。
7. **引用は既存 evidence ID のみ**（付与する場合）。存在しない ID は破棄する。
8. **監査**は `ai.critique_requested` / `ai.candidate_requested` に provider / model / promptVersion /
   件数 / latency を残し、プロンプト・生成本文・鍵は残さない。
9. **レート制限は討論と共通**のバケットを使う（`check_draft_rate`）。
10. **承認の自動化はしない**。採用は研究者の操作で、既存の承認フローとは独立。

## 理由

- 批判は文章の追加に留まり、決定論の対象（検証・スコア）を汚さない。
- 候補は「文面と変数の提案」に限定し、採点を既存関数に固定すれば、AI の有無に関わらず
  同じ入力に対して同じスコアが得られる（再現性・監査の維持）。
- 生成物を保存しないことで、幻覚や注入が研究データへ固定化されるのを防ぐ（ADR-0006/0007 と同じ）。

## 影響

- 追加 API: `POST /api/projects/{id}/ai/critiques`、`POST /api/projects/{id}/ai/candidates`（editor 以上）。
- UI: 04/05 にプレビュー→採用/破棄、AI 提案ラベル、provenance 表示。
- 保存形式: `critiques[]` / `candidates[]` の要素に `origin`（AI 提案）を付け、文書に
  `aiAssist`（工程ごとの provider/model/promptVersion/generatedAt）を追加する（案）。
- テスト: 決定論（採用後のスコアが再計算と一致）、未知 type/vars の破棄、監査、既定 OFF。
- 実装・検証: [検証記録](../verification/2026-11-13-ai-critique-candidate.md) / [テスト計画 08](../testing/08-ai-critique-candidate-test-plan.md)。

## 代替案

- **候補の採点も AI に任せる**: 再現性・監査の前提を壊すため不採用。
- **生成物を自動保存**: 幻覚の固定化と承認境界の曖昧化のため不採用（ADR-0006/0007 と同じ）。
- **02 タスク管理まで対象拡大**: 実行系（承認・状態遷移）に触れるため、Phase 3 C では対象外。

## 実キー canary（2026-11-13）

隔離 DB・3 リクエストで実施。LHT-C4/C5/C6 は PASS（捏造なし・注入拒否・根拠不足の明示）、
AI の採点値は応答に含まれず、監査/tokens も確認した。評定は 2 名（2 名目は AI 再評定・独立性限定的）で全次元「十分」。詳細: [canary 記録](../verification/2026-11-13-ai-critique-candidate-canary.md)。

## 限定パイロット（2026-11-13）

本番で限定運用する場合、`RIHRP_LLM_ALLOWED_PROJECTS`（カンマ区切りのプロジェクト ID）で
対象プロジェクトを限定できる。空なら制限なし。AI 下書きは対象外。
手順: [AI 限定パイロット運用](../operations/ai-pilot-runbook.md)。
