# 検証記録 — 2026-11-03 Offline Research Studio WebUI（PR #5・レビュー3巡）

環境: ローカル Linux、Python 3.12、Node 22、PostgreSQL 16（`rihrp_test*`）、systemd --user。
対象ブランチ: `feat/offline-studio-ui`（PR #5、base=`main`）。

## 1. サマリ

| 項目 | 結果 |
|---|---|
| レビュー1巡目 | fail（High 2 / Medium 2 / Low 3）→ head `8528d84` |
| レビュー2巡目 | fail（High 1 / Medium 3 / Low 4）→ head `674e58e` |
| 修正1 | `a7ad639`（2巡目の全 8 件を修正） |
| レビュー3巡目 | fail（High 1 / Medium 2 / Low 1）→ head `a7ad639` |
| 修正2 | `5a328d3`（3巡目の全 4 件を修正） |
| レビュー4巡目 | fail（High 1 / Medium 1）→ head `5a328d3` |
| 修正3 | `938a72e`（書き込みは abort せず完了・後始末する方針へ統一） |
| レビュー5巡目 | fail（High 1 / Medium 1 / Low 1）→ head `938a72e` |
| 修正4 | `bd32a8e`（取込保存の flush 追跡・所有者による削除・cleanup 条件） |
| レビュー6巡目 | fail（High 2）→ head `bd32a8e` |
| 修正5 | `6adffcf`（正本 HTML のエスケープ・複数件取込の flush 追跡） |
| レビュー7巡目 | fail（High 1）→ head `6adffcf` |
| 修正6 | `bc134c3`（正本 HTML の残存 sink を normalize + esc で解消） |
| レビュー8巡目 | fail（High 1 / Medium 1）→ head `bc134c3` |
| 修正7 | `0808c42`（正本の全フィールド正規化・配列型不正の耐性） |
| レビュー9巡目 | **pass**（High 0 / Medium 1 / Low 1）→ head `0808c42` |
| 修正8 | 本コミット（型不正データの起動保護・空候補 / vars 欠落） |
| 自動テスト | pytest **144 passed / 1 skipped**、vitest **10 passed**、Playwright **22 passed**（46.0s） |
| 静的検査 | `tsc -b` / `vite build` / `ruff check apps/api tests` / `ruff format --check apps/api tests` / `openapi --check` すべて pass |
| CI | run `41560328053`（head `a7ad639`）**success** |

## 2. レビュー2巡目の指摘と対応（`a7ad639`）

| # | 重要度 | 指摘 | 対応 |
|---|---|---|---|
| 1 | High | 比較・根拠画面の保存型 XSS（`viewCompare` / `rankHTML` の `candidate.label`、`evidence` / `critique` / `candidate` の id、plan measure role が未エスケープ） | 全動的文字列・属性を `esc()`、id を `safeId()` で `[A-Za-z0-9_-]` に正規化。E2E「保存済みデータ由来の XSS が成立しない」で compare / evidence 経路も拘束（`[data-injected]` 0 件・`img[src="x"]` 0 件・`window.__xss` 未定義） |
| 2 | Medium | AbortController が API 通信へ伝播せず、中止後もプロジェクト作成 | `request()` が `signal` を `fetch` へ伝播。list/get/create/save/rename/delete 全てに伝播。中止時の孤児プロジェクトを削除。unmount 時の flush は signal を切り離し（`detached`）、遷移で保存待ちを失わない |
| 3 | Medium | `destroy` が未追跡 `setTimeout` を残し unmount 後も処理が進行 | 生の `setTimeout` を `later()` に統一（残存は `later` 内と討論再生の interval のみ）。`destroy` で `clearInterval`（interval）/ `clearTimeout`（timeout）に整理し、`playDebate` / `touch` / `render` は `destroyed` で停止 |
| 4 | Medium | `ResearchDocIn` の 422 形状検証が部分的 | `field` / `constraints` / `analysis`（field・配列・真偽値・quality 0〜5）/ `tasks`（10 件・key 集合・重複なし）/ `progress`・`runs`・`relevance`・`reliability`・`candidates.scores`・`weights`（有限・範囲）/ `candidate.label`（50 文字・文字列）・`id` / `plan` role を検証。クライアント sanitize も field・plan role の列挙、candidate label の型、analysis の形状を保証。422 回帰テストを 20 ケースに拡張 |
| 5 | Low | テーマ切替 E2E がサーバー永続化を拘束していない | 切替後に `page.reload()` して値を再確認 |
| 6 | Low | `flush` が同一プロジェクトを重複保存 | プロジェクト ID の集合でジョブを一意化 |
| 7 | Low | 次のステップ欄の二重エスケープ | 内側の `esc()` を外し、出力時の 1 回に統一（`A&B` が `A&amp;B` にならない） |
| 8 | Low | 仕様書の内部リンク切れ | `../adr/0004-auth-session.md` / `../architecture/01-architecture.md` に修正 |

