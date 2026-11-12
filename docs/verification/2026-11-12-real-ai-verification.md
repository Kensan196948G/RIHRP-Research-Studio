# 2026-11-12 実AIの生成物を用いた検証エンジン実地試験

- 実行: 2026-11-12 18:07〜18:20 JST（DSH 実モデル + 隔離環境）
- 対象: main `efb04ea`（作業ツリーの追加は `AGENTS.md` のみ）
- 位置づけ: 実 LLM が生成した主張・引用を、製品の検証エンジン（決定論）に通した**実地試験**。
- 関連: [ADR-0002](../adr/0002-deterministic-verification.md) / [ADR-0003](../adr/0003-approval-rule.md)

## 0. 前提（何を「実AI」と呼ぶか）

本製品に LLM 呼び出しは無い。`apps/api/rihrp/verify.py` は ADR-0002 に従い決定論で判定し、
WebUI の「AI エージェント」は `apps/web/src/studio/engine.js` のルールベース処理である。
したがって本試験の「実AI」は、**実 LLM に生成させる側**を指す。

| 役割 | 実体 |
|---|---|
| 主張・引用の生成（Part A/B） | DSH サブエージェント（実モデル。申告 `deepseek-v4` / `DeepSeek (DeepSeek Harness agent)`） |
| 判定 | 製品の `verify_claim()`（変更なし） |
| 保存・認可・承認 | 製品の FastAPI（変更なし） |

## 1. 環境（本番非接触）

| 項目 | 値 |
|---|---|
| DB | `rihrp_test_ai_20261112`（`rihrp_test*` 命名規約内。本番 `rihrp_production` は不使用） |
| API | `127.0.0.1:18120`（本番 `rihrp.service` :8080 とは別プロセス・別 DB） |
| 認証 | 隔離 DB に seed した `editor@rihrp.local` / `reviewer@rihrp.local` |
| マイグレーション | `0004_research_documents` |

本番 DB・本番配備・設定・secret への変更は 0。

## 2. 出典（実データ・スナップショット固定）

| ID | 出典 | 取得元 | 本文 SHA-256 |
|---|---|---|---|
| JMA | 気象庁 日本の年平均気温 | https://www.data.jma.go.jp/cpdinfo/temp/an_jpn.html | `35aa51d9…be14` |
| STAT | 総務省統計局 人口推計（2026年10月公表） | https://www.stat.go.jp/data/jinsui/new.html | `10abdf2b…7a3a` |
| ARXIV | arXiv:2005.14165 GPT-3 | https://arxiv.org/abs/2005.14165 | `7c562309…2bd5` |

本文はローカルへ保存し、その全文をスナップショットとして登録した（`docs/verification/2026-11-12-real-ai/sources/`）。

## 3. Part A: 統制した 24 主張

生成側に「型」だけ指定し、文面は実モデルに書かせた（型の内訳: verified 8 / 数値改変 6 / 引用捏造 6 / アンカー無し 4）。

| 意図した型 | 件数 | 登録時の挙動 | 最終 verdict | 一致 |
|---|---|---|---|---|
| verified（逐語引用＋実在数値） | 8 | 8 登録 | 8 `verified` | **8/8** |
| 数値改変（逐語引用＋1桁改変） | 6 | 6 登録 | 6 `unverified`（`number_not_found`） | **6/6** |
| 引用捏造（本文に無い引用） | 6 | **6 拒否（422 `quote_not_found`）** | 6 `insufficient`（根拠 0 件） | **6/6（入口で遮断）** |
| アンカー無し（数値なし・引用なし） | 4 | 根拠なし | 4 `insufficient` | **4/4** |

- 意図との一致は **24/24**。誤判定（見逃し・過剰検出）は Part A では 0。
- 捏造引用は**検証エンジンに到達しない**。入口（`POST /claims/{id}/evidence`）が原文照合で 422 を返すため、
  主張は「根拠不足（insufficient）」として残る。`contradicted` にはならない。

