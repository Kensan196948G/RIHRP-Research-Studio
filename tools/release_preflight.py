#!/usr/bin/env python3
"""Read-only release preflight for RIHRP.

This checks a local git checkout and a backup artifact only. A successful result
is not deployment approval, proof that CI passed, or proof of the production
runtime commit SHA. This tool performs no database, network, or service
operation and never changes git configuration or fetches refs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final, TypedDict

TARGET_DB: Final = "rihrp_production"
EXPECTED_MIGRATION: Final = "0004_research_documents"
TABLES: Final = (
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
SHA_RE: Final = re.compile(r"[0-9a-f]{40}")
DIGEST_RE: Final = re.compile(r"[0-9a-f]{64}")
DUMP_RE: Final = re.compile(r"rihrp_production-[A-Za-z0-9][A-Za-z0-9._-]*\.dump")
SIDECAR_RE: Final = re.compile(r"([0-9a-f]{64}) [ *](.+)\n?")

type JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


class Check(TypedDict):
    name: str
    ok: bool
    detail: str


class Report(TypedDict):
    ok: bool
    checks: list[Check]


@dataclass(frozen=True, slots=True)
class PreflightConfig:
    expect_sha: str
    repo: Path
    backup_dir: Path
    max_age_hours: float = 36.0


@dataclass(frozen=True, slots=True)
class ManifestCandidate:
    path: Path
    data: dict[str, JsonValue]
    created_at: datetime


def _check(name: str, ok: bool, success: str, failure: str) -> Check:
    return {"name": name, "ok": ok, "detail": success if ok else failure}


def _git(repo: Path, args: tuple[str, ...]) -> subprocess.CompletedProcess[str] | None:
    # Never let caller Git routing/config variables select a different checkout.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    try:
        return subprocess.run(  # noqa: S603 - fixed git read-only subcommands, no shell
            ["git", "-C", str(repo), "--no-optional-locks", *args],  # noqa: S607
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _git_commit(repo: Path, revision: str) -> str | None:
    result = _git(repo, ("rev-parse", "--verify", revision))
    if result is None or result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value if SHA_RE.fullmatch(value) else None


def _git_checks(config: PreflightConfig) -> list[Check]:
    head = _git_commit(config.repo, "HEAD")
    origin_main = _git_commit(config.repo, "refs/remotes/origin/main")
    diff = _git(
        config.repo,
        ("diff", "--no-ext-diff", "--no-textconv", "--quiet", "HEAD", "--"),
    )
    untracked = _git(
        config.repo,
        ("ls-files", "--others", "--exclude-standard", "--full-name"),
    )
    clean = (
        diff is not None
        and diff.returncode == 0
        and untracked is not None
        and untracked.returncode == 0
        and not untracked.stdout
    )
    return [
        _check(
            "git_head",
            head == config.expect_sha,
            "HEAD matches the expected commit",
            "HEAD does not match the expected commit",
        ),
        _check(
            "origin_main",
            origin_main == config.expect_sha,
            "origin/main matches the expected commit",
            "origin/main does not match the expected commit",
        ),
        _check(
            "worktree_clean",
            clean,
            "tracked and untracked worktree paths are clean",
            "worktree has tracked or untracked changes",
        ),
    ]


def _is_regular(path: Path) -> bool:
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except OSError:
        return False


def _read_json_object(path: Path) -> dict[str, JsonValue] | None:
    try:
        if path.stat().st_size > 65_536:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(value, dict):
        return None
    return value


def _utc_timestamp(value: JsonValue | None) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return None
    return parsed.astimezone(UTC)


def _select_latest_manifest(
    backup_dir: Path,
) -> tuple[ManifestCandidate | None, str]:
    try:
        paths = sorted(backup_dir.glob("*.manifest.json"))
    except OSError:
        return None, "backup directory cannot be read"
    if not backup_dir.is_dir():
        return None, "backup directory does not exist"

    candidates: list[ManifestCandidate] = []
    for path in paths:
        if not _is_regular(path):
            return None, "a manifest is not a regular file or is a symlink"
        data = _read_json_object(path)
        if data is None:
            if path.name.startswith(f"{TARGET_DB}-"):
                return None, "a production manifest cannot be parsed"
            continue
        db = data.get("db")
        if db != TARGET_DB:
            if path.name.startswith(f"{TARGET_DB}-"):
                return None, "a production manifest has a mismatched database identity"
            continue
        created_at = _utc_timestamp(data.get("created_at"))
        if created_at is None:
            return None, "the latest production manifest has no aware UTC timestamp"
        candidates.append(ManifestCandidate(path, data, created_at))

    if not candidates:
        return None, f"no {TARGET_DB} manifest was found"
    return max(candidates, key=lambda candidate: candidate.created_at), "latest manifest selected"


def _freshness_check(
    candidate: ManifestCandidate,
    now: datetime,
    max_age_hours: float,
) -> Check:
    age = now - candidate.created_at
    fresh = age <= timedelta(hours=max_age_hours) and age >= -timedelta(minutes=5)
    return _check(
        "backup_freshness",
        fresh,
        "latest production backup is within the freshness window",
        "latest production backup is expired or too far in the future",
    )


def _safe_file(path: Path) -> bool:
    return _is_regular(path)


def _digest(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _sidecar_digest(path: Path, dump_name: str) -> str | None:
    try:
        if path.stat().st_size > 4096:
            return None
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    match = SIDECAR_RE.fullmatch(text)
    if match is None or match.group(2) != dump_name:
        return None
    return match.group(1)


def _backup_checks(
    config: PreflightConfig,
    now: datetime,
) -> list[Check]:
    candidate, detail = _select_latest_manifest(config.backup_dir)
    checks = [
        _check(
            "latest_manifest",
            candidate is not None,
            "latest production manifest selected",
            detail,
        )
    ]
    if candidate is None:
        return checks

    checks.append(_freshness_check(candidate, now, config.max_age_hours))
    dump_value = candidate.data.get("dump")
    dump_safe = (
        isinstance(dump_value, str)
        and DUMP_RE.fullmatch(dump_value) is not None
        and candidate.path.name == f"{dump_value}.manifest.json"
    )
    dump_path = config.backup_dir / dump_value if dump_safe else None
    dump_ok = dump_path is not None and _safe_file(dump_path)
    checks.append(
        _check(
            "dump_file",
            dump_ok,
            "production dump has a safe basename and is a regular file",
            "production dump name or file type is invalid",
        )
    )

    manifest_digest = candidate.data.get("sha256")
    digest_safe = (
        isinstance(manifest_digest, str) and DIGEST_RE.fullmatch(manifest_digest) is not None
    )
    checksum_ok = False
    if dump_ok and digest_safe:
        assert dump_path is not None
        sidecar_path = dump_path.with_name(f"{dump_path.name}.sha256")
        sidecar_digest = (
            _sidecar_digest(sidecar_path, dump_path.name) if _safe_file(sidecar_path) else None
        )
        actual_digest = _digest(dump_path)
        checksum_ok = (
            actual_digest is not None
            and actual_digest == manifest_digest
            and actual_digest == sidecar_digest
        )
    checks.append(
        _check(
            "sha256",
            checksum_ok,
            "recomputed SHA-256 matches the manifest and sidecar",
            "SHA-256, manifest, or sidecar verification failed",
        )
    )

    counts = candidate.data.get("counts")
    counts_ok = (
        isinstance(counts, dict)
        and set(counts) == set(TABLES)
        and all(
            not isinstance(counts[table], bool)
            and isinstance(counts[table], int)
            and 0 <= counts[table] <= 2**63 - 1
            for table in TABLES
        )
    )
    checks.append(
        _check(
            "table_counts",
            counts_ok,
            "all 11 table counts are non-negative integers",
            "table counts are incomplete, invalid, or contain booleans",
        )
    )
    migration_ok = candidate.data.get("migration") == EXPECTED_MIGRATION
    checks.append(
        _check(
            "migration",
            migration_ok,
            f"migration is {EXPECTED_MIGRATION}",
            f"migration is not {EXPECTED_MIGRATION}",
        )
    )
    return checks


def run_preflight(config: PreflightConfig, now: datetime) -> Report:
    """Return all preflight checks without mutating git or backup state."""
    checks = _git_checks(config)
    checks.extend(_backup_checks(config, now))
    return {"ok": all(check["ok"] for check in checks), "checks": checks}


def _expect_sha(value: str) -> str:
    if SHA_RE.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("expected SHA must be 40 lowercase hexadecimal characters")
    return value


def _positive_hours(value: str) -> float:
    try:
        hours = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("max age must be a positive number") from exc
    if not math.isfinite(hours) or not 0 < hours <= 8760:
        raise argparse.ArgumentTypeError("max age must be greater than 0 and at most 8760 hours")
    return hours


def _parser() -> argparse.ArgumentParser:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(prog="release_preflight.py")
    parser.add_argument("--expect-sha", required=True, type=_expect_sha)
    parser.add_argument("--repo", type=Path, default=repo_root)
    parser.add_argument("--backup-dir", required=True, type=Path)
    parser.add_argument("--max-age-hours", type=_positive_hours, default=36.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and print one JSON report."""
    args = _parser().parse_args(argv)
    report = run_preflight(
        PreflightConfig(
            expect_sha=args.expect_sha,
            repo=args.repo,
            backup_dir=args.backup_dir,
            max_age_hours=args.max_age_hours,
        ),
        datetime.now(UTC),
    )
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
