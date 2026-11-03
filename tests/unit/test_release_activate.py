"""Unit tests for tools/release_activate.py.

Every external effect (git, gh, systemctl, HTTP health, read-only DB inspect)
is a FakeOperations instance; releases, backups, the service unit, and the
environment file are built under tmp_path only. No real service, database,
systemctl invocation, or production path is touched.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import functools
import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Final

import pytest
from tools import release_activate

NOW: Final = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
SHA_A: Final = "a" * 40
SHA_B: Final = "b" * 40
DUMP_NAME: Final = "rihrp_production-20261103T110000000000-1001.dump"
NEWER_DUMP_NAME: Final = "rihrp_production-20261103T113000000000-1002.dump"
MIGRATION: Final = release_activate.EXPECTED_MIGRATION
OLD_UNIT: Final = b'[Service]\nExecStart="/opt/previous/bin/uvicorn" rihrp.main:app\n'
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
RELEASE_FILES: Final = {
    "apps/api/rihrp/__init__.py": b"",
    "apps/api/rihrp/main.py": b"from fastapi import FastAPI\n",
    "infra/migrations/env.py": b"# migration environment\n",
    "infra/migrations/versions/0004_research_documents.py": b"# revision 0004\n",
    "apps/web/dist/index.html": b"<!doctype html>\n",
    "apps/web/dist/assets/app.js": b"console.log('rihrp');\n",
    "uv.lock": b"version = 1\n",
    "requirements-production.txt": b"fastapi==0.115.0\n",
    "pyproject.toml": b"[project]\nname = 'rihrp'\n",
    "apps/web/package-lock.json": b"{}\n",
    "apps/web/package.json": b"{}\n",
}
INVENTORY_TREES: Final = (
    ("apps/api", True),
    ("infra/migrations", True),
    ("apps/web/dist", False),
)
INVENTORY_FILES: Final = (
    "uv.lock",
    "requirements-production.txt",
    "pyproject.toml",
    "apps/web/package-lock.json",
    "apps/web/package.json",
)


@dataclass(frozen=True, slots=True)
class World:
    """One isolated release root, repository, backup set, unit, and env file."""

    release_root: Path
    releases: Path
    repo: Path
    env_file: Path
    backup_dir: Path
    backup_manifest: Path
    restore_evidence: Path
    unit: Path

    def config(
        self,
        sha: str,
        action: str = "activate",
    ) -> release_activate.ActivationConfig:
        return release_activate.ActivationConfig(
            action=action,
            expect_sha=sha,
            release_root=self.release_root,
            repo=self.repo,
            env_file=self.env_file,
            backup_dir=self.backup_dir,
            backup_manifest=self.backup_manifest,
            restore_evidence=self.restore_evidence,
            unit_path=self.unit,
        )


@dataclass
class FakeOperations:
    """Replacement for the Operations protocol; records every call."""

    git_ok: bool = True
    ci_ok: bool = True
    preflight_ok: bool = True
    schema_ok: bool = True
    systemctl_outcomes: list[bool] = field(default_factory=lambda: [True, True])
    healthy: bool | set[str | None] = True
    clock: float = 0.0
    calls: list[tuple[object, ...]] = field(default_factory=list)

    def git_matches(self, repo: Path, sha: str) -> bool:
        self.calls.append(("git_matches", str(repo), sha))
        return self.git_ok

    def ci_success(self, repo: Path, sha: str) -> bool:
        self.calls.append(("ci_success", str(repo), sha))
        return self.ci_ok

    def preflight_ready(self, repo: Path, sha: str, backup_dir: Path) -> bool:
        self.calls.append(("preflight_ready", str(repo), sha, str(backup_dir)))
        return self.preflight_ok

    def schema_ready(self, release: release_activate.Release, env_file: Path) -> bool:
        self.calls.append(("schema_ready", release.sha, str(env_file)))
        return self.schema_ok

    def systemctl(self, action: str) -> bool:
        self.calls.append(("systemctl", action))
        if not self.systemctl_outcomes:
            return True
        if len(self.systemctl_outcomes) == 1:
            return self.systemctl_outcomes[0]
        return self.systemctl_outcomes.pop(0)

    def health_ready(self, expected_sha: str | None) -> bool:
        self.calls.append(("health_ready", expected_sha))
        if isinstance(self.healthy, bool):
            return self.healthy
        return expected_sha in self.healthy

    def monotonic(self) -> float:
        return self.clock

    def sleep(self, seconds: float) -> None:
        self.clock += seconds


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump_json(path: Path, document: dict[str, object]) -> None:
    path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")


def _assert_rejected(
    call: Callable[[], object],
    fragment: str,
    *,
    error: type[BaseException] = release_activate.ActivationError,
    label: str = "",
) -> None:
    with pytest.raises(error) as excinfo:
        call()
    assert fragment in str(excinfo.value), f"{label}: {excinfo.value}"


def _inventory(release: Path) -> dict[str, str]:
    """Independent statement of the release inventory the activator must accept."""
    files: dict[str, str] = {}
    for tree, skip_python_cache in INVENTORY_TREES:
        for path in sorted((release / tree).rglob("*")):
            relative = path.relative_to(release)
            if skip_python_cache and path.suffix == ".pyc":
                continue
            if skip_python_cache and "__pycache__" in relative.parts:
                continue
            if path.is_file():
                files[relative.as_posix()] = _sha256(path.read_bytes())
    for name in INVENTORY_FILES:
        files[name] = _sha256((release / name).read_bytes())
    return files


def _make_release(world: World, sha: str) -> Path:
    release = world.releases / sha
    release.mkdir(mode=0o755)
    for name, data in RELEASE_FILES.items():
        path = release / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    bin_dir = release / ".venv/bin"
    bin_dir.mkdir(parents=True)
    for executable in (bin_dir / "uvicorn", bin_dir / "python"):
        executable.write_bytes(b"#!/bin/sh\nexit 0\n")
        executable.chmod(0o755)
    document: dict[str, object] = {
        "schema": 1,
        "sha": sha,
        "migration": MIGRATION,
        "built_at": "2026-11-03T09:00:00.000000Z",
        "files": _inventory(release),
    }
    _dump_json(release / "manifest.json", document)
    release.chmod(0o755)
    return release


def _write_backup(
    backup_dir: Path,
    *,
    created_at: datetime,
    name: str = DUMP_NAME,
) -> tuple[Path, str]:
    payload = f"PGDMP fixture {name}\n".encode()
    (backup_dir / name).write_bytes(payload)
    digest = _sha256(payload)
    (backup_dir / f"{name}.sha256").write_text(f"{digest}  {name}\n", encoding="utf-8")
    document: dict[str, object] = {
        "db": release_activate.TARGET_DB,
        "dump": name,
        "sha256": digest,
        "migration": MIGRATION,
        "created_at": created_at.isoformat(),
        "counts": dict.fromkeys(TABLES, 0),
    }
    manifest = backup_dir / f"{name}.manifest.json"
    _dump_json(manifest, document)
    return manifest, digest


def _write_evidence(path: Path, *, digest: str, **changes: object) -> Path:
    document: dict[str, object] = {
        "backup_sha256": digest,
        "migration": MIGRATION,
        "restored": True,
        "source_db": release_activate.TARGET_DB,
        "restored_at": (NOW - timedelta(minutes=30)).isoformat(),
    }
    document.update(changes)
    _dump_json(path, document)
    path.chmod(0o600)
    return path


def _world(base: Path) -> World:
    base.mkdir(parents=True, exist_ok=True)
    release_root = base / "release-root"
    releases = release_root / "releases"
    releases.mkdir(parents=True)
    repo = base / "repo"
    repo.mkdir()
    env_file = base / "rihrp.conf"
    env_file.write_text("RIHRP_ENV=production\n", encoding="utf-8")
    backup_dir = base / "backups"
    backup_dir.mkdir()
    backup_manifest, digest = _write_backup(backup_dir, created_at=NOW - timedelta(hours=1))
    restore_evidence = base / "restore-evidence.json"
    _write_evidence(restore_evidence, digest=digest)
    unit_dir = base / "systemd"
    unit_dir.mkdir()
    unit = unit_dir / "rihrp.service"
    unit.write_bytes(OLD_UNIT)
    for directory in (release_root, releases, repo, unit_dir):
        directory.chmod(0o755)
    backup_dir.chmod(0o700)
    env_file.chmod(0o600)
    unit.chmod(0o644)
    return World(
        release_root=release_root,
        releases=releases,
        repo=repo,
        env_file=env_file,
        backup_dir=backup_dir,
        backup_manifest=backup_manifest,
        restore_evidence=restore_evidence,
        unit=unit,
    )


def _point(world: World, name: str, sha: str) -> None:
    path = world.release_root / name
    with contextlib.suppress(FileNotFoundError):
        path.unlink()
    path.symlink_to(f"releases/{sha}")


def test_activate_switches_current_previous_unit_and_persists_state(tmp_path: Path) -> None:
    world = _world(tmp_path)
    _make_release(world, SHA_A)
    release = _make_release(world, SHA_B)
    _point(world, "current", SHA_A)
    ops = FakeOperations()

    release_activate.execute(world.config(SHA_B), operations=ops, now=NOW)

    assert os.readlink(world.release_root / "current") == f"releases/{SHA_B}"
    assert os.readlink(world.release_root / "previous") == f"releases/{SHA_A}"
    unit_text = world.unit.read_text(encoding="utf-8")
    assert f'Environment="RIHRP_RELEASE_SHA={SHA_B}"' in unit_text
    assert f"WorkingDirectory={release}" in unit_text
    assert (world.unit.stat().st_mode & 0o777) == 0o644

    state_path = world.release_root / "rollback-state.json"
    state = _json(state_path)
    assert (state_path.stat().st_mode & 0o777) == 0o600
    assert state["schema"] == 1
    assert state["action"] == "activate"
    assert state["target_sha"] == SHA_B
    assert state["previous_current"] == SHA_A
    assert state["previous_previous"] is None
    assert state["unit_path"] == str(world.unit)
    assert base64.b64decode(str(state["old_unit_base64"])) == OLD_UNIT
    assert state["old_unit_sha256"] == _sha256(OLD_UNIT)
    assert state["old_unit_mode"] == 0o644
    assert state["created_at"] == NOW.isoformat()

    assert [call[1] for call in ops.calls if call[0] == "systemctl"] == [
        "daemon-reload",
        "restart",
    ]
    assert [call[1] for call in ops.calls if call[0] == "health_ready"] == [SHA_B]
    assert ("git_matches", str(world.repo), SHA_B) in ops.calls
    assert ("ci_success", str(world.repo), SHA_B) in ops.calls
    assert (
        "preflight_ready",
        str(world.repo),
        SHA_B,
        str(world.backup_dir),
    ) in ops.calls
    assert ("schema_ready", SHA_B, str(world.env_file)) in ops.calls
    lock_mode = (world.release_root / ".release.lock").stat().st_mode & 0o777
    assert lock_mode == 0o600


def test_first_activation_creates_current_and_leaves_no_previous(tmp_path: Path) -> None:
    world = _world(tmp_path)
    _make_release(world, SHA_B)
    ops = FakeOperations()

    release_activate.execute(world.config(SHA_B), operations=ops, now=NOW)

    assert os.readlink(world.release_root / "current") == f"releases/{SHA_B}"
    assert not (world.release_root / "previous").is_symlink()
    state = _json(world.release_root / "rollback-state.json")
    assert state["previous_current"] is None
    assert state["previous_previous"] is None


@pytest.mark.parametrize(
    ("gate", "fragment"),
    [
        ("git_ok", "repository HEAD, origin/main, or worktree gate failed"),
        ("ci_ok", "CI is not completed successfully for the exact SHA"),
        ("preflight_ok", "fresh production backup preflight failed"),
        ("schema_ok", "read-only migration 0004 inspection failed"),
    ],
)
def test_gate_failure_aborts_before_any_state_change(
    tmp_path: Path,
    gate: str,
    fragment: str,
) -> None:
    world = _world(tmp_path)
    _make_release(world, SHA_A)
    _make_release(world, SHA_B)
    _point(world, "current", SHA_A)
    ops = replace(FakeOperations(), **{gate: False})

    with pytest.raises(release_activate.ActivationError) as excinfo:
        release_activate.execute(world.config(SHA_B), operations=ops, now=NOW)

    assert fragment in str(excinfo.value)
    assert os.readlink(world.release_root / "current") == f"releases/{SHA_A}"
    assert not (world.release_root / "previous").is_symlink()
    assert world.unit.read_bytes() == OLD_UNIT
    assert not (world.release_root / "rollback-state.json").exists()
    assert [call for call in ops.calls if call[0] == "systemctl"] == []


def test_release_already_current_is_rejected(tmp_path: Path) -> None:
    world = _world(tmp_path)
    _make_release(world, SHA_A)
    _make_release(world, SHA_B)
    _point(world, "current", SHA_A)
    ops = FakeOperations()

    with pytest.raises(release_activate.ActivationError) as excinfo:
        release_activate.execute(world.config(SHA_A), operations=ops, now=NOW)

    assert "already current" in str(excinfo.value)
    assert [call for call in ops.calls if call[0] == "systemctl"] == []
    assert world.unit.read_bytes() == OLD_UNIT


def test_health_timeout_restores_previous_release(tmp_path: Path) -> None:
    world = _world(tmp_path)
    _make_release(world, SHA_A)
    _make_release(world, SHA_B)
    _point(world, "current", SHA_A)
    ops = FakeOperations(healthy={SHA_A})

    with pytest.raises(release_activate.ActivationError) as excinfo:
        release_activate.execute(world.config(SHA_B), operations=ops, now=NOW)

    assert "previous service state was recovered" in str(excinfo.value)
    assert os.readlink(world.release_root / "current") == f"releases/{SHA_A}"
    assert not (world.release_root / "previous").is_symlink()
    assert world.unit.read_bytes() == OLD_UNIT
    assert [call[1] for call in ops.calls if call[0] == "systemctl"] == [
        "daemon-reload",
        "restart",
        "daemon-reload",
        "restart",
    ]
    assert ("health_ready", SHA_B) in ops.calls
    assert ops.calls[-1] == ("health_ready", SHA_A)


def test_failed_restore_reports_unrecovered_state(tmp_path: Path) -> None:
    world = _world(tmp_path)
    _make_release(world, SHA_A)
    _make_release(world, SHA_B)
    _point(world, "current", SHA_A)
    ops = FakeOperations(systemctl_outcomes=[True, True, True, False], healthy=False)

    with pytest.raises(release_activate.ActivationError) as excinfo:
        release_activate.execute(world.config(SHA_B), operations=ops, now=NOW)

    message = str(excinfo.value)
    assert "could NOT be recovered" in message
    assert "manual intervention required" in message
    # Pointers and the unit were already restored before the failing restart, so the
    # "unrecovered" verdict reports unverified service health, not stale files.
    assert os.readlink(world.release_root / "current") == f"releases/{SHA_A}"
    assert not (world.release_root / "previous").is_symlink()
    assert world.unit.read_bytes() == OLD_UNIT
    assert [call[1] for call in ops.calls if call[0] == "systemctl"] == [
        "daemon-reload",
        "restart",
        "daemon-reload",
        "restart",
    ]


def test_daemon_reload_failure_restores_previous_unit(tmp_path: Path) -> None:
    world = _world(tmp_path)
    _make_release(world, SHA_A)
    _make_release(world, SHA_B)
    _point(world, "current", SHA_A)
    ops = FakeOperations(systemctl_outcomes=[False, True, True])

    with pytest.raises(release_activate.ActivationError) as excinfo:
        release_activate.execute(world.config(SHA_B), operations=ops, now=NOW)

    assert "previous service state was recovered" in str(excinfo.value)
    assert os.readlink(world.release_root / "current") == f"releases/{SHA_A}"
    assert world.unit.read_bytes() == OLD_UNIT
    assert (world.unit.stat().st_mode & 0o777) == 0o644
    assert [call[1] for call in ops.calls if call[0] == "systemctl"] == [
        "daemon-reload",
        "daemon-reload",
        "restart",
    ]


def test_rollback_swaps_previous_back_into_current(tmp_path: Path) -> None:
    world = _world(tmp_path)
    _make_release(world, SHA_A)
    _make_release(world, SHA_B)
    _point(world, "current", SHA_B)
    _point(world, "previous", SHA_A)
    # Disaster recovery must not depend on a fresh backup/evidence or CI/main.
    world.backup_manifest.unlink()
    world.restore_evidence.unlink()
    ops = FakeOperations(git_ok=False, ci_ok=False, preflight_ok=False)

    release_activate.execute(world.config(SHA_A, action="rollback"), operations=ops, now=NOW)

    assert os.readlink(world.release_root / "current") == f"releases/{SHA_A}"
    assert os.readlink(world.release_root / "previous") == f"releases/{SHA_B}"
    assert f'Environment="RIHRP_RELEASE_SHA={SHA_A}"' in world.unit.read_text(encoding="utf-8")
    state = _json(world.release_root / "rollback-state.json")
    assert state["action"] == "rollback"
    assert state["target_sha"] == SHA_A
    assert state["previous_current"] == SHA_B
    assert state["previous_previous"] == SHA_A
    assert [call for call in ops.calls if call[0] in {"git_matches", "ci_success"}] == []


def test_rollback_requires_previous_release_to_match(tmp_path: Path) -> None:
    variants = [
        (
            "mismatched_previous",
            SHA_B,
            SHA_A,
            SHA_B,
            "rollback SHA must equal the current previous release",
        ),
        (
            "identical_pointers",
            SHA_A,
            SHA_A,
            SHA_A,
            "current and previous release pointers must differ",
        ),
    ]
    for label, current, previous, expect, fragment in variants:
        world = _world(tmp_path / label)
        _make_release(world, SHA_A)
        _make_release(world, SHA_B)
        _point(world, "current", current)
        _point(world, "previous", previous)
        ops = FakeOperations()
        _assert_rejected(
            functools.partial(
                release_activate.execute,
                world.config(expect, action="rollback"),
                operations=ops,
                now=NOW,
            ),
            fragment,
            label=label,
        )
        assert world.unit.read_bytes() == OLD_UNIT
        assert not (world.release_root / "rollback-state.json").exists()


def test_manifest_identity_must_match_declared_schema_sha_and_migration(
    tmp_path: Path,
) -> None:
    identity = "release manifest schema, SHA, or migration is invalid"
    variants = [
        ("schema", {"schema": 2}, None, identity),
        ("schema_type", {"schema": "1"}, None, identity),
        ("sha", {"sha": SHA_B}, None, identity),
        ("migration", {"migration": "0005_research_documents"}, None, identity),
        ("files_missing", None, "files", "release manifest file inventory is missing"),
        ("files_not_object", {"files": []}, None, "release manifest file inventory is missing"),
    ]
    for label, patch, drop, fragment in variants:
        world = _world(tmp_path / label)
        release = _make_release(world, SHA_A)
        document = _json(release / "manifest.json")
        if patch is not None:
            document.update(patch)
        if drop is not None:
            del document[drop]
        _dump_json(release / "manifest.json", document)
        _assert_rejected(
            functools.partial(release_activate._load_release, world.config(SHA_A)),
            fragment,
            label=label,
        )


def test_manifest_inventory_must_match_release_bytes_except_python_cache(
    tmp_path: Path,
) -> None:
    world = _world(tmp_path)
    release = _make_release(world, SHA_A)
    config = world.config(SHA_A)

    cache = release / "apps/api/__pycache__"
    cache.mkdir()
    (cache / "main.cpython-312.pyc").write_bytes(b"cache")
    (release / "apps/api/legacy.pyc").write_bytes(b"cache")
    release_activate._load_release(config)

    (release / "apps/api/rihrp/extra.py").write_bytes(b"# extra\n")
    _assert_rejected(
        functools.partial(release_activate._load_release, config),
        "release manifest inventory does not match release files",
        label="extra_file",
    )
    (release / "apps/api/rihrp/extra.py").unlink()
    with (release / "uv.lock").open("ab") as stream:
        stream.write(b"# tampered\n")
    _assert_rejected(
        functools.partial(release_activate._load_release, config),
        "release manifest inventory does not match release files",
        label="tampered_required_file",
    )


def test_manifest_json_rejects_unsafe_or_invalid_inventory_entries(tmp_path: Path) -> None:
    inventory_invalid = "release manifest file inventory is invalid"
    for label, key in (
        ("traversal", "../apps/api/evil.py"),
        ("absolute", "/apps/api/evil.py"),
        ("backslash", "apps\\api\\evil.py"),
        ("dot_segment", "apps/api/../evil.py"),
        ("empty", ""),
    ):
        world = _world(tmp_path / f"key-{label}")
        release = _make_release(world, SHA_A)
        document = _json(release / "manifest.json")
        files = dict(document["files"])  # type: ignore[arg-type]
        files[key] = "0" * 64
        document["files"] = files
        _dump_json(release / "manifest.json", document)
        _assert_rejected(
            functools.partial(release_activate._load_release, world.config(SHA_A)),
            inventory_invalid,
            label=label,
        )

    for label, digest in (
        ("uppercase", "A" * 64),
        ("short", "0" * 63),
        ("not_string", 5),
    ):
        world = _world(tmp_path / f"digest-{label}")
        release = _make_release(world, SHA_A)
        document = _json(release / "manifest.json")
        files = dict(document["files"])  # type: ignore[arg-type]
        files["uv.lock"] = digest
        document["files"] = files
        _dump_json(release / "manifest.json", document)
        _assert_rejected(
            functools.partial(release_activate._load_release, world.config(SHA_A)),
            inventory_invalid,
            label=label,
        )

    linked = _world(tmp_path / "linked")
    release = _make_release(linked, SHA_A)
    (release / "manifest.json").rename(release / "manifest.real")
    (release / "manifest.json").symlink_to(release / "manifest.real")
    _assert_rejected(
        functools.partial(release_activate._load_release, linked.config(SHA_A)),
        "release manifest is missing or is a symlink",
        label="symlink",
    )

    duplicated = _world(tmp_path / "duplicated")
    release = _make_release(duplicated, SHA_A)
    raw = (release / "manifest.json").read_text(encoding="utf-8")
    (release / "manifest.json").write_text(raw[:-1] + ', "schema": 1}', encoding="utf-8")
    _assert_rejected(
        functools.partial(release_activate._load_release, duplicated.config(SHA_A)),
        "required JSON file is invalid",
        label="duplicate_key",
    )

    not_object = _world(tmp_path / "not-object")
    release = _make_release(not_object, SHA_A)
    (release / "manifest.json").write_text("[]", encoding="utf-8")
    _assert_rejected(
        functools.partial(release_activate._load_release, not_object.config(SHA_A)),
        "required JSON file must contain an object",
        label="not_object",
    )


def test_config_and_directory_validation_is_fail_closed(tmp_path: Path) -> None:
    world = _world(tmp_path / "base")
    _make_release(world, SHA_A)
    config = world.config(SHA_A)

    _assert_rejected(
        functools.partial(
            release_activate._validate_config_paths,
            replace(config, release_root=Path("relative-root")),
        ),
        "all release paths must be absolute",
        label="relative_path",
    )
    _assert_rejected(
        functools.partial(
            release_activate._validate_config_paths,
            replace(config, action="deploy"),
        ),
        "action must be activate or rollback",
        label="action",
    )
    _assert_rejected(
        functools.partial(
            release_activate._validate_config_paths,
            replace(config, unit_path=tmp_path / "absent" / "rihrp.service"),
        ),
        "systemd user unit directory is unavailable",
        label="unit_directory",
    )
    _assert_rejected(
        functools.partial(
            release_activate._validate_config_paths,
            replace(config, expect_sha="A" * 40),
        ),
        "expected SHA must be 40 lowercase hexadecimal characters",
        error=argparse.ArgumentTypeError,
        label="sha_case",
    )

    release_mode = _world(tmp_path / "release-mode")
    release = _make_release(release_mode, SHA_A)
    release.chmod(0o775)
    _assert_rejected(
        functools.partial(release_activate._load_release, release_mode.config(SHA_A)),
        "release target has unsafe ownership or permissions",
        label="release_mode",
    )

    releases_mode = _world(tmp_path / "releases-mode")
    _make_release(releases_mode, SHA_A)
    releases_mode.releases.chmod(0o775)
    _assert_rejected(
        functools.partial(release_activate._load_release, releases_mode.config(SHA_A)),
        "releases directory has unsafe ownership or permissions",
        label="releases_mode",
    )

    real = _world(tmp_path / "root-real")
    _make_release(real, SHA_A)
    linked_root = tmp_path / "root-link"
    linked_root.symlink_to(real.release_root)
    _assert_rejected(
        functools.partial(
            release_activate._load_release,
            replace(real.config(SHA_A), release_root=linked_root),
        ),
        "release root must be a directory, not a symlink",
        label="root_symlink",
    )


def test_release_pointers_must_be_canonical_relative_symlinks(tmp_path: Path) -> None:
    orphan = _world(tmp_path / "orphan")
    _make_release(orphan, SHA_A)
    _point(orphan, "previous", SHA_A)
    _assert_rejected(
        functools.partial(release_activate._inspect_topology, orphan.config(SHA_A)),
        "previous exists without a current release pointer",
        label="orphan_previous",
    )

    regular = _world(tmp_path / "regular")
    _make_release(regular, SHA_A)
    (regular.release_root / "current").write_text(f"releases/{SHA_A}", encoding="utf-8")
    _assert_rejected(
        functools.partial(
            release_activate._release_link,
            regular.config(SHA_A),
            "current",
        ),
        "current path must be a relative release symlink",
        label="regular_file",
    )

    absolute = _world(tmp_path / "absolute")
    _make_release(absolute, SHA_A)
    (absolute.release_root / "current").symlink_to(absolute.releases / SHA_A)
    _assert_rejected(
        functools.partial(
            release_activate._release_link,
            absolute.config(SHA_A),
            "current",
        ),
        "current release pointer escapes the release root",
        label="absolute_link",
    )

    traversal = _world(tmp_path / "traversal")
    _make_release(traversal, SHA_A)
    (traversal.release_root / "current").symlink_to(f"releases/../releases/{SHA_A}")
    _assert_rejected(
        functools.partial(
            release_activate._release_link,
            traversal.config(SHA_A),
            "current",
        ),
        "current release pointer is not a canonical relative path",
        label="traversal_link",
    )


def test_environment_file_must_be_owner_controlled_0600(tmp_path: Path) -> None:
    message = "environment file must be an owner-controlled regular file with mode 0600"

    mode = _world(tmp_path / "mode")
    mode.env_file.chmod(0o644)
    _assert_rejected(
        functools.partial(release_activate._validate_env_file, mode.env_file),
        message,
        label="mode",
    )

    linked = _world(tmp_path / "linked")
    target = linked.env_file.with_name("rihrp.conf.real")
    linked.env_file.rename(target)
    linked.env_file.symlink_to(target)
    _assert_rejected(
        functools.partial(release_activate._validate_env_file, linked.env_file),
        message,
        label="symlink",
    )

    missing = _world(tmp_path / "missing")
    missing.env_file.unlink()
    _assert_rejected(
        functools.partial(release_activate._validate_env_file, missing.env_file),
        "environment file is unavailable",
        label="missing",
    )


def test_service_unit_must_be_regular_owned_and_not_group_writable(tmp_path: Path) -> None:
    linked = _world(tmp_path / "linked")
    target = linked.unit.with_name("rihrp.service.real")
    linked.unit.rename(target)
    linked.unit.symlink_to(target)
    _assert_rejected(
        functools.partial(release_activate._read_unit, linked.unit),
        "service unit must be a regular file, not a symlink",
        label="symlink",
    )

    mode = _world(tmp_path / "mode")
    mode.unit.chmod(0o664)
    _assert_rejected(
        functools.partial(release_activate._read_unit, mode.unit),
        "service unit has unsafe ownership or permissions",
        label="mode",
    )


@pytest.mark.skipif(shutil.which("systemd-analyze") is None, reason="systemd-analyze unavailable")
def test_generated_unit_syntax_with_real_systemd_parser(tmp_path):
    world = _world(tmp_path)
    path = _make_release(world, SHA_B)
    unit = tmp_path / "verify" / "rihrp.service"
    unit.parent.mkdir()
    release = release_activate._load_release(world.config(SHA_B))
    unit.write_text(release_activate._unit_text(release, world.env_file))
    assert path.is_dir()
    result = subprocess.run(  # noqa: S603 - local systemd parser, no unit installation
        ["systemd-analyze", "--user", "verify", str(unit)],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_ci_query_is_pinned_and_routing_environment_removed(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_DIR", "/other/.git")
    monkeypatch.setenv("GH_REPO", "other/repo")
    monkeypatch.setenv("GH_HOST", "other.invalid")
    captured = {}

    def fake(args, **kwargs):
        captured.update(args=args, env=kwargs["env"])
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "headSha": SHA_A,
                        "status": "completed",
                        "conclusion": "success",
                        "workflowName": "CI",
                    }
                ]
            ),
        )

    monkeypatch.setattr(release_activate.subprocess, "run", fake)
    assert release_activate._ci_success(tmp_path, SHA_A)
    args = captured["args"]
    assert args[args.index("--repo") + 1] == "Kensan196948G/RIHRP-Research-Studio"
    assert args[args.index("--branch") + 1] == "main"
    assert args[args.index("--event") + 1] == "push"
    assert not {"GIT_DIR", "GH_REPO", "GH_HOST"} & set(captured["env"])


def test_completion_journal_failure_does_not_trigger_second_transition(tmp_path, monkeypatch):
    world = _world(tmp_path)
    _make_release(world, SHA_B)
    ops = FakeOperations()

    def fail(_config, _status):
        raise release_activate.ActivationError("completion durability failed")

    monkeypatch.setattr(release_activate, "_finish_transition", fail)
    with pytest.raises(release_activate.ActivationError, match="release is healthy"):
        release_activate.execute(world.config(SHA_B), operations=ops, now=NOW)
    assert [call for call in ops.calls if call[0] == "systemctl"] == [
        ("systemctl", "daemon-reload"),
        ("systemctl", "restart"),
    ]
    assert os.readlink(world.release_root / "current") == f"releases/{SHA_B}"


def test_pending_durability_failure_stops_before_unit_changes(tmp_path, monkeypatch):
    world = _world(tmp_path)
    _make_release(world, SHA_B)
    old_unit = world.unit.read_bytes()
    ops = FakeOperations()

    def fail(_path):
        raise release_activate.ActivationError("state directory durability check failed")

    monkeypatch.setattr(release_activate, "_fsync_directory", fail)
    with pytest.raises(release_activate.ActivationError, match="durability"):
        release_activate.execute(world.config(SHA_B), operations=ops, now=NOW)
    assert world.unit.read_bytes() == old_unit
    assert not (world.release_root / "current").exists()
    assert not any(call[0] == "systemctl" for call in ops.calls)


def test_special_unit_permission_bits_rejected(tmp_path):
    world = _world(tmp_path)
    world.unit.chmod(0o4644)
    with pytest.raises(release_activate.ActivationError, match="unsafe ownership"):
        release_activate._read_unit(world.unit)


def test_failed_manual_rollback_does_not_retry(tmp_path):
    world = _world(tmp_path)
    _make_release(world, SHA_A)
    _make_release(world, SHA_B)
    _point(world, "current", SHA_B)
    _point(world, "previous", SHA_A)
    ops = FakeOperations(healthy=False)
    with pytest.raises(release_activate.ActivationError, match="automatic retry is disabled"):
        release_activate.execute(world.config(SHA_A, "rollback"), operations=ops, now=NOW)
    assert [call for call in ops.calls if call[0] == "systemctl"] == [
        ("systemctl", "daemon-reload"),
        ("systemctl", "restart"),
    ]
    assert (world.release_root / "transition-pending.json").exists()


def test_interrupted_transition_blocks_retry_and_preserves_files(tmp_path):
    world = _world(tmp_path)
    _make_release(world, SHA_B)
    pending = world.release_root / "transition-pending.json"
    _dump_json(pending, {"schema": 1, "target_sha": SHA_B})
    old = world.unit.read_bytes()
    with pytest.raises(release_activate.ActivationError, match="interrupted transition"):
        release_activate.execute(world.config(SHA_B), operations=FakeOperations(), now=NOW)
    assert world.unit.read_bytes() == old
    assert pending.exists()


def test_backup_requires_latest_fresh_intact_backup_and_restore_evidence(
    tmp_path: Path,
) -> None:
    valid = _world(tmp_path / "valid")
    release_activate._validate_backup(valid.config(SHA_A), NOW)

    stale = _world(tmp_path / "stale")
    stale_document = _json(stale.backup_manifest)
    stale_document["created_at"] = (NOW - timedelta(hours=25)).isoformat()
    _dump_json(stale.backup_manifest, stale_document)
    _assert_rejected(
        functools.partial(release_activate._validate_backup, stale.config(SHA_A), NOW),
        "production backup manifest is invalid or stale",
        label="stale",
    )

    older = _world(tmp_path / "older")
    _write_backup(older.backup_dir, created_at=NOW - timedelta(minutes=30), name=NEWER_DUMP_NAME)
    _assert_rejected(
        functools.partial(release_activate._validate_backup, older.config(SHA_A), NOW),
        "backup manifest is not the latest production backup",
        label="not_latest",
    )

    tampered = _world(tmp_path / "tampered")
    dump = tampered.backup_dir / DUMP_NAME
    with dump.open("ab") as stream:
        stream.write(b"tampered")
    _assert_rejected(
        functools.partial(release_activate._validate_backup, tampered.config(SHA_A), NOW),
        "production backup SHA-256 verification failed",
        label="digest",
    )

    sidecar = _world(tmp_path / "sidecar")
    (sidecar.backup_dir / f"{DUMP_NAME}.sha256").write_text(
        f"{'0' * 64}  other-name.dump\n",
        encoding="utf-8",
    )
    _assert_rejected(
        functools.partial(release_activate._validate_backup, sidecar.config(SHA_A), NOW),
        "production backup SHA-256 verification failed",
        label="sidecar",
    )

    evidence = _world(tmp_path / "evidence")
    _write_evidence(evidence.restore_evidence, digest="0" * 64)
    _assert_rejected(
        functools.partial(release_activate._validate_backup, evidence.config(SHA_A), NOW),
        "restore evidence does not match the fresh production backup",
        label="evidence",
    )

    dump_name = _world(tmp_path / "dump-name")
    dump_document = _json(dump_name.backup_manifest)
    dump_document["dump"] = "../rihrp_production-escape.dump"
    _dump_json(dump_name.backup_manifest, dump_document)
    _assert_rejected(
        functools.partial(release_activate._validate_backup, dump_name.config(SHA_A), NOW),
        "production backup manifest is invalid or stale",
        label="dump_name",
    )