## 4. Part B: 指示なし／逐語指示の 12 主張

同じ出典から、実モデルに「普通の引用」と「逐語コピー」の 2 群を書かせた。

| 群 | 引用の逐語一致 | 入口通過 | verdict |
|---|---|---|---|
| 自然な引用（指示なし） | 0/6 | **0/6（全件 422）** | 6 `insufficient` |
| 逐語コピー指示 | 6/6 | 6/6 | 5 `verified` / 1 `unverified` |

- 自然な引用は、語順変更・助詞欠落・`…` 省略・改行の結合だけで**全て入口で拒否**された。
- 逐語指示でも 1 件が `unverified`。原因は主張中の順序数「2位」の `2` が原文に単独で存在しないため
  （原文は `①2024年（+1.48℃）、②2023年（+1.29℃）`）。引用自体は逐語一致している。

## 5. 改竄・引用消失（実データ）

| ケース | 操作 | verdict | reasons |
|---|---|---|---|
| T1 本文改竄（SHA は元のまま） | DB の `sources.content` のみ変更 | `contradicted` | `evidence_tampered` |
| T2 善意の編集（本文＋SHA 更新） | 引用が消える形で更新 | `contradicted` | `quote_not_found` |

改竄検出は 2/2 で機能した（登録後に根拠が変わった場合を捕捉）。

## 6. 丸め・順序数の扱い（6 ケース）

実 AI・人間がよく書く「約1.4℃」「約1億2300万人」「2番目」等は、**6/6 が `unverified`** になった。

| 主張の数値 | 原文 | verdict |
|---|---|---|
| 約1.4℃ | 1.44℃ | `unverified`（`1.4` 不在） |
| 約1.2℃ | +1.23℃ | `unverified` |
| 約1億2300万人 | 1億2269万人 | `unverified` |
| 約1330万人 | 1326万3千人 | `unverified` |
| 約3620万人 | 3622万7千人 | `unverified` |
| 2番目 | ② | `unverified`（`2` 不在） |

これは規則どおりの結果（原文に無い数値は `unverified`）だが、**「数値の改変」と「丸め・順序数」を区別しない**。
実 AI の要約では後者が高頻度に出るため、`unverified` の件数は多くなりやすい。

## 7. 承認ゲート（実 AI 出力のレポート）

| レポート | 構成 | 検証サマリ | 承認結果 |
|---|---|---|---|
| R1 | 16 主張（verified 4 / unverified 4 / **捏造引用 4（insufficient）** / 根拠なし 4） | contradicted 0 / unverified 4 / insufficient 8 | **200 approved** |
| R2 | R1 の一部＋改竄由来 `contradicted` 1 | contradicted 1 | **409 `approval_blocked`** |

ADR-0003 のとおり、停止するのは `contradicted` のみ。R1 は**捏造引用 4 件を含むのに承認できた**
（未検証・根拠不足の件数は応答と UI に残る）。

> 本試験の結果を受け、ADR-0003 を改訂した（同日）。AI 支援として提出されたレポートは
> `insufficient = 0` も承認条件に加える。以下の R1 は**改訂前の実測**である。

改訂後の再試験（同日、同じ隔離 DB に `0005` を適用）:

| レポート | 提出 | 結果 |
|---|---|---|
| R3 | `ai_assisted=true`（verified 2 + 捏造引用 4） | **409 `approval_blocked`**（insufficient 4 / contradicted 0） |
| R4 | 通常提出（同じ内容・対照） | 200 approved（従来ルールのまま） |

証跡: `docs/verification/2026-11-12-real-ai/post_policy_recheck.json`

## 8. 知見

1. **入口ガードは強い**。捏造引用は 6/6 で登録前に拒否され、DB に入らない。
2. **数値幻覚の検出は確実**。数値改変 6/6 を `unverified` で捕捉。
3. **実 AI の自然な引用は通らない**。逐語指示なしでは 0/6。引用の逐語性を利用者に要求する設計であり、
   AI に書かせる導線では「原文をそのままコピーさせる」支援が要る。
