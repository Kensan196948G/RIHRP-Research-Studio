#!/usr/bin/env python3
"""RIHRP のバックアップを 1 つのスナップショットで取得し、manifest を添えて公開する。

- REPEATABLE READ のトランザクションで `pg_export_snapshot()` を発行し、
  `pg_dump --snapshot` と件数・migration の取得を**同一スナップショット**で行う。
- 完成するまで `.part` / `.tmp` のままにし、checksum → dump → manifest の順で公開する。
  manifest を最後に置くことで、「manifest がある = 完全な組」を保証する。
- 同時実行はロックファイルで直列化し、ファイル名にもマイクロ秒と PID を付ける。

使い方（rihrp-backup.sh から呼ぶ）:
  .venv/bin/python infra/native/backup_manifest.py --db rihrp_production \
      --out-dir ~/.local/state/rihrp/backups --pg-dump /usr/lib/postgresql/16/bin/pg_dump
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import psycopg

# 保持・復元の対象になるアプリケーションテーブル（sessions は揮発のため除外）。
TABLES = (
    "users",
    "projects",
    "sources",
    "claims",
    "claim_evidence",
    "reports",
    "report_versions",
    "report_verifications",
    "reviews",
    "research_documents",
    "audit_events",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_tmp(path: Path, text: str) -> Path:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.chmod(tmp, 0o600)
    return tmp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="backup_manifest.py")
    parser.add_argument("--db", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--pg-dump", default="pg_dump")
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(out_dir, 0o700)

    created: list[Path] = []
    lock_path = out_dir / ".rihrp-backup.lock"
    try:
        with lock_path.open("w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("BACKUP FAILED: 別のバックアップが実行中です", file=sys.stderr)
                return 3

            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
            final = out_dir / f"{args.db}-{stamp}-{os.getpid()}.dump"
            part = final.with_name(final.name + ".part")
            manifest_path = final.with_name(final.name + ".manifest.json")
            checksum_path = final.with_name(final.name + ".sha256")
            created.extend([part, manifest_path, checksum_path])

            with psycopg.connect(f"postgresql:///{args.db}", autocommit=False) as conn:
                with conn.cursor() as cur:
                    cur.execute("BEGIN ISOLATION LEVEL REPEATABLE READ")
                    cur.execute("SELECT pg_export_snapshot()")
                    snapshot = cur.fetchone()[0]

                    subprocess.run(  # noqa: S603
                        [
                            args.pg_dump,
                            "-Fc",
                            f"--snapshot={snapshot}",
                            "--dbname",
                            args.db,
                            "--file",
                            str(part),
                        ],
                        check=True,
                    )

                    counts_sql = (
                        "SELECT json_build_object("  # noqa: S608
                        + ", ".join(
                            f"'{table}', (SELECT count(*) FROM {table})"  # noqa: S608
                            for table in TABLES
                        )
                        + ")::text"
                    )
                    # テーブル名は上の固定タプルからのみ生成する（外部入力なし）。
                    cur.execute(counts_sql)  # noqa: S608
                    counts = json.loads(cur.fetchone()[0])
                    cur.execute("SELECT version_num FROM alembic_version")
                    migration = cur.fetchone()[0]
                conn.commit()

            sha256 = _sha256(part)
            manifest = {
                "db": args.db,
                "dump": final.name,
                "sha256": sha256,
                "migration": migration,
                "created_at": datetime.now(UTC).isoformat(),
                "counts": {table: int(counts[table]) for table in TABLES},
            }
            checksum_tmp = _write_tmp(checksum_path, f"{sha256}  {final.name}\n")
            manifest_tmp = _write_tmp(
                manifest_path,
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            )
            created.extend([checksum_tmp, manifest_tmp])

            # manifest を最後に公開する（存在 = 完全な組の目印）。
            os.replace(part, final)
            os.chmod(final, 0o600)
            os.replace(checksum_tmp, checksum_path)
            os.replace(manifest_tmp, manifest_path)
            print(f"backup: {final}")
            print(f"manifest: {manifest_path}")
            return 0
    except Exception as exc:  # noqa: BLE001 - CLI は失敗をそのまま返す
        print(f"BACKUP FAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        for leftover in created:
            if leftover.name.endswith((".part", ".tmp")):
                leftover.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
