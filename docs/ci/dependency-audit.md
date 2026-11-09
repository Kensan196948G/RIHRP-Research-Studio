# CI への依存脆弱性監査ジョブ（適用済み・実 CI 検証済み）

> **状態: 適用済み（2026-11-07）。**
> PR #16 で `.github/workflows/dependency-audit.yml` として追加し、main（`f868ec7`）にマージした。
> 実 CI で緑を確認済み（PR の `pull_request` run `42373686405`、main の `workflow_dispatch`
> run `42374269050`）。実行条件・結果は §4、詳細は
> [検証記録](../verification/2026-11-07-dependency-audit.md) 第 10 章を参照。

## 0. なぜ AI ではなく人間が適用したか（実測）

AI エージェントは `.github/workflows/**` へ**書き込めない**。2026-11-07 に実測した。

- `write` ツールは次のエラーで拒否された:
  `self-evolution policy gate: DEPLOY is critical risk (critical operations are denied)`
- これはサンドボックスのパス制限ではなく**パス単位のポリシー拒否**である
  （同一内容を `/tmp` へは書けたため、内容起因ではないと切り分け済み）。
- 同セッションは**承認プロンプトが無効**（承認要求は自動的に拒否される）ため、
  AI 側から承認を要求することもできない。
- 拒否された操作を別ルート（シェルリダイレクト等）で再試行することは方針上禁止であり、
  迂回はしていない。

したがって「検証済み YAML をドキュメントに置き、人間が適用する」という形を採った。
2026-11-07 に依頼者（人間）が PR #16 として適用し、main にマージされた。
この挙動はワークフロー冒頭のコメント `Apply only after human approval` と整合している。

## 1. 検証済み最終 YAML 全文

`actionlint 1.7.12`（shellcheck 0.9.0 併用）で **exit 0・警告 0**、`yaml.safe_load` で
構文解析成功を確認済み（63 行）。この内容が 2026-11-07 に
`.github/workflows/dependency-audit.yml` として適用された（PR #16 / commit `eb74d5b`）。

```yaml
# Dependency audit — weekly + PR gate. Apply only after human approval: .github/workflows/**
# is risk-class DEPLOY (critical). Both jobs are NEW, non-required; branch protection untouched.
name: Dependency audit

on:
  schedule:
    - cron: "0 0 * * 1" # Mondays 00:00 UTC = 09:00 JST
  workflow_dispatch:
  pull_request:
    branches: [main]
    paths: [requirements-production.txt, pyproject.toml, uv.lock, "apps/web/package*.json", .github/workflows/dependency-audit.yml]

permissions:
  contents: read

concurrency:
  group: dependency-audit-${{ github.ref }}
  cancel-in-progress: true

jobs:
  python-audit:
    name: Dependency audit (Python)
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: |
            pyproject.toml
            requirements-production.txt
      # Never `pip install -e .`: an editable dist breaks `pip-audit --strict` ("not found on PyPI").
      - name: Install auditors
        run: python -m pip install --disable-pip-version-check "pip-audit>=2.10,<3" "uv>=0.12"
      - name: Audit production pins (34 pkgs, hashed)
        run: pip-audit -r requirements-production.txt --strict --progress-spinner off
      - name: Export runtime + dev extras from uv.lock
        run: uv export --locked --all-extras --no-emit-project --format requirements.txt -o "$RUNNER_TEMP/dev-extras.txt"
      - name: Audit runtime + dev extras
        run: pip-audit -r "$RUNNER_TEMP/dev-extras.txt" --strict --progress-spinner off

  node-audit:
    name: Dependency audit (Node)
    runs-on: ubuntu-latest
    timeout-minutes: 10
    defaults:
      run:
        working-directory: apps/web
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: apps/web/package-lock.json
      - name: Install from lockfile
        run: npm ci --no-audit --no-fund
      - name: Audit production deps (fail on high+)
        run: npm audit --omit=dev --audit-level=high
      - name: Audit all deps (fail on critical)
        run: npm audit --audit-level=critical
```

## 2. なぜこの形か

### 2.1 環境ベース監査（`pip install -e .` + `pip-audit --strict`）は必ず失敗する

旧ドラフトは `pip install -e ".[dev]"` した環境に対して `pip-audit --strict` を実行していた。
これは**構造的に必ず赤になる**。理由は、editable インストールされた自パッケージ `rihrp` が
PyPI に存在せず、`--strict` が「監査できなかった依存」をエラーとして扱うためである。

