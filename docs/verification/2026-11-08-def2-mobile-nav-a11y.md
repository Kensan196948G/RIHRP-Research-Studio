# DEF-2（モバイル幅でナビリンクが無名）修正・検証記録（2026-11-08）

- 対象: RIHRP Research Studio（`main` = `98995ce` / PR #21、リリース候補 = `98995ce`）
- 位置づけ: **修正と検証の実行証拠**。リリース承認・本番切替ではない。
- 関連: [品質ゲート実行記録](2026-11-08-gate-execution.md) の DEF-2。修正前の証跡は
  `tmp/gate-20261108/mobile-a11y.json`（ローカル、git 管理外）。

## 1. 症状と再現

- 900px 以下（Pixel 5 393px / iPhone 13 390px）でログインし `/dashboard` を開くと、
  サイドバーの `a.nav-link` 4 件（`/dashboard`・`/settings`・`/audit`・`/users`）が
  アクセシビリティツリーで無名になる。
- 読み上げでは「リンク」とのみ通知され、行き先を識別できない。重大度 major・再現 必現。

## 2. 原因

- `apps/web/src/styles.css` の `@media (max-width: 900px)` が
  `.nav-link span.nav-label { display: none; }` としていた。
- アイコン SVG は `aria-hidden="true"` のため、リンクのアクセシブル名の供給源がなくなる。
- レイアウト自体はアイコンレールとして正常で、読み上げ名だけが欠落していた。

## 3. 修正

- ラベルを `display: none` ではなく visually hidden（1×1 クリップ）に変更した。
  アイコンレールの見た目・グリッド（68px + 本文）は変えない。
- 回帰テストを追加: `apps/web/e2e/a11y-mobile.spec.ts`
  - 390px / 393px でナビ 4 リンクの accessible name を検証
  - 900px 以下でラベルが 1×1 の visually hidden であること
  - 1280px でラベルが表示されること（デスクトップ回帰）
- 既存 E2E `apps/web/e2e/gate-extra.spec.ts` の CASE-2 断言は
  「ラベルが `display: none`」前提だったため、visually hidden + 読み上げ名維持の検証へ更新。

## 4. 検証結果

| 検証 | 結果 | 証跡 |
|---|---|---|
| `npx tsc -b` | pass | — |
| `npx vitest run` | 10 passed | — |
| `npm run build` | pass（`index-Bmdaog8l.css`） | — |
| Playwright 全 40 件 | **40 passed**（1.8m） | `tmp/gate-20261108/a11y-def2-junit.xml`（追加 3 件） |
| AX 実測（Pixel 5 / iPhone 13 / Desktop、`/dashboard`） | 390/393px で nav 4 リンクに名前、無名 interactive **0**、横スクロールなし | `tmp/gate-20261108/mobile-a11y-fixed.json` |
| リリース候補 `98995ce` の隔離起動 | `/healthz`・`/readyz` が release sha `98995ce…` / manifest `0213e48…` を返す | `tmp/gate-20261108/a11y-release-98995ce.json` |
| リリース候補の AX 実測 | 390 / 393 / 1280px で nav 4 リンクに名前、無名 interactive 0 | 同上 |

実測した AX スナップショット（390px、`/dashboard`）:

```
- navigation "メインナビゲーション":
  - link "ダッシュボード":
    - /url: /dashboard
  - link "設定":
    - /url: /settings
  - link "監査ログ":
    - /url: /audit
  - link "利用者":
    - /url: /users
```

修正前は同じ 4 リンクが `link`（無名）として出力されていた。

## 5. 影響範囲

- Web のレイアウト CSS（900px 以下のナビ表示）と E2E テストのみ。
- API・DB・migration・依存関係の変更はない。
- 900px 以下の見た目は従来どおりアイコンレール。デスクトップ表示も不変。

## 6. 残課題

- 実機 iOS Safari / Android Chrome + VoiceOver / TalkBack での確認は未実施（RISK-04）。
- 検証中に**別件**の a11y 課題を確認した（本修正の対象外・今回未修正）。
  - `/studio`（ログイン後の既定画面）の可視フォーム項目 9 件のうち **7 件**に
    programmatic label がない（`<label class="f">` と input/select/textarea の関連付けなし）。
    1280px でも同じで、モバイル固有ではない既存課題。
  - 例: 研究テーマ名 input、研究分野 select、研究仮説 textarea、背景・目的 textarea、
    前提条件・適用範囲 textarea、予算 select、期間 select。
  - 影響: スクリーンリーダーで項目名が読まれず、音声操作のラベル一致も効かない
    （WCAG 1.3.1 / 4.1.2 相当）。要件 NFR-8 はキーボード・フォーカスのみを規定しており、
    本件は既存の受容リスク RISK-04 の範囲で見つかった追加所見。
  - 証跡: `tmp/gate-20261108/studio-labels-98995ce.json`（9 項目中 7 項目が `labels: 0`・`aria: null`）。

## 7. 証跡一覧

| 証跡 | パス |
|---|---|
| 修正前の AX（390 / 393px） | `tmp/gate-20261108/mobile-a11y.json` |
| 修正後の AX（開発ビルド） | `tmp/gate-20261108/mobile-a11y-fixed.json` |
| 修正後の AX（リリース候補 `98995ce`） | `tmp/gate-20261108/a11y-release-98995ce.json` |
| Studio の label 欠落（既存・別件） | `tmp/gate-20261108/studio-labels-98995ce.json` |
| 追加 E2E の JUnit | `tmp/gate-20261108/a11y-def2-junit.xml` |
| PR / マージ | PR #21 → `98995ce`（squash、必須 Check 3 件 success） |
| リリースビルド | `~/.local/share/rihrp/releases/98995ce…/`（manifest `0213e48…`） |
| 修正ファイル | `apps/web/src/styles.css`、`apps/web/e2e/a11y-mobile.spec.ts`、`apps/web/e2e/gate-extra.spec.ts` |