## 3. レビュー3巡目の指摘と対応（`5a328d3`）

| # | 重要度 | 指摘 | 対応 |
|---|---|---|---|
| 1 | High | `destroy` 時の abort 競合で直近の保存が失われる。送信中の PUT を abort するとサーバー側だけ version が進み、遷移時の detached 保存が古い `expected_version` で 409 → `aborted()` で握りつぶされ編集が消える | **書き込みは abort しない**（`saveDocument` / `renameProject` に signal を渡さない）。409 の detached 保存は最新 version を GET し直して同じスナップショットを再送（`getDocument` → `saveDocument`）。`saveChain` により後続保存は前の version 更新後に送信される |
| 2 | Medium | 新規作成・JSON 取込が destroy の signal を無視し、破棄後も作成が継続して孤児プロジェクトを作る | 新規研究・削除後の代替作成・JSON 取込・サンプル追加の `createProject` に signal を伝播。中止時は作成済みプロジェクトを削除。click ハンドラ全体を try/catch し AbortError を握りつぶさず `aborted()` で抑制 |
| 3 | Medium | 列挙値に配列等を送ると型検査前に集合所属判定で未処理 TypeError → **HTTP 500**。クライアントも境界値をクランプしない | `_enum_ok()`（`isinstance(str)` を先に判定）へ全列挙判定を置換（field/analysis.field/constraints/tasks.key・status/evidence.stance/critiques.sev・status/candidates.status/plan role）。クライアントは weights 0〜50・reliability/relevance/candidate scores/total 0〜100・method cost/time/val 1〜5・tasks runs 0〜100000・revision 0〜100000 に正規化。500→422 の回帰テストを追加 |
| 4 | Low | `flush` が未変更でも現在プロジェクトを保存し、ログアウト時に同一内容の PUT が2回（2回目は 401） | `dirty` マップで未保存変更を管理し、`flush` は dirty なプロジェクトだけ保存。ログアウト E2E で **PUT が1回だけ**であることを拘束 |

## 4. レビュー4巡目の指摘と対応（`938a72e`）

同じ根因（**書き込みの abort**）に対する2件。

| # | 重要度 | 指摘 | 対応 |
|---|---|---|---|
| 1 | High | JSON 取込の初回保存だけ `saveDocument(..., signal)` が残っており、遷移時に取込スナップショットが失われる（プロジェクトは作成済み・payload 空・削除もされない） | 取込の初回保存から signal を除去。書き込みは完了させ、破棄済みなら作成済みプロジェクトを削除する |
| 2 | Medium | `createProject` の応答保留中に遷移すると、abort で `created` の代入前に fetch が拒否され、後続の `deleteProject(created.id)` に到達せず孤児が残る | **作成も abort しない**（完了させてから `aborted()` なら削除）。load・新規研究・サンプル追加・削除後の代替作成・JSON 取込の全てに適用。削除も abort しない |

方針: 読み取り（`listProjects` / `getDocument`）だけ AbortSignal で中断する。書き込み（create / save / rename / delete）は中断せず完了させ、画面破棄後は ID が確定してから後始末する。abort で打ち切るとサーバーだけコミットされ ID 不明の孤児・未保存が残るため。

## 5. レビュー5巡目の指摘と対応（`bd32a8e`）

| # | 重要度 | 指摘 | 対応 |
|---|---|---|---|
| 1 | High | JSON 取込の初回保存が dirty / saveTimers / saveChain の追跡外で、ログアウト前 flush が完了を待たない。ログアウト後の PUT が 401 となり取込データが失われ、作成済みプロジェクトだけ残る | 取込の初回保存を `saveProject()`（dirty・saveChain・queued）経由に統一。`flush()` は保存待ちの tail を必ず await し、`queued` で同一プロジェクトの二重送信を抑止 |
| 2 | Medium | 作成は editor 以上、DELETE は admin 限定のため、editor の cleanup DELETE が 403 となり孤児が残る | `DELETE /api/projects/{id}` を `require_editor` + 所有者判定へ変更（admin は全件、editor は**自分が作成したプロジェクトのみ**）。他人のプロジェクトは従来どおり admin のみ。RBAC テスト（editor 自作品 200 / 他人品 403）を追加 |
| 3 | Low | `options.signal` なしで構成した場合、`destroy()` 後も cleanup 判定が `aborted()` だけを見るため削除されない | cleanup 条件を `aborted() \|\| destroyed` に統一（load・新規・サンプル・削除後の代替作成・取込） |