実測 3 種（いずれも隔離 venv、2026-11-07）:

| コマンド | exit | メッセージ |
|---|---|---|
| `pip-audit --strict` | **1** | `rihrp: Dependency not found on PyPI and could not be audited: rihrp (0.1.0)` |
| `pip-audit --strict --skip-editable` | **1** | `rihrp: distribution marked as editable` |
| `pip-audit`（`--strict` なし） | 0 | `No known vulnerabilities found` だが Skip Reason 表に `rihrp` が並ぶ |

`--skip-editable` を足しても「editable であること自体」がエラーになるため回避できない。
`--strict` を外せば緑になるが、それは **監査できていない依存を黙って見逃す**ことになり、
ゲートとしての意味を失う。

→ 対策: 環境を監査する方式をやめ、**要件ファイル（`-r`）方式**にして自パッケージを
監査対象から外す。`--strict` は維持したまま緑にできる。

### 2.2 `--no-emit-project` が緑の要

`uv export` は既定でプロジェクト自身を `-e .` として出力に含める。実測では出力 3 行目に
`-e .` が現れた。このファイルを `pip-audit -r ... --strict` に渡すと:

```
ERROR: The editable requirement file://<repo>
       (from -r dev-extras-with-project.txt (line 3)) cannot be installed when requiring hashes,
       because there is no single file to hash.
EXIT=1
```

`--no-emit-project` を付けると `-e .` が出力されず、46 パッケージのみの要件ファイルになり
`pip-audit -r --strict` が exit 0 で通る。**このフラグが緑になるための必須条件**である。

### 2.3 `--locked` で lock 同期漏れを検出する

`uv export --frozen` は「`uv.lock` を更新しない」だけで、lockfile が `pyproject.toml` と
同期していることを検証しない。`uv export --help` の定義:

- `--frozen`: `Do not update the uv.lock before exporting`
- `--locked`: `Assert that the uv.lock will remain unchanged`

paths トリガに `pyproject.toml` を含めているため、**`pyproject.toml` だけ変更して
`uv.lock` を再生成し忘れた PR では、古い lock を監査して緑になる**恐れがあった。
`--locked` に変えることでその同期漏れを失敗として検出できる。

### 2.4 2 段の監査しきい値

- 本番依存（`--omit=dev`）: **high 以上**で失敗 — 利用者に直接影響する範囲を厳しく見る
- 全依存（開発依存含む）: **critical のみ**失敗 — 開発ツールチェーンの割れは騒ぎすぎない

### 2.5 既存 CI と非干渉

- 追加するのは**新規ファイル 1 つ**で、既存ワークフロー（`ci.yml` / `e2e.yml`）は変更しない。
- 両ジョブとも **required checks に追加しない**。ブランチ保護設定は一切触らない。
- `permissions: contents: read` のみ。書き込み権限を要求しない。
- `concurrency` で同一 ref の重複実行を打ち消す。
- `timeout-minutes: 10` でハングを打ち切る。

### 2.6 fail closed

`continue-on-error` は使用していない。監査が失敗すればジョブは赤くなる。
脆弱性検知を「警告のみ」で素通りさせない設計である。

## 3. 実測結果（2026-11-07 / Asia/Tokyo）

環境: Python 3.12.3 / pip-audit 2.10.0（リポジトリ PATH）・2.10.1（隔離 venv に
CI 同条件 `>=2.10,<3` で導入）/ uv 0.12.5 / Node v22.22.3 / npm 10.9.8 /
actionlint 1.7.12 / shellcheck 0.9.0

| # | コマンド | exit | 結果 |
|---|---|---|---|
| 1 | `pip-audit -r requirements-production.txt --strict --progress-spinner off` | **0** | `No known vulnerabilities found` / 34 パッケージ / 33.3s |
| 2 | `uv export --locked --all-extras --no-emit-project --format requirements.txt -o <tmp>` | **0** | 46 パッケージ・1099 行（hash 付き）/ 0.05s |
| 3 | `pip-audit -r <上記 export> --strict --progress-spinner off` | **0** | `No known vulnerabilities found` / 46 パッケージ / 28.2s |
| 4 | `npm audit --omit=dev --audit-level=high`（`apps/web`） | **0** | `found 0 vulnerabilities` |
| 5 | `npm audit --audit-level=critical`（`apps/web`） | **0** | `found 0 vulnerabilities` |
| 6 | `actionlint dependency-audit.yml`（最終 63 行） | **0** | `Found total 0 errors`（18ms、shellcheck 実走） |
| 7 | `yaml.safe_load`（最終 63 行） | **0** | name / on / jobs / permissions / concurrency すべて設計どおり |

