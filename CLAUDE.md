# RIHRP Research Studio リポジトリ規則

- 全体方針は組織方針と `~/.claude/CLAUDE.md` に従う。本書は固有事項のみ。
- DB はローカル PostgreSQL（DB 名 `rihrp` / テストは `rihrp_test*`）。Neon・Docker は使わない（native systemd）。
- `audit_events` は append-only。業務操作と同一トランザクションで書き、失敗時は操作も失敗させる。
- 判定系は fail closed。検証（verification）は根拠スナップショットの SHA-256 を毎回再計算し、改竄・欠落は `contradicted` として扱う。推測で `verified` にしない。
- レポートの `approved` は「矛盾（contradicted）ゼロ」を必須とする。未検証（unverified / insufficient）は残数として表示し、承認画面から隠さない。
- 秘密情報（パスワード、セッション、接続文字列）をコード・文書・ログに書かない。`.env` はコミットしない。
- API を変えたら `docs/api/openapi.yaml` を再生成する。DB モデルを変えたら Alembic migration を追加する。
- テストは `rihrp_test*` の DB でのみ実行する（`tests/conftest.py` が強制する）。
- フロントは `apps/web`。ビルド成果物は API が同一オリジンで配信する。UI の正本は `docs/design/`（OpenDesign 由来の設計）とする。
- 実装していない機能を実装済みとして README に書かない。README の実装状況を機能変更時に更新する。