4. **捏造引用は `contradicted` にならない**。入口で拒否されるため `insufficient` に落ち、
   ADR-0003 の承認条件（contradicted = 0）を満たしてしまう。実 AI のレポートでは
   「最頻の幻覚が、最も弱い停止条件に落ちる」構造になる。
5. **丸め・順序数は `unverified` に集まる**。誤りではないが、レビュー時のノイズになりやすい。

## 9. 限界

- 出典は 3 件・主張は 44 件（Part A 24 + Part B 12 + 丸め 6 + 改竄 2）で、統計的な代表性は無い。
- 生成モデルは 1 系統。モデル差・温度差は未測定。
- 自然引用の拒否は「入口 422」であり、UI 上の見え方（エラートースト）は未確認。
- 本試験は製品コードを変更していない。したがって「直すべきか」は別判断。

## 10. 証跡

| 証跡 | パス |
|---|---|
| 生成ブリーフ（出典全文・型指定） | `docs/verification/2026-11-12-real-ai/brief_generate.md` |
| Part A 生成物 | `docs/verification/2026-11-12-real-ai/claims.json` |
| Part A 実行結果（24 件） | `docs/verification/2026-11-12-real-ai/results.json` |
| Part B 生成物 | `docs/verification/2026-11-12-real-ai/claims_free.json` |
| Part B・承認ゲート結果 | `docs/verification/2026-11-12-real-ai/free_results.json` |
| 改竄試験 | `docs/verification/2026-11-12-real-ai/tamper_results.json` |
| 丸め試験 | `docs/verification/2026-11-12-real-ai/rounding_results.json` |
| 実行スクリプト | `docs/verification/2026-11-12-real-ai/{driver,driver_free,tamper,rounding,report_gate}.py` |
| 出典スナップショット | `docs/verification/2026-11-12-real-ai/sources/{jma,stat,arxiv}.txt` |
| 再実行手順 | `docs/verification/2026-11-12-real-ai/README.md` |

## 11. 実行主体・Skill・資格情報

| 項目 | 実態 |
|---|---|
| AI エージェント | DSH サブエージェント 2 回（Part A / Part B）。生成物にモデル申告 `deepseek-v4` / `DeepSeek (DeepSeek Harness agent)` を記録 |
| Skill | **実施時点では未適用**。記録作成後に `llm-hallucination-testing` を適用し、優先度・Human 判断境界・残リスクの記載を補った（§12） |
| API キー | **追加・保存なし**。DSH の既存プロバイダ設定で実行。製品側は LLM を呼ばない。リポジトリ／環境変数への鍵の書込みは 0 |
| ネットワーク | 出典取得は公開 HTTP のみ（3 URL）。認証情報は使っていない |

## 12. 残リスクと優先度（提案）

| 優先 | リスク | 状態 | 終了条件 |
|---|---|---|---|
| P1 | 捏造引用が `insufficient` に落ち、承認が通る | **完了**（ADR-0003 改訂 + R3 で 409 を実測） | 済 |
| P1 | `ai_assisted` は自己申告のため、虚偽申告を防げない | 未対応 | AI 生成物を扱う運用で申告を必須にする統制（別判断） |
| P2 | 実 AI の自然な引用が入口で全滅（0/6） | 未対応 | 原文コピー支援または正規化一致を設計し、通過率を再測 |
| P2 | 丸め・順序数が `unverified` に集まりレビュー負荷になる | 仕様どおり（未対応） | 表記ルール／許容範囲を決める（プロダクト判断） |
| P3 | モデル 1 系統・出典 3 件で代表性が無い | 未対応 | モデル・出典・温度を増やして再試験 |

Human 判断が必要な点: 承認ポリシーの正否（P1 の統制）、自然引用をどこまで許すか（P2）、丸めの扱い（P2）。
本記録は実行証跡であり、これらの受容・承認は行っていない。