補足:

- 手順 1 の `requirements-production.txt` は 34 パッケージ・`--hash` 825 個。手順 2 の
  `--all-extras` により開発依存（`dev` extra）が加わり 46 パッケージになる。
- 手順 2 の出力は `--frozen` 版と依存集合が一致する（差分は uv が自動生成する
  ヘッダコメント 1 行のみ）。`--locked` は `uv.lock` を変更しないことも確認済み。
- 検証 1〜5 は**リポジトリの `.venv` を変更せずに**実行した。手順 4・5 は `npm ci` を
  実行しておらず、`node_modules` を作り直していない（`npm audit` は lockfile ベースで動作）。
- 詳細な生ログ・コマンド列は [検証記録](../verification/2026-11-07-dependency-audit.md) を参照。

## 4. 適用と実 CI 検証（2026-11-07 実施済み）

1. **ファイル追加（人間）**: 依頼者が `tmp/dependency-audit.yml`（本ドキュメント §1 と同一バイト列）を
   `.github/workflows/dependency-audit.yml` にコピーし、ブランチ `ci/apply-dependency-audit-20261107`
   として commit `eb74d5b` を作成、PR #16 を開いた。
2. **PR 検証**: チェック 5 件（必須 3 + 新規 2）がすべて green。新規ワークフローは
   `pull_request` の paths 条件に合致し、**PR 上で初回実行**された（run `42373686405`）。
3. **マージ**: squash マージで main へ（`f868ec7`、2026-11-07 12:50 UTC）。
   main CI run `42374211728` は 3/3 success。
4. **初回手動実行**: `gh workflow run dependency-audit.yml --ref main` → run `42374269050` success
   （`workflow_dispatch` / head `f868ec7`）。
5. **週次 schedule の初回発火**: 2026-11-09 09:27:51 JST に run `42540311340` が success
   （cron 予定 09:00 から約 28 分の遅延。§4.1 / 検証記録 §11）。
6. **未実施（任意・別途）**: required checks への追加、失敗時の通知先
   （Issue 自動作成・Webhook 等）、`schedule` の時刻変更。

### 4.1 実 CI の実行結果

| 実行 | トリガー | run | Python ジョブ | Node ジョブ |
|---|---|---|---|---|
| 適用 PR #16（head `eb74d5b`） | `pull_request` | `42373686405` | 35s / success | 11s / success |
| main 初回（head `f868ec7`） | `workflow_dispatch` | `42374269050` | 26s / success | 14s / success |
| 週次 schedule 初回（head `b4b6688`） | `schedule` | `42540311340` | 31s / success | 15s / success |

実 CI のログで確認した出力:

- Python 本番固定: `No known vulnerabilities found`（34 パッケージ）
- Python runtime + dev extras: `No known vulnerabilities found`
  （`uv export --locked --all-extras --no-emit-project` が CI 上でも exit 0）
- Node 本番: `found 0 vulnerabilities` / Node 全依存: `found 0 vulnerabilities`
- 監査ステップはいずれもスキップされず実行され、全 step が success

## 5. 旧ドラフトとの差分

本リポジトリには以前の提案 YAML が本ドキュメントに記載されていた。**旧版をそのまま適用すると
Python ジョブが必ず赤になる**（§2.1 の実測どおり）。主な差分:

| 項目 | 旧ドラフト | 検証済み最終版 |
|---|---|---|
| Python の監査方式 | `pip install -e ".[dev]"` して `pip-audit --strict` | `-r` 要件ファイル方式（`--no-emit-project` で自パッケージを除外） |
| Python ジョブの結果 | **exit 1**（`Dependency not found on PyPI`）。`--skip-editable` 併用も exit 1 | **exit 0** |
| 監査対象 | 本番 + dev を 1 回で | 本番固定（hash 付き）と runtime+dev extras の 2 回に分離 |
| lock 同期 | 対象外 | `--locked` で同期漏れを検出 |
| `pull_request` トリガ | なし（`schedule` + `workflow_dispatch` のみ） | paths 限定で追加 |
| pip キャッシュ | 未指定 | `cache-dependency-path` に `pyproject.toml` と `requirements-production.txt` を明示 |
| `timeout-minutes` | なし | 両ジョブ 10 分 |