**権限変更の注意**: editor に「自分が作成したプロジェクトの削除」を許可した。他人のプロジェクトの削除は admin のみで、監査イベント `project.deleted` は従来どおり記録する。viewer は引き続き削除不可。

## 6. レビュー6巡目の指摘と対応（`6adffcf`）

| # | 重要度 | 指摘 | 対応 |
|---|---|---|---|
| 1 | High | **正本** `RIHRP_Offline_Research_Studio.html` の比較画面に保存型 XSS が残存（`candidate.label` 等を未エスケープで innerHTML へ補間。JSON 読込で実体の `img` が生成される） | 正本にも `apps/web` と同じエスケープを適用（`candidate.label`、`candidate` / `evidence` / `critique` の id、評論文言、plan measure role、報告書の仮説名）。実ブラウザで hostile な label / id / cat を注入し、`img[src=x]`・`[data-injected]`・`window.__p` がすべて 0/未定義であることを確認 |
| 2 | High | 複数件 JSON 取込中にログアウトすると、flush が呼出時点の `saveChain` しか待たず、後続の作成・保存が追跡されない。2 件目が version 0・payload 空で残り、cleanup DELETE も 401 | 取込全体を `trackOp()` で登録し、`flush()` が pending operation の完了まで待つよう変更。取込ループは各件を `saveProject()` 経由で保存するため、ログアウトは全件保存の完了後に実行される |

**正本の扱い**: 正本は UI/文言/CSS のオラクルだが、セキュリティ上の欠陥（HTML インジェクション）は正本側にも存在したため、表示結果が変わらない範囲で正本にも同じ `esc()` を適用した。仕様書 §5.1 の「逸脱」ではなく、正本と実装の双方に対する修正として扱う。

## 7. レビュー7巡目の指摘と対応（`bc134c3`）

| # | 重要度 | 指摘 | 対応 |
|---|---|---|---|
| 1 | High | 正本 HTML に保存型 XSS の sink が残存。報告書の `plan.measures[].role`、`tasks[].status`（class）・`runs`、`revisions[].rev`、candidate の `scores` / `total`、`evidence.relevance`、plan methods の `cost`、`critique.sev` / `status`、`ethics.level` など。`normalize()` が型・列挙を検証しないため任意文字列が innerHTML に通る | 正本に `sanitizeP()` を追加し、`render()` の先頭で列挙・数値・配列を強制正規化（field / revision / revisions.rev / tasks.status・progress・runs / evidence.stance・reliability・relevance / critiques.sev・status / candidates.status・scores・total / plan.methods.cost・time・val / plan.measures.role / ethics.level / debate.agent）。加えて報告書の `m.role`・評論文言・`i.level`・各種数値を `esc()`。**全6画面**に hostile 値を注入し、`img[src=x]` 0・`[data-injected]` 0・`window.__p` 未定義を実測。通常表示のスモーク（6画面が描画・pageerror 0）も確認 |

## 8. レビュー8巡目の指摘と対応（`0808c42`）

| # | 重要度 | 指摘 | 対応 |
|---|---|---|---|
| 1 | High | `sanitizeP()` が `p.id` / `analysis.quality` / `weights.*` / `debateShown` を正規化せず、innerHTML の sink（プロジェクト選択の option value、報告書の構造スコア・重み、討論タイムライン）に到達 | `sanitizeP()` を全フィールドへ拡張（文字列・列挙・有限数値・配列・オブジェクト形状を強制）。加えて当該 sink を `esc()` / 数値化。全6画面に hostile 値を注入して img 0・injected 0・`window.__z` 未定義を実測 |
| 2 | Medium | `sanitizeP()` が配列を強制しないため、`revisions: {}` 等の取込で描画が例外になり、localStorage 保存後に再読込しても nav/main が空のまま（永続的に起動不能） | すべての配列を `Array.isArray` で検証し、非配列は `[]` / `null` に正規化。空の plan は `null`。malformed project を localStorage に保存して再読込し、nav/main が描画され pageerror 0 であることを実測 |

