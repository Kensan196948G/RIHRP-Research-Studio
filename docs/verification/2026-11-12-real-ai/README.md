# 2026-11-12 実AI検証の証跡

`docs/verification/2026-11-12-real-ai-verification.md` の生データと再実行スクリプト。

## 内容

| ファイル | 内容 |
|---|---|
| `brief_generate.md` | 生成ブリーフ（出典全文・型指定・抜粋） |
| `claims.json` | Part A の生成物（実モデル、24 件） |
| `results.json` | Part A の登録・検証結果 |
| `claims_free.json` | Part B の生成物（自然引用 6 / 逐語 6） |
| `free_results.json` | Part B とレポート承認ゲートの結果 |
| `tamper_results.json` | 改竄・引用消失の結果 |
| `rounding_results.json` | 丸め・順序数の結果 |
| `sources/` | 出典スナップショット（気象庁 / 総務省 / arXiv） |
| `*.py` | 再実行スクリプト |

## 再実行

前提: 隔離 DB（`rihrp_test*`）と、その DB を指す uvicorn。

```bash
createdb -O rihrp_app rihrp_test_ai_20261112
RIHRP_DATABASE_URL="postgresql+psycopg://rihrp_app:<pw>@127.0.0.1:5432/rihrp_test_ai_20261112" \
  .venv/bin/python -m alembic -c infra/migrations/alembic.ini upgrade head
RIHRP_ENV=development RIHRP_DATABASE_URL="..." RIHRP_SEED_DEMO=true \
  RIHRP_SEED_PASSWORD="$RIHRP_AI_TEST_PASSWORD" \
  .venv/bin/uvicorn rihrp.main:app --app-dir apps/api --host 127.0.0.1 --port 18120

export RIHRP_AI_TEST_PASSWORD='...'
python driver.py && python tamper.py && python rounding.py && python report_gate.py
```

- スクリプトはパスワードを環境変数 `RIHRP_AI_TEST_PASSWORD` から読む。
- 生成は実モデル（DSH サブエージェント）による。再実行時は生成物を固定するため `claims*.json` をそのまま使う。
- 本番 DB・本番配備には触れない。
