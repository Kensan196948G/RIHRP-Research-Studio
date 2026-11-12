#!/usr/bin/env python3.12
"""Activate or roll back an immutable RIHRP release.

The command is intentionally limited to the current ``0004`` schema. It
performs read-only database metadata inspection, never migrates or downgrades
the database, and never fetches or rewrites Git configuration.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import json
import os
import pwd
import re
import secrets
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final, Protocol

TARGET_DB: Final = "rihrp_production"
EXPECTED_MIGRATION: Final = "0005_reports_ai_assisted"
# 切替前の current/previous は旧 migration のまま存在する。topology 検証では既知の
# migration を許容し、切替対象（activate）だけ EXPECTED_MIGRATION を要求する。
KNOWN_MIGRATIONS: Final = frozenset({EXPECTED_MIGRATION, "0004_research_documents"})
SERVICE_NAME: Final = "rihrp.service"
SERVICE_PORT: Final = 18110
SHA_RE: Final = re.compile(r"[0-9a-f]{40}")
DIGEST_RE: Final = re.compile(r"[0-9a-f]{64}")
DUMP_RE: Final = re.compile(r"rihrp_production-[A-Za-z0-9][A-Za-z0-9._-]*\.dump")
SIDECAR_RE: Final = re.compile(r"([0-9a-f]{64}) [ *](.+)\n?")
MAX_BACKUP_AGE: Final = timedelta(hours=24)
FUTURE_SKEW: Final = timedelta(minutes=5)
HEALTH_TIMEOUT_SECONDS: Final = 30.0
MANIFEST_LIMIT: Final = 8 * 1024 * 1024
EVIDENCE_LIMIT: Final = 64 * 1024
UNIT_LIMIT: Final = 1024 * 1024
INVENTORY_DIRECTORIES: Final = ("apps/api", "infra/migrations")
INVENTORY_DIRECTORY_ALL: Final = "apps/web/dist"
INVENTORY_FILES: Final = (
    "uv.lock",
    "requirements-production.txt",
    "pyproject.toml",
    "apps/web/package-lock.json",
    "apps/web/package.json",
)

type JsonObject = dict[str, object]


class ActivationError(RuntimeError):
    """A release action failed without exposing command output or secrets."""


@dataclass(frozen=True, slots=True)
class ActivationConfig:
    action: str
    expect_sha: str
    release_root: Path
    repo: Path
    env_file: Path
    backup_dir: Path
    backup_manifest: Path
    restore_evidence: Path
    unit_path: Path


@dataclass(frozen=True, slots=True)
class Release:
    sha: str
    path: Path
    manifest: JsonObject


@dataclass(frozen=True, slots=True)
class TransitionState:
    action: str
    target_sha: str
    previous_current: str | None
    previous_previous: str | None
    unit_path: Path
    old_unit: bytes
    old_unit_mode: int
    created_at: datetime

    @property
    def old_unit_sha256(self) -> str:
        return hashlib.sha256(self.old_unit).hexdigest()


class Operations(Protocol):
    """External effects, injectable in tests without production bypass flags."""

    def git_matches(self, repo: Path, sha: str) -> bool: ...

    def ci_success(self, repo: Path, sha: str) -> bool: ...

    def preflight_ready(self, repo: Path, sha: str, backup_dir: Path) -> bool: ...

    def schema_ready(self, release: Release, env_file: Path) -> bool: ...

    def systemctl(self, action: str) -> bool: ...

    def health_ready(self, expected_sha: str | None) -> bool: ...

    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


def _preflight_module():
    try:
        return importlib.import_module("tools.release_preflight")
    except ModuleNotFoundError:
        return importlib.import_module("release_preflight")


def _clean_git_environment() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return env


def _git(repo: Path, args: tuple[str, ...]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(  # noqa: S603 - fixed read-only git subcommands, no shell
            ["git", "-C", str(repo), "--no-optional-locks", *args],  # noqa: S607
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            env=_clean_git_environment(),
            stdin=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _git_commit(repo: Path, revision: str) -> str | None:
    result = _git(repo, ("rev-parse", "--verify", revision))
    if result is None or result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value if SHA_RE.fullmatch(value) is not None else None


def _git_ready(repo: Path, sha: str) -> bool:
    head = _git_commit(repo, "HEAD")
    origin_main = _git_commit(repo, "refs/remotes/origin/main")
    tracked = _git(
        repo,
        ("diff", "--no-ext-diff", "--no-textconv", "--quiet", "HEAD", "--"),
    )
    untracked = _git(
        repo,
        ("ls-files", "--others", "--exclude-standard", "--full-name"),
    )
    return (
        head == sha
        and origin_main == sha
        and tracked is not None
        and tracked.returncode == 0
        and untracked is not None
        and untracked.returncode == 0
        and not untracked.stdout
    )


def _ci_success(repo: Path, sha: str) -> bool:
    env = _clean_git_environment()
    env.pop("GH_REPO", None)
    env.pop("GH_HOST", None)
    try:
        result = subprocess.run(  # noqa: S603 - fixed gh invocation, no shell
            [  # noqa: S607
                "gh",
                "run",
                "list",
                "--repo",
                "Kensan196948G/RIHRP-Research-Studio",
                "--branch",
                "main",
                "--event",
                "push",
                "--workflow",
                "ci.yml",
                "--commit",
                sha,
                "--limit",
                "50",
                "--json",
                "headSha,status,conclusion,workflowName",
            ],
            cwd=repo,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            env=env,
            stdin=subprocess.DEVNULL,
            timeout=30,
        )
        if result.returncode != 0:
            return False
        runs = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
    if not isinstance(runs, list):
        return False
    ci_runs = [run for run in runs if isinstance(run, dict) and run.get("workflowName") == "CI"]
    return bool(ci_runs) and all(
        run.get("headSha") == sha
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
        for run in ci_runs
    )


_SCHEMA_INSPECTION = r"""
import os
import sys
from urllib.parse import unquote, urlsplit