## 9. レビュー9巡目（pass）と残指摘の対応（本コミット）

9巡目は **pass（critical 0 / high 0 / medium 1 / low 1）**。残った 2 件も実害があるため併せて修正した。

| # | 重要度 | 指摘 | 対応 |
|---|---|---|---|
| 1 | Medium | `load()` が `sanitizeP()` より先に全プロジェクトへ `normalize()` を実行するため、localStorage に `null` 要素や任意の task key が混在すると起動不能（nav/main 0） | `load()` でプロジェクト要素を object に限定し、`sanitizeP()` → `normalize()` の順に実行。`sanitizeP()` で task key 集合を検証し、不一致なら既定タスクへ戻す。プロジェクトが空にならないようフォールバック。null 要素 + 任意 key を保存して再読込し、nav/main 描画・pageerror 0 を実測 |
| 2 | Low | `candidates: []` が truthy のまま `viewCompare()` に入り `best` が undefined で例外。候補に `vars` が無い場合も `c.vars.map` で例外 | 空候補は `null` に正規化し、`viewCompare()` に空配列ガードを追加（正本・apps/web 両方）。候補の `label` / `type` / `origin` / `text` / `vars` を正規化。空候補・vars 欠落で比較画面が描画されることを実測 |

## 10. 実測コマンド

```bash
.venv/bin/python -m pytest -p no:warnings        # 144 passed, 1 skipped
cd apps/web && npx vitest run                    # 10 passed
cd apps/web && npm run build && npx playwright test  # 26 passed (51.3s)
.venv/bin/ruff check apps/api tests
.venv/bin/ruff format --check apps/api tests
.venv/bin/python infra/db/export_openapi.py --check
```

注意: `pytest` と Playwright を**同時に実行しない**。同じ `rihrp_test*` DB を奪い合い、無関係なテストが落ちる（実際に `test_admin_cannot_demote_self` が偽陽性で落ちた）。単独実行では pass。

## 11. 未検証・残課題

- CI に E2E ジョブは未追加（workflow 変更は要人間承認）。
- スクリーンリーダー / キーボード全画面 / 320px / 実機 / ネットワーク遮断時の保存失敗 UI は未検証。
- 書き込み中に画面遷移する競合（3巡目 High #1）の専用 E2E は未追加。孤児プロジェクト（4巡目 #2）とログアウト経路の「PUT 1 回」は E2E で拘束済み。
- レビュー10巡目（最終確認）の結果はマージ後に追記する。

## 12. マージ後の追加対応（本 PR）

PR #5 マージ後の最終レビューで残った low と、未検証 UI 項目の自動化。

| 項目 | 対応 | 実測 |
|---|---|---|
| レビュー10巡目の low | 正本と同じ「空配列は null に正規化」を apps/web の `sanitizeProject` に追加（`navStatus` は正本と同一の truthy 判定）。空配列は「候補 0件」ではなく「未生成」 | 回帰テスト追加（`candidates: []` を保存 → 再読込 → 比較ナビが「未生成」・非 active） |
| 320px | **初回実装はデータ依存で失敗**（長い研究テーマ名で `.topbar` が 53px はみ出した）。`max-width:700px` で brand の折返し・`minmax(0,1fr)`・select の最大幅を修正。**さらに報告書の 9 列表が 320px で 100px はみ出す**ことを正本の実ブラウザ実測で発見し、`table-layout:fixed`・`th` の折返し・`overflow-wrap:anywhere` を追加 | 長いタイトルに改名したうえで 320px の**全 6 ビュー**（登録/タスク/討論/根拠/比較/報告書）を実測し、文書の横スクロール 0。正本 HTML も同じ 320px ルールで全 6 ビュー横スクロール 0 |
| キーボード操作 | プログラム的 `focus()` ではなく **Tab で到達 → フォーカス可視（outline）→ Enter で遷移**を検証 | passed |
| ネットワーク遮断時の保存失敗 UI | オフラインで「保存に失敗しました」→ 復帰後に再保存で「サーバーに自動保存済み」を検証 | passed |

### 12.1 独立レビュー（PR #6・1巡目）の指摘と対応

PR #6 の独立レビューは **pass（critical 0 / high 0 / medium 2 / low 1）**。medium/low も実害があるため修正した（修正後の head で再レビューする）。