旧ドラフトのままだと「追加した初日から赤いジョブ」が常設され、監査の信号が
ノイズで埋もれる。§2 の設計変更はこの失敗を避けるためのもの。

## 6. 制約・リスク・ロールバック

**変更範囲**: 新規ファイル 1 つ（`.github/workflows/dependency-audit.yml`）のみ。
既存ファイルの変更なし。既存の required checks・ブランチ保護に影響しない。

**ロールバック**: 追加したコミットを revert するか、当該ファイルを削除するだけで元に戻る。
既存ジョブへの依存が無いため、削除による副作用はない。

**既知のリスク**:

- **fork PR からの実行**: `pull_request` は fork からの PR でも実行され得る。本 YAML は
  `permissions: contents: read` のみ・`secrets` 不使用・`pull_request_target` 不使用のため、
  読み取り専用トークンの範囲で完結する。既存 `ci.yml` も全 PR で `npm ci` を実行しており、
  新たな露出の増分はほぼ無い。初回貢献者の承認要否はリポジトリ設定に依存する。
- **外部レジストリ障害時の偽陽性**: PyPI / npm レジストリの一時障害やレート制限で
  ジョブが赤くなり得る。その場合は原因を確認したうえで **re-run** する。恒常的に
  不安定なら step の retry 追加を別途検討する。
- **新規アドバイザリによる突発的な赤**: 週次の定期実行が新しい脆弱性を検知して赤くなるのは
  意図した動作である。依存更新は別 PR で行う（本提案は自動更新を含まない）。
- **`cache: pip` のキャッシュキー**: `cache-dependency-path` で
  `requirements-production.txt` を明示しているが、setup-python のキャッシュ機構の
  詳細な挙動は**実 CI での初回実行時に未確認**である。動作はキャッシュの効率に影響する
  だけで、監査結果の正しさには影響しない。
- **`uv` / `pip-audit` のバージョン範囲**: `pip-audit>=2.10,<3`・`uv>=0.12` という範囲指定の
  ため、将来のマイナー更新で挙動が変わる可能性はゼロではない。完全な再現性が必要なら
  バージョン固定を別途検討する。

## 7. 残課題

- **`.github/dependabot.yml` は不在**（2026-11-07 時点で未作成）。Dependabot アラート
  （リポジトリ設定側の機能）は有効だが、依存更新 PR の自動化・グループ化を併用するには
  設定ファイルの追加が別途必要。本提案には含まない。
- **GitHub Actions のメジャーバージョン**: 2026-11-07 に GitHub API
  （`repos/<owner>/<repo>/releases/latest`）で確認した最新は `actions/checkout` **v7.0.1**・
  `actions/setup-python` **v7.1.0**・`actions/setup-node` **v7.1.0** で、いずれも v7 系。
  本ワークフローは既存 CI と同じ `checkout@v4`・`setup-python@v5`・`setup-node@v4` に揃えた
  （2026-11-03 に同バージョンで CI が緑だった実績がある）。ただし実 CI では
  `Node.js 20 is deprecated ... forced to run on Node.js 24` の警告が出ており
  （対象はジョブにより `actions/checkout@v4` / `actions/setup-python@v5` / `actions/setup-node@v4`。
  2026-11-07 / run `42373686405`）、v7 への横断更新は既存 3 ワークフロー
  （`ci.yml` / `e2e.yml` / 本ファイル）に影響するため別 PR で行う。
- **paths 限定による取りこぼし**: `pull_request` トリガは依存ファイル変更時にしか走らない
  ため、依存を変更しない PR では監査されない。**週次の `schedule` 実行がこれを補完する**
  設計だが、依存変更 PR の検出遅れは残る。
- **実 CI の実行は完了**: PR #16（run `42373686405`）、main の `workflow_dispatch`
  （run `42374269050`）、週次 `schedule` の初回（run `42540311340` / 2026-11-09）で
  両ジョブの緑を確認した（§4.1）。継続監視の対象は、`ubuntu-latest` の
  Ubuntu 26 移行（2026-10-19 以降）と `actions/*@v4/v5` の非推奨警告である。
  schedule は実測で予定時刻から約 28 分遅れて発火した（GitHub の遅延仕様）。
- **通知先は未設定**: 失敗時に誰がどう気づくかは未定。必要なら Issue 自動起票や
  Slack/Webhook 通知を別途追加する。