def truthy(value):
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}


def falsy(value):
    return value is not None and value.strip().lower() in {"0", "false", "no", "off"}


def inspect_database():
    if os.environ.get("RIHRP_ENV") != "production":
        return False
    if not truthy(os.environ.get("RIHRP_COOKIE_SECURE")):
        return False
    if not falsy(os.environ.get("RIHRP_SEED_DEMO")):
        return False

    database_url = os.environ.get("RIHRP_DATABASE_URL", "")
    if not database_url.startswith("postgresql+psycopg://"):
        return False
    parsed = urlsplit(database_url)
    if unquote(parsed.path.removeprefix("/")) != "rihrp_production":
        return False

    import psycopg

    conninfo = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(
        conninfo,
        autocommit=True,
        options="-c statement_timeout=5000",
    ) as connection:
        connection.read_only = True
        with connection.transaction():
            rows = connection.execute(
                "SELECT current_setting('transaction_read_only'), version_num "
                "FROM alembic_version"
            ).fetchall()
    return (
        len(rows) == 1
        and str(rows[0][0]).lower() == "on"
        and rows[0][1] == "0005_reports_ai_assisted"
    )


try:
    ok = inspect_database()
except BaseException:
    ok = False
if not ok:
    raise SystemExit(1)
print("ok")
"""


def _schema_ready(release: Release, env_file: Path) -> bool:
    _validate_env_file(env_file)
    python = release.path / ".venv/bin/python"
    script = 'set -euo pipefail\numask 077\nset -a\nsource "$1"\nset +a\nexec "$2" -I -B -c "$3"\n'
    home = Path(pwd.getpwuid(os.geteuid()).pw_dir)
    env = {
        "HOME": str(home),
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
    }
    try:
        result = subprocess.run(  # noqa: S603 - fixed bash and absolute release Python
            [
                "/bin/bash",
                "--noprofile",
                "--norc",
                "-c",
                script,
                "rihrp-release-env",
                str(env_file),
                str(python),
                _SCHEMA_INSPECTION,
            ],
            capture_output=True,
            check=False,
            env=env,
            stdin=subprocess.DEVNULL,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == b"ok"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _read_small_json_response(url: str) -> JsonObject:
    opener = urllib.request.build_opener(_NoRedirect())
    if url not in {
        f"http://127.0.0.1:{SERVICE_PORT}/readyz",
        f"http://127.0.0.1:{SERVICE_PORT}/healthz",
    }:
        raise ActivationError("health URL must be the fixed local endpoint")
    request = urllib.request.Request(url, headers={"Accept": "application/json"})  # noqa: S310
    with opener.open(request, timeout=2) as response:
        if response.status != 200:
            raise ActivationError("health endpoint is not ready")
        payload = response.read(65_537)
    if len(payload) > 65_536:
        raise ActivationError("health endpoint response is too large")
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ActivationError("health endpoint response is not an object")
    return value


def _health_ready(expected_sha: str | None) -> bool:
    try:
        ready = _read_small_json_response(f"http://127.0.0.1:{SERVICE_PORT}/readyz")
        if ready.get("status") != "ready" or ready.get("migration") != EXPECTED_MIGRATION:
            return False
        if expected_sha is not None:
            release = ready.get("release")
            if not isinstance(release, dict) or release.get("sha") != expected_sha:
                return False
        health = _read_small_json_response(f"http://127.0.0.1:{SERVICE_PORT}/healthz")
        return health.get("status") == "ok"
    except (
        OSError,
        ValueError,
        urllib.error.URLError,
        ActivationError,
    ):
        return False


def _systemctl(action: str) -> bool:
    if action not in {"daemon-reload", "restart"}:
        return False
    args = ["systemctl", "--user", action]
    if action == "restart":
        args.append(SERVICE_NAME)
    try:
        result = subprocess.run(  # noqa: S603 - fixed unit and actions, no shell
            args,  # noqa: S607
            capture_output=True,
            check=False,
            env=os.environ.copy(),
            stdin=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


class ProductionOperations:
    def git_matches(self, repo: Path, sha: str) -> bool:
        return _git_ready(repo, sha)

    def ci_success(self, repo: Path, sha: str) -> bool:
        return _ci_success(repo, sha)

    def preflight_ready(self, repo: Path, sha: str, backup_dir: Path) -> bool:
        try:
            module = _preflight_module()
            report = module.run_preflight(
                module.PreflightConfig(
                    expect_sha=sha,
                    repo=repo,
                    backup_dir=backup_dir,
                    max_age_hours=MAX_BACKUP_AGE.total_seconds() / 3600,
                ),
                datetime.now(UTC),
            )
        except Exception:
            return False
        return bool(report.get("ok"))

    def schema_ready(self, release: Release, env_file: Path) -> bool:
        return _schema_ready(release, env_file)

    def systemctl(self, action: str) -> bool:
        return _systemctl(action)

    def health_ready(self, expected_sha: str | None) -> bool:
        return _health_ready(expected_sha)

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def _expect_sha(value: str) -> str:
    if SHA_RE.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("expected SHA must be 40 lowercase hexadecimal characters")
    return value


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return None
    return parsed.astimezone(UTC)


def _fresh(value: datetime, now: datetime) -> bool:
    age = now - value
    return -FUTURE_SKEW <= age <= MAX_BACKUP_AGE


def _lexical(path: Path) -> str:
    return os.path.normpath(os.path.abspath(path))


def _is_regular(path: Path) -> bool:
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except OSError:
        return False


def _require_plain_directory(path: Path, label: str) -> None:
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise ActivationError(f"{label} is unavailable") from exc
    if not stat.S_ISDIR(mode):
        raise ActivationError(f"{label} must be a directory, not a symlink")


def _require_owned_directory(path: Path, label: str) -> None:
    _require_plain_directory(path, label)
    try:
        info = path.lstat()
    except OSError as exc:
        raise ActivationError(f"{label} is unavailable") from exc
    if info.st_uid != os.geteuid() or info.st_mode & 0o022:
        raise ActivationError(f"{label} has unsafe ownership or permissions")


def _validate_env_file(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise ActivationError("environment file is unavailable") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise ActivationError(
            "environment file must be an owner-controlled regular file with mode 0600"
        )


def _open_regular(path: Path, limit: int) -> tuple[int, bytes]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ActivationError("required file is unavailable or is a symlink") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ActivationError("required file has an invalid type or size")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return stat.S_IMODE(info.st_mode), b"".join(chunks)
    finally:
        os.close(fd)


def _read_regular(path: Path, limit: int) -> bytes:
    return _open_regular(path, limit)[1]


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _read_json_object(path: Path, limit: int) -> JsonObject:
    raw = _read_regular(path, limit)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise ActivationError("required JSON file is invalid") from exc
    if not isinstance(value, dict):
        raise ActivationError("required JSON file must contain an object")
    return value


def _digest(path: Path) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ActivationError("release or backup file is unavailable") from exc
    digest = hashlib.sha256()
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ActivationError("hashed path is not a regular file")
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    finally:
        os.close(fd)
    return digest.hexdigest()


def _collect_release_file(
    release: Path,
    relative: str,
    files: dict[str, str],
    *,
    exclude_python_cache: bool,
) -> None:
    root = release / relative
    _require_plain_directory(root, "release inventory directory")
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise ActivationError("release inventory cannot be read") from exc
        for entry in entries:
            if entry.is_symlink():
                raise ActivationError("release inventory contains a symlink")
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise ActivationError("release inventory cannot be inspected") from exc
            if stat.S_ISDIR(info.st_mode):
                if exclude_python_cache and entry.name == "__pycache__":
                    continue
                pending.append(Path(entry.path))
                continue
            if not stat.S_ISREG(info.st_mode):
                raise ActivationError("release inventory contains a special file")
            if exclude_python_cache and entry.name.endswith(".pyc"):
                continue
            path = Path(entry.path)
            key = path.relative_to(release).as_posix()
            files[key] = _digest(path)


def _expected_inventory(release: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for relative in INVENTORY_DIRECTORIES:
        _collect_release_file(
            release,
            relative,
            files,
            exclude_python_cache=True,
        )
    _collect_release_file(
        release,
        INVENTORY_DIRECTORY_ALL,
        files,
        exclude_python_cache=False,
    )
    for relative in INVENTORY_FILES:
        path = release / relative
        if not _is_regular(path):
            raise ActivationError("release manifest file is missing or is a symlink")
        files[relative] = _digest(path)
    return files


def _valid_relative_inventory_key(value: str) -> bool:
    if not value or value.startswith("/") or "\\" in value or "\x00" in value:
        return False
    parts = value.split("/")
    return all(part not in {"", ".", ".."} for part in parts)


def _migration_allowed(value: object, *, require_current: bool) -> bool:
    return value == EXPECTED_MIGRATION if require_current else value in KNOWN_MIGRATIONS


def _load_release(config: ActivationConfig, *, require_current_migration: bool = True) -> Release:
    _require_owned_directory(config.release_root, "release root")
    releases = config.release_root / "releases"
    _require_owned_directory(releases, "releases directory")
    release = releases / config.expect_sha
    _require_owned_directory(release, "release target")

    manifest_path = release / "manifest.json"
    if not _is_regular(manifest_path):
        raise ActivationError("release manifest is missing or is a symlink")
    manifest = _read_json_object(manifest_path, MANIFEST_LIMIT)
    built_at = _parse_utc(manifest.get("built_at"))
    if built_at is None:
        raise ActivationError("release build timestamp is invalid")
    if (
        type(manifest.get("schema")) is not int
        or manifest.get("schema") != 1
        or manifest.get("sha") != config.expect_sha
        or not _migration_allowed(
            manifest.get("migration"), require_current=require_current_migration
        )
    ):
        raise ActivationError("release manifest schema, SHA, or migration is invalid")

    manifest_files = manifest.get("files")
    if not isinstance(manifest_files, dict):
        raise ActivationError("release manifest file inventory is missing")
    declared: dict[str, str] = {}
    for key, value in manifest_files.items():
        if (
            not isinstance(key, str)
            or not _valid_relative_inventory_key(key)
            or not isinstance(value, str)
            or DIGEST_RE.fullmatch(value) is None
        ):
            raise ActivationError("release manifest file inventory is invalid")
        declared[key] = value
    if not _is_regular(release / "apps/web/dist/index.html"):
        raise ActivationError("release web index is missing")
    actual = _expected_inventory(release)
    if declared != actual:
        raise ActivationError("release manifest inventory does not match release files")

    venv = release / ".venv"
    bin_dir = venv / "bin"
    uvicorn = bin_dir / "uvicorn"
    python = bin_dir / "python"
    _require_plain_directory(venv, "release virtual environment")
    _require_plain_directory(bin_dir, "release virtual environment bin directory")
    if not _is_regular(uvicorn) or not _is_regular(python):
        raise ActivationError("release virtual environment executable is missing or unsafe")
    try:
        executable = uvicorn.stat().st_mode
    except OSError as exc:
        raise ActivationError("release virtual environment executable is unavailable") from exc
    if not stat.S_ISREG(executable) or not executable & (
        stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    ):
        raise ActivationError("release uvicorn executable is not executable")
    if not os.access(python, os.X_OK):
        raise ActivationError("release Python executable is not executable")
    return Release(sha=config.expect_sha, path=release, manifest=manifest)


def _release_link(config: ActivationConfig, name: str) -> str | None:
    path = config.release_root / name
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ActivationError(f"{name} release pointer is unavailable") from exc
    if not stat.S_ISLNK(info.st_mode):
        raise ActivationError(f"{name} path must be a relative release symlink")
    try:
        raw = os.readlink(path)
    except OSError as exc:
        raise ActivationError(f"{name} release pointer is unreadable") from exc
    prefix = "releases/"
    if not raw.startswith(prefix):
        raise ActivationError(f"{name} release pointer escapes the release root")
    sha = raw.removeprefix(prefix)
    if SHA_RE.fullmatch(sha) is None or raw != f"{prefix}{sha}":
        raise ActivationError(f"{name} release pointer is not a canonical relative path")
    target = config.release_root / "releases" / sha
    _require_owned_directory(target, f"{name} release target")
    return sha


def _release_for_sha(config: ActivationConfig, sha: str) -> Release:
    return _load_release(
        ActivationConfig(
            action=config.action,
            expect_sha=sha,
            release_root=config.release_root,
            repo=config.repo,
            env_file=config.env_file,
            backup_dir=config.backup_dir,
            backup_manifest=config.backup_manifest,
            restore_evidence=config.restore_evidence,
            unit_path=config.unit_path,
        ),
        require_current_migration=False,
    )


def _inspect_topology(
    config: ActivationConfig,
) -> tuple[str | None, str | None]:
    current = _release_link(config, "current")
    previous = _release_link(config, "previous")
    if current is None and previous is not None:
        raise ActivationError("previous exists without a current release pointer")
    if current is not None and previous == current:
        raise ActivationError("current and previous release pointers must differ")
    for sha in {current, previous} - {None, config.expect_sha}:
        assert sha is not None
        _release_for_sha(config, sha)
    return current, previous


def _read_unit(path: Path) -> tuple[bytes, int]:
    try:
        info = path.lstat()
    except OSError as exc:
        raise ActivationError("service unit is unavailable") from exc
    if not stat.S_ISREG(info.st_mode):
        raise ActivationError("service unit must be a regular file, not a symlink")
    if info.st_uid != os.geteuid() or info.st_mode & 0o7022:
        raise ActivationError("service unit has unsafe ownership or permissions")
    mode, data = _open_regular(path, UNIT_LIMIT)
    return data, mode


def _latest_manifest(config: ActivationConfig) -> Path:
    try:
        module = _preflight_module()
        candidate, _ = module._select_latest_manifest(config.backup_dir)
    except Exception as exc:
        raise ActivationError("latest production backup manifest is unavailable") from exc
    if candidate is None:
        raise ActivationError("latest production backup manifest is unavailable")
    return Path(candidate.path)


def _validate_backup(
    config: ActivationConfig,
    now: datetime,
) -> None:
    _require_owned_directory(config.backup_dir, "backup directory")
    if not config.backup_manifest.is_absolute() or not config.restore_evidence.is_absolute():
        raise ActivationError("backup and restore evidence paths must be absolute")
    if _lexical(_latest_manifest(config)) != _lexical(config.backup_manifest):
        raise ActivationError("backup manifest is not the latest production backup")

    manifest = _read_json_object(config.backup_manifest, MANIFEST_LIMIT)
    dump_name = manifest.get("dump")
    digest = manifest.get("sha256")
    created_at = _parse_utc(manifest.get("created_at"))
    safe_dump = (
        isinstance(dump_name, str)
        and DUMP_RE.fullmatch(dump_name) is not None
        and config.backup_manifest.name == f"{dump_name}.manifest.json"
    )
    if (
        manifest.get("db") != TARGET_DB
        or manifest.get("migration") != EXPECTED_MIGRATION
        or not safe_dump
        or not isinstance(digest, str)
        or DIGEST_RE.fullmatch(digest) is None
        or created_at is None
        or not _fresh(created_at, now)
    ):
        raise ActivationError("production backup manifest is invalid or stale")

    counts = manifest.get("counts")
    tables = _preflight_module().TABLES
    if (
        not isinstance(counts, dict)
        or set(counts) != set(tables)
        or any(
            type(counts[name]) is not int or not 0 <= counts[name] <= 2**63 - 1 for name in tables
        )
    ):
        raise ActivationError("backup table counts are invalid")
    assert isinstance(dump_name, str)
    dump = config.backup_dir / dump_name
    sidecar = dump.with_name(f"{dump.name}.sha256")
    if not _is_regular(dump) or not _is_regular(sidecar):
        raise ActivationError("production backup files are missing or unsafe")
    try:
        sidecar_text = _read_regular(sidecar, 4096).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ActivationError("production backup checksum is invalid") from exc
    sidecar_match = SIDECAR_RE.fullmatch(sidecar_text)
    actual_digest = _digest(dump)
    if (
        actual_digest != digest
        or sidecar_match is None
        or sidecar_match.group(1) != digest
        or sidecar_match.group(2) != dump.name
    ):
        raise ActivationError("production backup SHA-256 verification failed")

    _validate_env_file(config.restore_evidence)  # same owner-controlled 0600 file contract
    evidence = _read_json_object(config.restore_evidence, EVIDENCE_LIMIT)
    restored_at = _parse_utc(evidence.get("restored_at"))
    if (
        evidence.get("backup_sha256") != digest
        or evidence.get("migration") != EXPECTED_MIGRATION
        or evidence.get("restored") is not True
        or evidence.get("source_db") != TARGET_DB
        or restored_at is None
        or restored_at < created_at
        or not _fresh(restored_at, now)
    ):
        raise ActivationError("restore evidence does not match the fresh production backup")


def _systemd_quote(value: str) -> str:
    if "\n" in value or "\r" in value or "\x00" in value:
        raise ActivationError("service unit value contains an unsupported character")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    return f'"{escaped}"'


def _systemd_path(value: str) -> str:
    if not value.startswith("/") or any(c in value for c in ("\n", "\r", "\x00", '"')):
        raise ActivationError("systemd path must be an absolute supported path")
    return (
        value.replace("\\", "\\\\").replace("%", "%%").replace(" ", "\\x20").replace("\t", "\\x09")
    )


def _unit_text(release: Release, env_file: Path) -> str:
    release_dir = str(release.path)
    web_dist = str(release.path / "apps/web/dist")
    app_dir = str(release.path / "apps/api")
    uvicorn = str(release.path / ".venv/bin/uvicorn")
    return (
        "[Unit]\n"
        "Description=RIHRP Research Studio API\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={_systemd_path(release_dir)}\n"
        f"EnvironmentFile={_systemd_path(str(env_file))}\n"
        f"Environment={_systemd_quote(f'RIHRP_WEB_DIST={web_dist}')}\n"
        f"Environment={_systemd_quote(f'RIHRP_RELEASE_SHA={release.sha}')}\n"
        f"Environment={_systemd_quote(f'RIHRP_RELEASE_DIR={release_dir}')}\n"
        f"ExecStart={_systemd_quote(uvicorn)} rihrp.main:app "
        f"--app-dir {_systemd_quote(app_dir)} --host 127.0.0.1 --port {SERVICE_PORT}\n"
        "Restart=on-failure\n"
        "RestartSec=3\n"
        "NoNewPrivileges=true\n"
        "ProtectSystem=strict\n"
        "ProtectHome=read-only\n"
        "PrivateTmp=true\n"
        "ReadWritePaths=/tmp\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError as exc:
        raise ActivationError("state directory durability check failed") from exc
    try:
        os.fsync(fd)
    except OSError as exc:
        raise ActivationError("state directory durability check failed") from exc
    finally:
        os.close(fd)


def _atomic_write(path: Path, data: bytes, mode: int) -> None:
    try:
        parent_info = path.parent.lstat()
    except OSError as exc:
        raise ActivationError("state file directory is unavailable") from exc
    if not stat.S_ISDIR(parent_info.st_mode):
        raise ActivationError("state file directory must not be a symlink")
    temporary = path.parent / f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd: int | None = None
    try:
        fd = os.open(temporary, flags, 0o600)
        os.fchmod(fd, mode)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise ActivationError("state file write failed")
            view = view[written:]
        os.fsync(fd)
        os.close(fd)
        fd = None
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except OSError as exc:
        raise ActivationError("state file write failed") from exc
    finally:
        if fd is not None:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


def _replace_release_link(path: Path, sha: str) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        info = None
    except OSError as exc:
        raise ActivationError("release pointer cannot be inspected") from exc
    if info is not None and not stat.S_ISLNK(info.st_mode):
        raise ActivationError("release pointer path contains a non-symlink entry")
    temporary = path.parent / f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    try:
        os.symlink(f"releases/{sha}", temporary)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except OSError as exc:
        raise ActivationError("release pointer replacement failed") from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


def _remove_release_link(path: Path) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ActivationError("release pointer cannot be inspected") from exc
    if not stat.S_ISLNK(info.st_mode):
        raise ActivationError("release pointer path contains a non-symlink entry")
    try:
        path.unlink()
        _fsync_directory(path.parent)
    except OSError as exc:
        raise ActivationError("release pointer removal failed") from exc


def _state_document(state: TransitionState) -> bytes:
    document = {
        "schema": 1,
        "action": state.action,
        "target_sha": state.target_sha,
        "previous_current": state.previous_current,
        "previous_previous": state.previous_previous,
        "unit_path": str(state.unit_path),
        "old_unit_mode": state.old_unit_mode,
        "old_unit_sha256": state.old_unit_sha256,
        "old_unit_base64": base64.b64encode(state.old_unit).decode("ascii"),
        "created_at": state.created_at.isoformat(),
    }
    return (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _persist_state(config: ActivationConfig, state: TransitionState) -> None:
    data = _state_document(state)
    history = config.release_root / "transitions"
    history.mkdir(mode=0o700, exist_ok=True)
    _require_owned_directory(history, "transition history")
    # Retain every old unit, including the initial legacy unit, across future activations.
    archive = (
        history / f"{state.created_at.strftime('%Y%m%dT%H%M%S%f')}-{secrets.token_hex(4)}.json"
    )
    _atomic_write(archive, data, 0o600)
    _atomic_write(config.release_root / "rollback-state.json", data, 0o600)
    _atomic_write(config.release_root / "transition-pending.json", data, 0o600)


def _finish_transition(config: ActivationConfig, status: str) -> None:
    _atomic_write(
        config.release_root / "transition-result.json",
        json.dumps({"status": status, "sha": config.expect_sha}).encode(),
        0o600,
    )
    pending = config.release_root / "transition-pending.json"
    if pending.exists():
        pending.unlink()
    _fsync_directory(config.release_root)


def _reject_interrupted_transition(config: ActivationConfig) -> None:
    pending = config.release_root / "transition-pending.json"
    if pending.exists() or pending.is_symlink():
        _read_json_object(pending, UNIT_LIMIT * 2)
        raise ActivationError(
            "interrupted transition recorded; "
            "reconcile saved unit and pointers manually before retry"
        )


def _wait_health(operations: Operations, expected_sha: str | None) -> bool:
    deadline = operations.monotonic() + HEALTH_TIMEOUT_SECONDS
    while True:
        try:
            if operations.health_ready(expected_sha):
                return True
        except Exception:  # noqa: S110 - bounded polling; no raw exception/secret logging
            pass
        remaining = deadline - operations.monotonic()
        if remaining <= 0:
            return False
        operations.sleep(min(1.0, remaining))


def _restore_transition(
    config: ActivationConfig,
    state: TransitionState,
    operations: Operations,
) -> bool:
    try:
        if state.unit_path != config.unit_path:
            return False
        decoded = state.old_unit
        if hashlib.sha256(decoded).hexdigest() != state.old_unit_sha256:
            return False
        if type(state.old_unit_mode) is not int or state.old_unit_mode & ~0o777:
            return False
        if state.previous_current is not None:
            _release_for_sha(config, state.previous_current)
            _replace_release_link(config.release_root / "current", state.previous_current)
        else:
            _remove_release_link(config.release_root / "current")
        if state.previous_previous is not None:
            _release_for_sha(config, state.previous_previous)
            _replace_release_link(config.release_root / "previous", state.previous_previous)
        else:
            _remove_release_link(config.release_root / "previous")
        _atomic_write(config.unit_path, decoded, state.old_unit_mode)
        if not operations.systemctl("daemon-reload"):
            return False
        if not operations.systemctl("restart"):
            return False
        return _wait_health(operations, state.previous_current)
    except Exception:
        return False


def _apply_transition(
    config: ActivationConfig,
    release: Release,
    previous_current: str | None,
    previous_previous: str | None,
    old_unit: bytes,
    old_unit_mode: int,
    operations: Operations,
    now: datetime,
) -> None:
    state = TransitionState(
        action=config.action,
        target_sha=release.sha,
        previous_current=previous_current,
        previous_previous=previous_previous,
        unit_path=config.unit_path,
        old_unit=old_unit,
        old_unit_mode=old_unit_mode,
        created_at=now,
    )
    new_unit = _unit_text(release, config.env_file).encode("utf-8")
    _persist_state(config, state)
    try:
        _replace_release_link(config.release_root / "current", release.sha)
        if previous_current is None:
            _remove_release_link(config.release_root / "previous")
        else:
            _replace_release_link(config.release_root / "previous", previous_current)
        _atomic_write(config.unit_path, new_unit, 0o644)
        if not operations.systemctl("daemon-reload"):
            raise ActivationError("daemon reload failed")
        if not operations.systemctl("restart"):
            raise ActivationError("service restart failed")
        if not _wait_health(operations, release.sha):
            raise ActivationError("release health verification failed")
    except Exception:
        if config.action == "rollback":
            raise ActivationError(
                "rollback failed; automatic retry is disabled; manual intervention required"
            ) from None
        if _restore_transition(config, state, operations):
            _finish_transition(config, "failed_recovered")
            raise ActivationError(
                f"{config.action} failed; previous service state was recovered"
            ) from None
        raise ActivationError(
            f"{config.action} failed; previous service state could NOT be recovered; "
            "manual intervention required"
        ) from None
    # Do not start a new recovery transition if only the completion journal fsync fails:
    # the target service is already healthy and both unit/pointers are coherent.
    try:
        _finish_transition(config, "succeeded")
    except Exception:
        raise ActivationError(
            "release is healthy but completion journal failed; manual verification required"
        ) from None


@contextmanager
def _release_lock(release_root: Path) -> Iterator[None]:
    import fcntl

    _require_owned_directory(release_root, "release root")
    path = release_root / ".release.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise ActivationError("release lock cannot be opened") from exc
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise ActivationError("release lock is not a trusted regular file")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ActivationError("another release operation is already in progress") from exc
        yield
    finally:
        os.close(fd)


def _validate_config_paths(config: ActivationConfig) -> None:
    if config.action not in {"activate", "rollback"}:
        raise ActivationError("action must be activate or rollback")
    _expect_sha(config.expect_sha)
    for path in (
        config.release_root,
        config.repo,
        config.env_file,
        config.backup_dir,
        config.backup_manifest,
        config.restore_evidence,
        config.unit_path,
    ):
        if not path.is_absolute():
            raise ActivationError("all release paths must be absolute")
    _require_plain_directory(config.repo, "repository")
    _require_owned_directory(config.unit_path.parent, "systemd user unit directory")


def execute(
    config: ActivationConfig,
    operations: Operations | None = None,
    now: datetime | None = None,
) -> None:
    operations = operations or ProductionOperations()
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None or current_time.utcoffset() != timedelta(0):
        raise ActivationError("release timestamp must be UTC")
    _validate_config_paths(config)
    _validate_env_file(config.env_file)

    with _release_lock(config.release_root):
        _reject_interrupted_transition(config)
        release = _load_release(
            config, require_current_migration=config.action == "activate"
        )
        current, previous = _inspect_topology(config)
        old_unit, old_unit_mode = _read_unit(config.unit_path)

        if config.action == "activate":
            if current == release.sha:
                raise ActivationError("requested release is already current")
            if not operations.git_matches(config.repo, release.sha):
                raise ActivationError("repository HEAD, origin/main, or worktree gate failed")
            if not operations.ci_success(config.repo, release.sha):
                raise ActivationError("CI is not completed successfully for the exact SHA")
        else:
            if previous != release.sha:
                raise ActivationError("rollback SHA must equal the current previous release")
            if current is None or current == release.sha:
                raise ActivationError("rollback previous release is not distinct from current")

        if config.action == "activate":
            if not operations.preflight_ready(config.repo, release.sha, config.backup_dir):
                raise ActivationError("fresh production backup preflight failed")
            _validate_backup(config, current_time)
        if not operations.schema_ready(release, config.env_file):
            raise ActivationError(
                "production configuration or read-only migration 0004 inspection failed"
            )

        _apply_transition(
            config,
            release,
            current,
            previous,
            old_unit,
            old_unit_mode,
            operations,
            current_time,
        )


def _home_directory() -> Path:
    return Path(pwd.getpwuid(os.geteuid()).pw_dir)


def _parser() -> argparse.ArgumentParser:
    home = _home_directory()
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(prog="release_activate.py")
    parser.add_argument("action", choices=("activate", "rollback"))
    parser.add_argument("--expect-sha", required=True, type=_expect_sha)
    parser.add_argument("--release-root", type=Path, default=home / ".local/share/rihrp")
    parser.add_argument("--repo", type=Path, default=repo_root)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=home / ".config/rihrp/rihrp.conf",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=home / ".local/state/rihrp/backups",
    )
    parser.add_argument("--backup-manifest", type=Path)
    parser.add_argument("--restore-evidence", type=Path)
    return parser


def _config_from_args(args: argparse.Namespace) -> ActivationConfig:
    home = _home_directory()
    if args.action == "activate" and (
        args.backup_manifest is None or args.restore_evidence is None
    ):
        raise ActivationError("activation requires backup manifest and restore evidence")
    return ActivationConfig(
        action=args.action,
        expect_sha=args.expect_sha,
        release_root=args.release_root,
        repo=args.repo,
        env_file=args.env_file,
        backup_dir=args.backup_dir,
        backup_manifest=args.backup_manifest or args.backup_dir / "unused-rollback-manifest",
        restore_evidence=args.restore_evidence or args.backup_dir / "unused-rollback-evidence",
        unit_path=home / ".config/systemd/user" / SERVICE_NAME,
    )


def main(
    argv: list[str] | None = None,
    *,
    operations: Operations | None = None,
    now: datetime | None = None,
) -> int:
    args = _parser().parse_args(argv)
    try:
        execute(_config_from_args(args), operations=operations, now=now)
    except ActivationError as exc:
        print(f"release action failed: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print("release action failed: internal validation error", file=sys.stderr)
        return 1
    print(f"release {args.action} complete sha={args.expect_sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