| # | 重要度 | 指摘 | 対応 |
|---|---|---|---|
| 1 | Medium | 320px 対応が `apps/web` にだけ入り、**正本 HTML** は折返し・`.cands` の 300px 最小トラックのままで、320px で横スクロールし得る。空配列の扱いも正本（`sanitizeP()` が null 化）と apps/web で異なる | 正本 `RIHRP_Offline_Research_Studio.html` に同じ `@media (max-width:700px)` を追加。apps/web にも正本と同じ空配列→null の正規化を入れ、`navStatus` は正本と同じ truthy 判定に統一（**CSS・正規化とも一致**） |
| 2 | Medium | 空候補テストが PUT の成否と対象プロジェクトを拘束せず、初期状態（`candidates: null`）でも旧実装で通る偽陽性になり得る。`not.toHaveClass(/active/)` はナビの選択状態を見ており、`navStatus` の `on`（`.st.on`）を拘束していない | 前提として候補 1 件を保存し `.st` が「候補 1件」になることを確認。対象は `#projSel` の選択中 ID に固定し、PUT の ok を検証。空配列後に `.st` が「未生成」かつ `on` クラスなしを検証 |
| 3 | Low | 追加 E2E が共有プロジェクトのタイトル・候補・仮説を変更したまま終了し、テスト間の状態分離がない | A-04b はタイトルを、空候補テストは候補を、オフライン試験は仮説を **finally で復元**。再実行・並べ替えに対して順序依存を解消 |

レビュー対応後の再検証で、**報告書ビューの 9 列表が 320px で 100px はみ出す**不具合を正本 HTML の実ブラウザ実測で追加発見した（候補ありの状態でのみ再現）。`@media (max-width:700px)` に `table-layout:fixed`・`th` の折返し・`overflow-wrap:anywhere` を追加して解消し、A-04b を**全 6 ビューの横スクロール検証**へ拡張した（報告書の表も拘束対象）。

### 12.2 独立レビュー（PR #6・2巡目）の指摘と対応

2巡目は **fail（critical 0 / high 1 / medium 2 / low 2）**。High は実測で再現し、修正した。

| # | 重要度 | 指摘 | 対応 |
|---|---|---|---|
| 1 | High | A-04b の「長いタイトル」検証が実質無効。`PATCH /api/projects/{id}` は一覧の title だけを更新し、描画に使う `payload.title` は変わらない。assert 文字列「河道湾曲部における護岸基礎」は旧 TITLE の接頭辞のため、改名が UI に届かなくても一致する。320px 計測は旧短タイトルで行われていた | 改名を **UI（title 入力）** から行い、payload.title とサーバー一覧を同時更新。再読込後に `#projSel option` の「長い研究テーマ名」と title 入力の longTitle 一致を検証。finally で元のタイトルへ復元 |
| 2 | Medium | 空配列を null 化する根本原因が未修正。`stances()` は `[]` で「代替案あり」、`makeH0` は `[]` を truthy と見て主仮説を生成せず、ナビの「未生成」と矛盾する（正本 1084 行との乖離） | `sanitizeProject` に正本と同じ `if(Array.isArray(p.candidates)&&!p.candidates.length)p.candidates=null;` を追加。`navStatus` は正本と同一の truthy 判定へ戻し、全経路を整合 |
| 3 | Medium | 空候補 E2E が seed の PUT 応答を検証せず、PUT が失敗しても「未生成」で green になり得る（回帰テストの空振り） | `expect(seeded.ok()).toBeTruthy()` を追加（対象は `#projSel` の選択中 ID に固定済み） |
| 4 | Low | 横スクロール判定が `window.innerWidth` 基準で、縦スクロールバー幅（約15px）ぶん鈍感 | `document.documentElement.clientWidth` 基準へ変更 |
| 5 | Low | 新規 E2E が共有 DB の状態を復元せず、テスト順序に依存する | A-04b はタイトル、空候補テストは candidates、オフライン試験は仮説を finally で復元 |

あわせて README の実測値を現行へ更新した（pytest 115→144、E2E 21→26）。

**E2E 合計 26 passed**（pytest 144 passed / 1 skipped、vitest 10 passed、build pass）。

残る未検証（自動化不可・人手）:
- Cloudflare Access 認証後の実ブラウザ操作（OTP/SSO）。
- スクリーンリーダーによる読み上げ（ARIA 名の自動検査は未導入）、実機。
- CI への E2E ジョブ追加（workflow 変更は AI 不可。提案は `docs/ci/e2e-workflow.md`、PR #7）。
