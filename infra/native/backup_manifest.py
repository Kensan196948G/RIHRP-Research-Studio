#!/usr/bin/env python3
"""RIHRP のバックアップを 1 つのスナップショットで取得し、manifest を添えて公開する。

- REPEATABLE READ のトランザクションで `pg_export_snapshot()` を発行し、
  `pg_dump --snapshot` と件数・migration の取得を**同一スナップショット**で行う。
  これにより「dump には無いが manifest にはある」書き込みの混入を防ぐ。
- 完成するまで `.part` のままにし、manifest とチェックサムが揃ってから公開する。

使い方（rihrp-backup.sh から呼ぶ）:
  .venv/bin/python infra/native/backup_manifest.py --db rihrp_production \
      --out-dir ~/.local/state/rihrp/backups --pg-dump /usr/lib/postgresql/16/bin/pg_dump
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

TABLES = ("users", "projects", "sources", "claims", "reports", "audit_events")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_atomic(path: Path, text: str, mode: int = 0o600) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="backup_manifest.py")
    parser.add_argument("--db", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--pg-dump", default="pg_dump")
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(out_dir, 0o700)

    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    final = out_dir / f"{args.db}-{stamp}.dump"
    part = final.with_name(final.name + ".part")
    manifest_path = final.with_name(final.name + ".manifest.json")
    checksum_path = final.with_name(final.name + ".sha256")

    try:
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

                cur.execute(
                    "SELECT json_build_object("
                    + ", ".join(f"'{table}', (SELECT count(*) FROM {table})" for table in TABLES)
                    + ")::text"
                )
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
            "created_at": datetime.now(timezone.utc).isoformat(),
            "counts": {table: int(counts[table]) for table in TABLES},
        }

        # 完全な組（dump / sha256 / manifest）が揃ってから公開する。
        os.replace(part, final)
        os.chmod(final, 0o600)
        _write_atomic(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        _write_atomic(checksum_path, f"{sha256}  {final.name}\n")
        print(f"backup: {final}")
        print(f"manifest: {manifest_path}")
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI は失敗をそのまま返す
        print(f"BACKUP FAILED: {exc}", file=sys.stderr)
        for leftover in (part, part.with_name(part.name + ".tmp")):
            leftover.unlink(missing_ok=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
