from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

import pytest
from tools import release_preflight

DUMP_NAME: Final = "rihrp_production-20261103T120000000000-123.dump"
OLD_DUMP_NAME: Final = "rihrp_production-20261102T120000000000-122.dump"


@dataclass(frozen=True, slots=True)
class BackupSpec:
    created_at: datetime
    dump_name: str = DUMP_NAME
    payload: bytes = b"backup fixture payload\n"
    migration: str = release_preflight.EXPECTED_MIGRATION
    digest: str | None = None
    sidecar_digest: str | None = None
    counts: dict[str, int] = field(
        default_factory=lambda: dict.fromkeys(release_preflight.TABLES, 0)
    )


def _git(repo: Path, *args: str) -> str:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Preflight Test",
            "GIT_AUTHOR_EMAIL": "preflight@example.invalid",
            "GIT_COMMITTER_NAME": "Preflight Test",
            "GIT_COMMITTER_EMAIL": "preflight@example.invalid",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        }
    )
    result = subprocess.run(  # noqa: S603 - isolated fixture repo, no shell
        ["git", "-C", str(repo), *args],  # noqa: S607
        check=True,
        capture_output=True,
        encoding="utf-8",
        env=env,
    )
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    (repository / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-m", "initial")
    sha = _git(repository, "rev-parse", "HEAD")
    _git(repository, "update-ref", "refs/remotes/origin/main", sha)
    return repository, sha


@pytest.fixture
def backups(tmp_path: Path) -> Path:
    directory = tmp_path / "backups"
    directory.mkdir()
    return directory


def _write_backup(backups: Path, spec: BackupSpec) -> Path:
    dump = backups / spec.dump_name
    dump.write_bytes(spec.payload)
    digest = spec.digest or hashlib.sha256(spec.payload).hexdigest()
    (backups / f"{spec.dump_name}.sha256").write_text(
        f"{spec.sidecar_digest or digest}  {spec.dump_name}\n",
        encoding="utf-8",
    )
    manifest = backups / f"{spec.dump_name}.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "db": release_preflight.TARGET_DB,
                "dump": spec.dump_name,
                "sha256": digest,
                "migration": spec.migration,
                "created_at": spec.created_at.isoformat(),
                "counts": spec.counts,
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _config(repo: tuple[Path, str], backups: Path) -> release_preflight.PreflightConfig:
    repository, sha = repo
    return release_preflight.PreflightConfig(
        expect_sha=sha,
        repo=repository,
        backup_dir=backups,
    )


def _check(report: release_preflight.Report, name: str) -> release_preflight.Check:
    return next(check for check in report["checks"] if check["name"] == name)


def _rewrite_manifest(path: Path, **changes: object) -> None:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.update(changes)
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_cli_success_uses_isolated_clean_repo_and_production_manifest(
    repo: tuple[Path, str],
    backups: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_backup(backups, BackupSpec(created_at=datetime.now(UTC) - timedelta(hours=1)))
    repository, sha = repo

    status = release_preflight.main(
        [
            "--expect-sha",
            sha,
            "--repo",
            str(repository),
            "--backup-dir",
            str(backups),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert status == 0
    assert output["ok"] is True
    assert all(check["ok"] for check in output["checks"])
    assert {check["name"] for check in output["checks"]} == {
        "git_head",
        "origin_main",
        "worktree_clean",
        "latest_manifest",
        "backup_freshness",
        "dump_file",
        "sha256",
        "table_counts",
        "migration",
    }


@pytest.mark.parametrize("bad_sha", ["f" * 39, "F" * 40, "g" * 40])
def test_cli_rejects_invalid_expected_sha(
    bad_sha: str,
    backups: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        release_preflight.main(["--expect-sha", bad_sha, "--backup-dir", str(backups)])

    assert excinfo.value.code == 2
    assert capsys.readouterr().out == ""


def test_head_mismatch_fails(
    repo: tuple[Path, str],
    backups: Path,
) -> None:
    _write_backup(backups, BackupSpec(created_at=datetime.now(UTC)))
    report = release_preflight.run_preflight(
        replace(_config(repo, backups), expect_sha="f" * 40),
        datetime.now(UTC),
    )

    assert report["ok"] is False
    assert _check(report, "git_head")["ok"] is False


def test_origin_main_mismatch_fails(
    repo: tuple[Path, str],
    backups: Path,
) -> None:
    repository, _ = repo
    _write_backup(backups, BackupSpec(created_at=datetime.now(UTC)))
    (repository / "README.md").write_text("second\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-m", "second")
    new_sha = _git(repository, "rev-parse", "HEAD")
    _git(repository, "update-ref", "refs/remotes/origin/main", new_sha)
    _git(repository, "update-ref", "refs/remotes/origin/main", repo[1])

    report = release_preflight.run_preflight(
        release_preflight.PreflightConfig(
            expect_sha=new_sha,
            repo=repository,
            backup_dir=backups,
        ),
        datetime.now(UTC),
    )

    assert _check(report, "git_head")["ok"] is True
    assert _check(report, "origin_main")["ok"] is False


@pytest.mark.parametrize("dirty_kind", ["tracked", "untracked"])
def test_dirty_worktree_fails(
    dirty_kind: str,
    repo: tuple[Path, str],
    backups: Path,
) -> None:
    repository, _ = repo
    _write_backup(backups, BackupSpec(created_at=datetime.now(UTC)))
    if dirty_kind == "tracked":
        (repository / "README.md").write_text("changed\n", encoding="utf-8")
    else:
        (repository / "new.txt").write_text("new\n", encoding="utf-8")

    report = release_preflight.run_preflight(_config(repo, backups), datetime.now(UTC))

    assert report["ok"] is False
    assert _check(report, "worktree_clean")["ok"] is False


def test_stale_backup_fails(
    repo: tuple[Path, str],
    backups: Path,
) -> None:
    now = datetime.now(UTC)
    _write_backup(backups, BackupSpec(created_at=now - timedelta(hours=37)))

    report = release_preflight.run_preflight(_config(repo, backups), now)

    assert report["ok"] is False
    assert _check(report, "backup_freshness")["ok"] is False


def test_future_backup_fails(
    repo: tuple[Path, str],
    backups: Path,
) -> None:
    now = datetime.now(UTC)
    _write_backup(backups, BackupSpec(created_at=now + timedelta(minutes=6)))

    report = release_preflight.run_preflight(_config(repo, backups), now)

    assert report["ok"] is False
    assert _check(report, "backup_freshness")["ok"] is False


def test_naive_created_at_fails_closed(
    repo: tuple[Path, str],
    backups: Path,
) -> None:
    manifest = _write_backup(backups, BackupSpec(created_at=datetime.now(UTC)))
    _rewrite_manifest(manifest, created_at="2026-11-03T12:00:00")

    report = release_preflight.run_preflight(_config(repo, backups), datetime.now(UTC))

    assert report["ok"] is False
    assert _check(report, "latest_manifest")["ok"] is False


def test_digest_mismatch_fails(
    repo: tuple[Path, str],
    backups: Path,
) -> None:
    _write_backup(
        backups,
        BackupSpec(created_at=datetime.now(UTC), digest="0" * 64),
    )

    report = release_preflight.run_preflight(_config(repo, backups), datetime.now(UTC))

    assert report["ok"] is False
    assert _check(report, "sha256")["ok"] is False


def test_tampered_dump_fails_without_exposing_content(
    repo: tuple[Path, str],
    backups: Path,
) -> None:
    secret_marker = "do-not-print-this-file-body"
    _write_backup(backups, BackupSpec(created_at=datetime.now(UTC), payload=secret_marker.encode()))
    (backups / DUMP_NAME).write_text("tampered", encoding="utf-8")

    report = release_preflight.run_preflight(_config(repo, backups), datetime.now(UTC))
    rendered = json.dumps(report)

    assert _check(report, "sha256")["ok"] is False
    assert secret_marker not in rendered
    assert "tampered" not in rendered


@pytest.mark.parametrize("missing_table", ["research_documents", "audit_events"])
def test_missing_count_fails(
    missing_table: str,
    repo: tuple[Path, str],
    backups: Path,
) -> None:
    counts = dict.fromkeys(release_preflight.TABLES, 0)
    del counts[missing_table]
    _write_backup(
        backups,
        BackupSpec(created_at=datetime.now(UTC), counts=counts),
    )

    report = release_preflight.run_preflight(_config(repo, backups), datetime.now(UTC))

    assert report["ok"] is False
    assert _check(report, "table_counts")["ok"] is False


def test_boolean_count_fails(
    repo: tuple[Path, str],
    backups: Path,
) -> None:
    counts = dict.fromkeys(release_preflight.TABLES, 0)
    counts["users"] = True
    _write_backup(
        backups,
        BackupSpec(created_at=datetime.now(UTC), counts=counts),
    )

    report = release_preflight.run_preflight(_config(repo, backups), datetime.now(UTC))

    assert report["ok"] is False
    assert _check(report, "table_counts")["ok"] is False


def test_wrong_migration_fails(
    repo: tuple[Path, str],
    backups: Path,
) -> None:
    _write_backup(
        backups,
        BackupSpec(created_at=datetime.now(UTC), migration="0003_audit_truncate"),
    )

    report = release_preflight.run_preflight(_config(repo, backups), datetime.now(UTC))

    assert report["ok"] is False
    assert _check(report, "migration")["ok"] is False


def test_unsafe_dump_name_fails(
    repo: tuple[Path, str],
    backups: Path,
) -> None:
    manifest = _write_backup(backups, BackupSpec(created_at=datetime.now(UTC)))
    _rewrite_manifest(manifest, dump="../rihrp_production-escape.dump")

    report = release_preflight.run_preflight(_config(repo, backups), datetime.now(UTC))

    assert report["ok"] is False
    assert _check(report, "dump_file")["ok"] is False


@pytest.mark.parametrize("artifact", ["manifest", "dump", "checksum"])
def test_symlinked_artifact_fails(
    artifact: str,
    repo: tuple[Path, str],
    backups: Path,
) -> None:
    manifest = _write_backup(backups, BackupSpec(created_at=datetime.now(UTC)))
    target = backups / f"{artifact}.target"
    if artifact == "manifest":
        source = manifest
    elif artifact == "dump":
        source = backups / DUMP_NAME
    else:
        source = backups / f"{DUMP_NAME}.sha256"
    source.rename(target)
    source.symlink_to(target)

    report = release_preflight.run_preflight(_config(repo, backups), datetime.now(UTC))

    assert report["ok"] is False


def test_tampered_latest_manifest_does_not_fall_back(
    repo: tuple[Path, str],
    backups: Path,
) -> None:
    now = datetime.now(UTC)
    _write_backup(
        backups,
        BackupSpec(created_at=now - timedelta(hours=2)),
    )
    latest = _write_backup(
        backups,
        replace(
            BackupSpec(created_at=now - timedelta(hours=1)),
            dump_name=OLD_DUMP_NAME,
        ),
    )
    _rewrite_manifest(latest, sha256="0" * 64)

    report = release_preflight.run_preflight(_config(repo, backups), now)

    assert _check(report, "latest_manifest")["ok"] is True
    assert _check(report, "sha256")["ok"] is False


def test_mislabeled_production_manifest_fails_closed(
    repo: tuple[Path, str],
    backups: Path,
) -> None:
    manifest = _write_backup(backups, BackupSpec(created_at=datetime.now(UTC)))
    _rewrite_manifest(manifest, db="rihrp_test")

    report = release_preflight.run_preflight(_config(repo, backups), datetime.now(UTC))

    assert report["ok"] is False
    assert _check(report, "latest_manifest")["ok"] is False


def test_production_db_mismatch_does_not_fall_back(repo, backups):
    now = datetime.now(UTC)
    _write_backup(backups, BackupSpec(created_at=now - timedelta(hours=2)))
    latest = _write_backup(backups, BackupSpec(created_at=now, dump_name=OLD_DUMP_NAME))
    _rewrite_manifest(latest, db="rihrp_test")
    report = release_preflight.run_preflight(_config(repo, backups), now)
    assert report["ok"] is False
    assert _check(report, "latest_manifest")["ok"] is False


def test_git_routing_environment_is_ignored(repo, backups, tmp_path, monkeypatch):
    now = datetime.now(UTC)
    _write_backup(backups, BackupSpec(created_at=now))
    other = tmp_path / "other"
    other.mkdir()
    _git(other, "init", "-b", "main")
    (other / "data").write_text("other")
    _git(other, "add", "data")
    _git(other, "commit", "-m", "other")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    report = release_preflight.run_preflight(_config(repo, backups), now)
    assert report["ok"] is True


@pytest.mark.parametrize("value", [-1, 10**100])
def test_count_outside_bigint_fails(repo, backups, value):
    counts = dict.fromkeys(release_preflight.TABLES, 0)
    counts["users"] = value
    _write_backup(backups, BackupSpec(created_at=datetime.now(UTC), counts=counts))
    report = release_preflight.run_preflight(_config(repo, backups), datetime.now(UTC))
    assert report["ok"] is False


@pytest.mark.parametrize(
    "body", ["[" * 5000 + "]" * 5000, '{"n":' + "1" * 10000 + "}", "x" * 65537]
)
def test_extreme_json_fails_without_traceback(repo, backups, body):
    manifest = _write_backup(backups, BackupSpec(created_at=datetime.now(UTC)))
    manifest.write_text(body)
    report = release_preflight.run_preflight(_config(repo, backups), datetime.now(UTC))
    assert report["ok"] is False


def test_extreme_max_age_rejected(backups):
    with pytest.raises(SystemExit) as excinfo:
        release_preflight.main(
            ["--expect-sha", "a" * 40, "--backup-dir", str(backups), "--max-age-hours", "1e308"]
        )
    assert excinfo.value.code == 2


def test_help_is_available(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        release_preflight.main(["--help"])

    assert excinfo.value.code == 0
    assert "--expect-sha" in capsys.readouterr().out
