# CI への依存脆弱性監査ジョブ追加（提案・要人間適用）

AI は `.github/workflows/**` を変更できない（self-evolution ポリシーで DEPLOY 扱い）。
以下を人間が `.github/workflows/dependency-audit.yml` として追加し、PR でレビューしてください。

- 起動条件は `schedule`（毎週月曜 09:00 JST = 00:00 UTC）と `workflow_dispatch`
- 既存 CI の必須チェックには含めない（ブランチ保護は変更しない）
- Python は `pip-audit`、Node は `npm audit --omit=dev` と `npm audit`（開発依存含む）を実行
- 失敗時はジョブを赤くし、PR で気づけるようにする（Dependabot のアラートと併用）

```yaml
name: Dependency audit

on:
  schedule:
    - cron: "0 0 * * 1"
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: dependency-audit-${{ github.ref }}
  cancel-in-progress: true

jobs:
  python:
    name: pip-audit
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]" pip-audit
      - name: Audit runtime and dev dependencies
        run: pip-audit --strict

  node:
    name: npm audit
    runs-on: ubuntu-latest
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
      - name: Install
        run: npm ci --no-audit --no-fund
      - name: Audit production dependencies
        run: npm audit --omit=dev --audit-level=high
      - name: Audit all dependencies
        run: npm audit --audit-level=critical
```

## 人間が行う手順

1. `.github/workflows/dependency-audit.yml` を上記内容で追加（またはブランチへコミット）。
2. 追加後に GitHub Actions の「Dependency audit」を **手動実行（workflow_dispatch）** し、
   緑になることを確認する。`schedule` 起動はデフォルトブランチに workflow が存在してから
   有効になるため、適用（マージ）後に初回の定期実行が行われる。
3. 必要なら PR の required checks へ追加するか、失敗時の通知先（Issue 自動作成等）を決める。

## 補足

- 現在の代替手段: Dependabot アラート（open critical/high 0）と、ローカル/配備前の
  `npm audit`・`pip-audit` 手動実行。
- `pip-audit --strict` は開発依存も含めて監査する。CI 環境で取得できないパッケージがある場合は
  `--skip-editable` などの調整が必要になることがある。
