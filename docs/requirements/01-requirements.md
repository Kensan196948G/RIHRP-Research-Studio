# RIHRP Research Studio — 要件定義（Requirements）

- 版: v0.1（提案ドラフト / ユーザー最終承認待ち）
- 日付: 2026-11-02
- 関連: `docs/concept/01-concept.md`、`docs/architecture/01-architecture.md`、ADR-0001〜0005

## 1. 機能要件

### FR-1 認証・セッション

- FR-1.1 メールアドレスとパスワードでログインできる。
- FR-1.2 セッションは HttpOnly / SameSite=Lax Cookie。`production` では Secure。
- FR-1.3 状態変更 API は CSRF トークン（Cookie + `X-CSRF-Token` ヘッダー）を要求する。
- FR-1.4 ログイン失敗はレート制限され、失敗理由は「認証情報が一致しない」に統一する（ユーザー存在の推測を防ぐ）。
- FR-1.5 ログアウトでサーバー側セッションを無効化する。

### FR-2 テーマ（Project）

- FR-2.1 editor 以上はテーマを作成・更新できる。admin は削除できる。
- FR-2.2 一覧は要対応件数（未検証・矛盾・レビュー待ち・差し戻し）を含む。
- FR-2.3 テーマ詳細は概要・出典・主張・レポートを返す。

### FR-3 出典（Source）とスナップショット

- FR-3.1 出典は kind（url / doi / text）と origin（URL・DOI・任意ラベル）と title を持つ。
- FR-3.2 登録時に本文（content）を必須とし、UTF-8 バイト列の SHA-256 を保存する。
- FR-3.3 同一テーマ内で同一 SHA-256 の出典は重複登録できない（409）。
- FR-3.4 読み出し時に SHA-256 を再計算し、不一致なら `tampered: true` を返す（削除・上書き API は提供しない）。
- FR-3.5 出典本文の最大長は 1 MiB。

### FR-4 主張（Claim）と根拠（Evidence）

- FR-4.1 主張はテーマに属し、本文（10〜2000 文字）を持つ。
- FR-4.2 主張には複数の根拠を結び付けられる。根拠は出典 ID と任意の引用（verbatim）を持つ。
- FR-4.3 引用は 1〜500 文字。登録時に出典スナップショット内に実在するか確認し、実在しなければ 422 で拒否する。
- FR-4.4 主張の検証 API は判定と理由（details）を返し、`last_verdict` / `last_verified_at` を更新する。

### FR-5 検証（Verification）

- FR-5.1 判定は次の決定論的規則による。
  - 根拠が 0 件 → `insufficient`
  - 出典スナップショットの SHA-256 不一致（改竄）→ `contradicted`
  - 引用がスナップショットに実在しない → `contradicted`
  - 主張中の数値トークンが、結合した根拠本文のいずれにも実在しない → `unverified`
  - 引用が実在し、数値がすべて実在する → `verified`
  - 引用が無く、数値も無い → `insufficient`
- FR-5.2 判定結果には、根拠ごとの `quote_found` / `digest_ok` と、数値ごとの `found` を含める。
- FR-5.3 テーマ一括検証と、レポート検証（参照主張の一括検証 + 集計）を提供する。
- FR-5.4 レポート検証は `report_verifications` に履歴を残す。

### FR-6 レポート

- FR-6.1 レポートはテーマに属し、title と content（sections → paragraphs → claimIds）を持つ。
- FR-6.2 保存のたびに不変の版（report_versions）を作り、content の正規化 JSON に対する SHA-256 を保存する。
- FR-6.3 提出（submit）は editor 以上が実行でき、status を `in_review` にする。
- FR-6.4 reviewer 以上は承認 / 差し戻しできる。承認は `contradicted` が 0 件であることを必須とする（409）。差し戻しはコメント 10 文字以上を必須とする。
- FR-6.5 提出者本人は承認できない（403）。
- FR-6.6 承認済みレポートは Markdown でエクスポートできる。各段落に検証マーカー、末尾に根拠付録を付ける。

### FR-7 監査ログ

- FR-7.1 認証・テーマ・出典・主張・根拠・検証・レポート・承認の操作を `audit_events` に記録する。
- FR-7.2 記録は業務操作と同一トランザクションで行い、失敗時は操作も失敗させる。
- FR-7.3 更新・削除 API を提供しない。reviewer 以上が閲覧できる（project スコープは全件）。

### FR-8 管理

- FR-8.1 admin は利用者の一覧・作成・無効化ができる。
- FR-8.2 初期ユーザーは環境変数 `RIHRP_SEED_DEMO=true` のときのみ投入する（development / test）。

## 2. 非機能要件

| ID | 要件 |
|---|---|
| NFR-1 | ローカル PostgreSQL 16。接続情報は環境変数。 |
| NFR-2 | p95 応答 300ms 以内（ローカル、100 テーマ・1000 主張規模）。 |
| NFR-3 | すべての API は JSON。エラーは `{error:{code,message,details?}}` の統一形式。 |
| NFR-4 | ログにパスワード・セッショントークン・接続文字列を出さない。 |
| NFR-5 | `audit_events` は append-only。DB ロールでも UPDATE/DELETE を付与しない。 |
| NFR-6 | ビルドは Node 22 / Python 3.12。Docker を使わない。 |
| NFR-7 | 起動時に migration の最新版適用を検証し、未適用なら `/readyz` を 503 にする。 |
| NFR-8 | 主要画面はキーボード操作可能で、フォーカスリングを表示する。 |

## 3. 画面と状態

| 画面 | 主な状態 |
|---|---|
| ログイン | 入力中 / 送信中 / 認証失敗 / 成功 |
| ダッシュボード | loading / empty（テーマ 0 件）/ error / 正常 |
| テーマ詳細 | loading / empty（出典・主張・レポート 0 件）/ error / 正常 |
| 出典登録 | 入力中 / 検証エラー / 送信中 / 成功 |
| 主張一覧・検証 | 未検証 / 検証中 / verified / unverified / contradicted / insufficient |
| レポートエディタ | 未保存 / 保存済み / 検証中 / 矛盾あり / 提出済み |
| レビュー | 承認可能 / 矛盾ありで承認不可 / 差し戻しコメント不足 |
| 監査ログ | loading / empty / error / 正常 |

## 4. 権限マトリクス

| 操作 | viewer | editor | reviewer | admin |
|---|---|---|---|---|
| 閲覧 | ○ | ○ | ○ | ○ |
| テーマ作成・更新 | × | ○ | × | ○ |
| 出典・主張・根拠の編集 | × | ○ | × | ○ |
| 検証実行 | × | ○ | ○ | ○ |
| レポート編集・提出 | × | ○ | × | ○ |
| 承認・差し戻し | × | × | ○ | ○ |
| 監査ログ閲覧 | × | × | ○ | ○ |
| 利用者管理・テーマ削除 | × | × | × | ○ |

## 5. 受入テスト

1. ログイン → ダッシュボード → テーマ作成 → 出典登録（SHA-256 表示）→ 主張作成 → 根拠紐付け → 検証 → レポート作成 → 提出 → reviewer 承認 → エクスポート、が通る。
2. 出典本文を DB 上で改竄すると、再検証で `contradicted` になり、承認が 409 で拒否される。
3. 引用が実在しない根拠登録は 422。
4. 未検証の主張を含むレポートは承認できない（または矛盾として扱う）。
5. 監査ログに各操作が残り、API で書き換えられない。
6. CSRF ヘッダー無しの POST は 403。
7. viewer の書き込みは 403。提出者本人の承認は 403。
8. 画面の empty / loading / error 状態が実装されている。
