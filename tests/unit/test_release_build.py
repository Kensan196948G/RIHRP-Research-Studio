"""Unit tests for the immutable release builder.

The builder is exercised with temporary files and a fake runner only. No git,
network, package manager, compiler, database, or service is invoked.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import stat
import sys
import tarfile
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from tools import release_build

SHA = "a" * 40
OTHER_SHA = "b" * 40
MIGRATION = "0004_research_documents"
BUILT_AT = datetime(2026, 11, 3, 12, 0, 0, tzinfo=UTC)
BUILT_AT_TEXT = "2026-11-03T12:00:00.000000Z"


def _write(path: Path, payload: bytes = b"fixture\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class Entry:
    name: str
    payload: bytes = b""
    kind: bytes = tarfile.REGTYPE
    linkname: str = ""


def _archive(*entries: Entry) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for entry in entries:
            info = tarfile.TarInfo(entry.name)
            info.type = entry.kind
            info.linkname = entry.linkname
            if entry.kind == tarfile.REGTYPE:
                info.size = len(entry.payload)
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(entry.payload))
            else:
                info.mode = 0o755 if entry.kind == tarfile.DIRTYPE else 0o644
                archive.addfile(info)
    return buffer.getvalue()


def _valid_entries() -> list[Entry]:
    return [
        Entry("uv.lock", b"lock\n"),
        Entry("requirements-production.txt", b"fastapi==0.115\n"),
        Entry("pyproject.toml", b'[project]\nname = "rihrp"\n'),
        Entry("apps/web/package.json", b"{}\n"),
        Entry("apps/web/package-lock.json", b"{}\n"),
        Entry("apps/api/rihrp/main.py", b"app = object()\n"),
        Entry(
            "infra/migrations/versions/0004_research_documents.py",
            b"revision = '0004_research_documents'\n",
        ),
    ]


@pytest.fixture
def release_tree(tmp_path: Path) -> Path:
    release = tmp_path / "release"
    _write(release / "uv.lock", b"lock\n")
    _write(release / "requirements-production.txt", b"fastapi==0.115\n")
    _write(release / "pyproject.toml", b'[project]\nname = "rihrp"\n')
    _write(release / "apps/web/package-lock.json", b"{}\n")
    _write(release / "apps/web/package.json", b"{}\n")
    _write(release / "apps/api/rihrp/main.py", b"app = object()\n")
    _write(release / "apps/api/__pycache__/main.cpython-312.pyc", b"cache\n")
    _write(
        release / "infra/migrations/versions/0004_research_documents.py",
        b"revision = '0004_research_documents'\n",
    )
    _write(release / "infra/migrations/__pycache__/0004.cpython-312.pyc", b"cache\n")
    _write(release / "apps/web/dist/index.html", b"<html>release</html>\n")
    _write(release / "apps/web/dist/assets/app.js", b"console.log('release');\n")
    return release


def test_validate_source_archive_accepts_required_files_and_trees() -> None:
    entries = _valid_entries()

    names = release_build.validate_source_archive(_archive(*entries))

    assert names == tuple(entry.name for entry in entries)


@pytest.mark.parametrize(
    "name",
    [
        "../escape.txt",
        "/absolute.txt",
        "apps/api/../../escape.txt",
        "apps\\api\\main.py",
    ],
)
def test_validate_source_archive_rejects_unsafe_paths(name: str) -> None:
    entries = [*_valid_entries(), Entry(name, b"escape\n")]

    with pytest.raises(release_build.BuildError, match="unsafe path"):
        release_build.validate_source_archive(_archive(*entries))


@pytest.mark.parametrize(
    "name",
    [".env", "apps/web/.env", ".env.local", "infra/.env.production"],
)
def test_validate_source_archive_rejects_environment_files(name: str) -> None:
    entries = [*_valid_entries(), Entry(name, b"SECRET=value\n")]

    with pytest.raises(release_build.BuildError, match="forbidden environment file"):
        release_build.validate_source_archive(_archive(*entries))


def test_validate_source_archive_allows_env_example() -> None:
    entries = [*_valid_entries(), Entry(".env.example", b"KEY=\n")]

    names = release_build.validate_source_archive(_archive(*entries))

    assert ".env.example" in names


def test_validate_source_archive_reserves_the_manifest_path() -> None:
    entries = [*_valid_entries(), Entry("manifest.json", b"{}\n")]

    with pytest.raises(release_build.BuildError, match="reserves the release manifest"):
        release_build.validate_source_archive(_archive(*entries))


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE])
def test_validate_source_archive_rejects_links(kind: bytes) -> None:
    entries = [
        *_valid_entries(),
        Entry("apps/api/link", kind=kind, linkname="outside-target"),
    ]

    with pytest.raises(release_build.BuildError, match="must not contain links"):
        release_build.validate_source_archive(_archive(*entries))


def test_validate_source_archive_rejects_special_files() -> None:
    entries = [*_valid_entries(), Entry("apps/api/pipe", kind=tarfile.FIFOTYPE)]

    with pytest.raises(release_build.BuildError, match="non-regular entry"):
        release_build.validate_source_archive(_archive(*entries))


def test_validate_source_archive_rejects_duplicate_paths() -> None:
    entries = [*_valid_entries(), Entry("uv.lock", b"second\n")]

    with pytest.raises(release_build.BuildError, match="duplicate paths"):
        release_build.validate_source_archive(_archive(*entries))


@pytest.mark.parametrize(
    ("missing", "message"),
    [
        ("pyproject.toml", "missing required files"),
        ("apps/api/rihrp/main.py", "missing the API tree"),
        ("infra/migrations/versions/0004_research_documents.py", "missing the migrations tree"),
    ],
)
def test_validate_source_archive_rejects_incomplete_tree(missing: str, message: str) -> None:
    entries = [entry for entry in _valid_entries() if entry.name != missing]

    with pytest.raises(release_build.BuildError, match=message):
        release_build.validate_source_archive(_archive(*entries))


@pytest.mark.parametrize("data", [b"", b"not a tar archive", b"\x1f\x8b\x08\x00"])
def test_validate_source_archive_rejects_invalid_archives(data: bytes) -> None:
    with pytest.raises(release_build.BuildError, match="source archive is invalid"):
        release_build.validate_source_archive(data)


def test_extract_source_archive_writes_valid_members(tmp_path: Path) -> None:
    release = tmp_path / "release"
    release.mkdir()

    release_build.extract_source_archive(_archive(*_valid_entries()), release)

    assert (release / "uv.lock").read_bytes() == b"lock\n"
    assert (release / "apps/api/rihrp/main.py").read_bytes() == b"app = object()\n"


def test_extract_source_archive_rejects_traversal_before_writing(tmp_path: Path) -> None:
    release = tmp_path / "release"
    release.mkdir()
    entries = [*_valid_entries(), Entry("../escaped.txt", b"escaped\n")]

    with pytest.raises(release_build.BuildError, match="unsafe path"):
        release_build.extract_source_archive(_archive(*entries), release)

    assert not (tmp_path / "escaped.txt").exists()
    assert not (release / "uv.lock").exists()


def test_extract_source_archive_rejects_links_before_writing(tmp_path: Path) -> None:
    release = tmp_path / "release"
    release.mkdir()
    entries = [
        *_valid_entries(),
        Entry("apps/api/linked-file", kind=tarfile.SYMTYPE, linkname="outside-target"),
    ]

    with pytest.raises(release_build.BuildError, match="must not contain links"):
        release_build.extract_source_archive(_archive(*entries), release)

    assert not (release / "apps/api/linked-file").exists()


def test_collect_manifest_files_hashes_required_and_tree_files(release_tree: Path) -> None:
    files = release_build.collect_manifest_files(release_tree)

    assert list(files) == sorted(files)
    assert files["uv.lock"] == _sha256(b"lock\n")
    assert files["apps/web/dist/index.html"] == _sha256(b"<html>release</html>\n")
    assert "apps/api/__pycache__/main.cpython-312.pyc" not in files
    assert "infra/migrations/__pycache__/0004.cpython-312.pyc" not in files


def test_collect_manifest_files_includes_python_cache_under_dist(release_tree: Path) -> None:
    _write(release_tree / "apps/web/dist/assets/legacy.pyc", b"cache\n")

    files = release_build.collect_manifest_files(release_tree)

    assert files["apps/web/dist/assets/legacy.pyc"] == _sha256(b"cache\n")


def test_collect_manifest_files_requires_a_regular_required_file(release_tree: Path) -> None:
    (release_tree / "uv.lock").unlink()

    with pytest.raises(release_build.BuildError, match="missing required regular file: uv.lock"):
        release_build.collect_manifest_files(release_tree)


def test_collect_manifest_files_rejects_symlinks_in_trees(
    release_tree: Path, tmp_path: Path
) -> None:
    outside = _write(tmp_path / "outside.txt", b"outside\n")
    (release_tree / "apps/api/rihrp/leak.py").symlink_to(outside)

    with pytest.raises(release_build.BuildError, match="symlink"):
        release_build.collect_manifest_files(release_tree)


def test_collect_manifest_files_rejects_empty_trees(release_tree: Path) -> None:
    dist = release_tree / "apps/web/dist"
    for path in sorted(dist.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()

    with pytest.raises(release_build.BuildError, match="empty: apps/web/dist"):
        release_build.collect_manifest_files(release_tree)


def test_collect_manifest_files_rejects_special_files(release_tree: Path) -> None:
    os.mkfifo(release_tree / "apps/api/pipe")

    with pytest.raises(release_build.BuildError, match="non-regular file"):
        release_build.collect_manifest_files(release_tree)


def test_collect_manifest_files_requires_real_tree_directories(release_tree: Path) -> None:
    shutil.rmtree(release_tree / "apps/web/dist")
    (release_tree / "apps/web/dist").write_text("not a directory\n", encoding="utf-8")

    with pytest.raises(release_build.BuildError, match="not a real directory: apps/web/dist"):
        release_build.collect_manifest_files(release_tree)


def test_create_manifest_records_schema_sha_migration_and_files(release_tree: Path) -> None:
    manifest = release_build.create_manifest(release_tree, SHA, BUILT_AT)

    assert manifest == {
        "schema": release_build.MANIFEST_SCHEMA,
        "sha": SHA,
        "migration": MIGRATION,
        "built_at": BUILT_AT_TEXT,
        "files": release_build.collect_manifest_files(release_tree),
    }


def test_create_manifest_normalizes_the_timestamp_to_utc(release_tree: Path) -> None:
    tokyo = timezone(timedelta(hours=9))
    built_at = datetime(2026, 11, 3, 21, 0, 0, tzinfo=tokyo)

    manifest = release_build.create_manifest(release_tree, SHA, built_at)

    assert manifest["built_at"] == BUILT_AT_TEXT


def test_create_manifest_rejects_naive_timestamps(release_tree: Path) -> None:
    with pytest.raises(release_build.BuildError, match="aware datetime"):
        release_build.create_manifest(release_tree, SHA, datetime(2026, 11, 3, 12, 0, 0))


@pytest.mark.parametrize("sha", ["", "a" * 39, "A" * 40, "g" * 40, "a" * 41])
def test_create_manifest_rejects_invalid_sha(release_tree: Path, sha: str) -> None:
    with pytest.raises(release_build.BuildError, match="40 lowercase hexadecimal"):
        release_build.create_manifest(release_tree, sha, BUILT_AT)


def test_write_manifest_is_compact_and_refuses_overwrite(tmp_path: Path) -> None:
    release = tmp_path / "release"
    release.mkdir()
    manifest: release_build.ReleaseManifest = {
        "schema": release_build.MANIFEST_SCHEMA,
        "sha": SHA,
        "migration": MIGRATION,
        "built_at": BUILT_AT_TEXT,
        "files": {},
    }

    path = release_build.write_manifest(release, manifest)

    raw = path.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert json.loads(raw) == manifest
    assert list(release.glob(".manifest.*.tmp")) == []
    with pytest.raises(release_build.BuildError, match="already exists"):
        release_build.write_manifest(release, manifest)


@dataclass
class FakeRunner:
    """A deterministic command runner that simulates git and build tools."""

    sha: str = SHA
    origin: str | None = None
    status: bytes = b""
    ci: bytes | None = None
    archive: bytes = b""
    fail: str | None = None
    manifest_path: Path | None = None
    calls: list[release_build.Command] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)
    manifest_seen: list[bool] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.ci is None:
            self.ci = json.dumps(
                [{"headSha": self.sha, "status": "completed", "conclusion": "success"}]
            ).encode()
        if not self.archive:
            self.archive = _archive(*_valid_entries())

    def _record(self, kind: str, command: release_build.Command) -> None:
        self.calls.append(command)
        self.kinds.append(kind)
        if self.manifest_path is not None:
            self.manifest_seen.append(self.manifest_path.exists())

    def __call__(self, command: release_build.Command) -> release_build.CommandResult:
        argv = command.argv
        if argv[0] == "git":
            arguments = argv[4:]
            if arguments == ("rev-parse", "--verify", "HEAD"):
                self._record("git-head", command)
                return release_build.CommandResult(0, (self.sha + "\n").encode())
            if arguments == ("rev-parse", "--verify", "refs/remotes/origin/main"):
                self._record("git-origin", command)
                return release_build.CommandResult(0, ((self.origin or self.sha) + "\n").encode())
            if arguments == ("status", "--porcelain=v1", "--untracked-files=all"):
                self._record("git-status", command)
                return release_build.CommandResult(0, self.status)
            if arguments == ("archive", "--format=tar", self.sha):
                self._record("git-archive", command)
                if self.fail == "archive":
                    return release_build.CommandResult(1)
                return release_build.CommandResult(0, self.archive)
            raise AssertionError(f"unexpected git command: {arguments}")
        if argv[0] == "gh":
            self._record("ci", command)
            if self.fail == "ci":
                return release_build.CommandResult(1)
            assert self.ci is not None
            return release_build.CommandResult(0, self.ci)
        if argv[0] == sys.executable and argv[1:3] == ("-m", "venv"):
            self._record("venv", command)
            if self.fail == "venv":
                return release_build.CommandResult(1)
            _write(Path(argv[-1]) / "bin/python", b"#!/bin/sh\n")
            return release_build.CommandResult(0)
        if argv[0] == "uv":
            self._record("uv", command)
            return release_build.CommandResult(1 if self.fail == "uv" else 0)
        if argv[0] == "npm" and argv[1:] == ("ci",):
            self._record("npm-ci", command)
            return release_build.CommandResult(1 if self.fail == "npm-ci" else 0)
        if argv[0] == "npm" and argv[1:] == ("run", "build"):
            self._record("npm-build", command)
            if self.fail == "npm-build":
                return release_build.CommandResult(1)
            dist = command.cwd / "dist"
            _write(dist / "index.html", b"<html>built</html>\n")
            _write(dist / "assets/app.js", b"console.log('built');\n")
            _write(dist / "assets/app.css", b"body{}\n")
            return release_build.CommandResult(0)
        raise AssertionError(f"unexpected command: {argv}")


def _repo_and_root(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo / "README.md", b"fixture\n")
    return repo, tmp_path / "release-root"


def _config(repo: Path, root: Path, sha: str = SHA) -> release_build.BuildConfig:
    return release_build.BuildConfig(sha, repo, root)


def test_build_release_publishes_manifest_after_all_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIRTUAL_ENV", "/build/venv")
    monkeypatch.setenv("PYTHONHOME", "/build/python")
    monkeypatch.setenv("GIT_DIR", "/build/git")
    repo, root = _repo_and_root(tmp_path)
    target = root / "releases" / SHA
    runner = FakeRunner(manifest_path=target / "manifest.json")

    result = release_build.build_release(_config(repo, root), runner, lambda: BUILT_AT)

    assert runner.kinds == [
        "git-head",
        "git-origin",
        "git-status",
        "ci",
        "git-archive",
        "venv",
        "uv",
        "npm-ci",
        "npm-build",
    ]
    assert runner.manifest_seen == [False] * len(runner.calls)
    assert result.release == target
    assert result.manifest == target / "manifest.json"
    assert result.api_dir == target / "apps/api"
    assert result.api_command == (
        str(target / ".venv/bin/python"),
        "-m",
        "uvicorn",
        "rihrp.main:app",
        "--app-dir",
        str(target / "apps/api"),
    )
    assert (target / ".venv/bin/python").is_file()
    assert (target / "apps/web/dist/index.html").is_file()

    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    assert manifest["schema"] == release_build.MANIFEST_SCHEMA
    assert manifest["sha"] == SHA
    assert manifest["migration"] == MIGRATION
    assert manifest["built_at"] == BUILT_AT_TEXT
    assert manifest["files"]["uv.lock"] == _sha256(b"lock\n")
    assert "apps/api/rihrp/main.py" in manifest["files"]
    assert "infra/migrations/versions/0004_research_documents.py" in manifest["files"]
    assert "apps/web/dist/index.html" in manifest["files"]

    git_calls = [call for call in runner.calls if call.argv[0] == "git"]
    assert {call.cwd for call in git_calls} == {repo}
    assert all("GIT_DIR" not in call.env for call in git_calls)

    build_calls = [
        call
        for call in runner.calls
        if call.argv[0] in {"uv", "npm"} or call.argv[0] == sys.executable
    ]
    assert build_calls
    assert all("VIRTUAL_ENV" not in call.env for call in build_calls)
    assert all("PYTHONHOME" not in call.env for call in build_calls)


def test_build_release_does_not_modify_the_source_repository(tmp_path: Path) -> None:
    repo, root = _repo_and_root(tmp_path)
    before = {
        path.relative_to(repo).as_posix(): path.read_bytes()
        for path in sorted(repo.rglob("*"))
        if path.is_file()
    }
    runner = FakeRunner(manifest_path=root / "releases" / SHA / "manifest.json")

    release_build.build_release(_config(repo, root), runner, lambda: BUILT_AT)

    after = {
        path.relative_to(repo).as_posix(): path.read_bytes()
        for path in sorted(repo.rglob("*"))
        if path.is_file()
    }
    assert after == before
    assert not (repo / "manifest.json").exists()
    assert not (repo / ".venv").exists()
    assert not (repo / "releases").exists()


def test_build_release_rejects_mixed_ci_runs(tmp_path: Path) -> None:
    repo, root = _repo_and_root(tmp_path)
    ci = json.dumps(
        [
            {"headSha": OTHER_SHA, "status": "completed", "conclusion": "failure"},
            {"headSha": SHA, "status": "completed", "conclusion": "success"},
        ]
    ).encode()
    runner = FakeRunner(ci=ci, manifest_path=root / "releases" / SHA / "manifest.json")

    with pytest.raises(release_build.BuildError, match="GitHub CI check failed"):
        release_build.build_release(_config(repo, root), runner, lambda: BUILT_AT)


@pytest.mark.parametrize(
    ("stage", "message", "target_created"),
    [
        ("ci", "GitHub CI check failed", False),
        ("archive", "source archive command failed", True),
        ("venv", "virtual environment creation failed", True),
        ("uv", "Python dependency sync failed", True),
        ("npm-ci", "npm ci failed", True),
        ("npm-build", "web build failed", True),
    ],
)
def test_build_release_failure_never_writes_the_manifest(
    tmp_path: Path, stage: str, message: str, target_created: bool
) -> None:
    repo, root = _repo_and_root(tmp_path)
    target = root / "releases" / SHA
    runner = FakeRunner(fail=stage, manifest_path=target / "manifest.json")

    with pytest.raises(release_build.BuildError, match=message):
        release_build.build_release(_config(repo, root), runner, lambda: BUILT_AT)

    assert not (target / "manifest.json").exists()
    assert target.exists() == target_created


def test_build_release_rejects_an_invalid_source_archive(tmp_path: Path) -> None:
    repo, root = _repo_and_root(tmp_path)
    target = root / "releases" / SHA
    runner = FakeRunner(archive=b"not a tar archive", manifest_path=target / "manifest.json")

    with pytest.raises(release_build.BuildError, match="source archive is invalid"):
        release_build.build_release(_config(repo, root), runner, lambda: BUILT_AT)

    assert not (target / "manifest.json").exists()


def test_build_release_rejects_an_incomplete_source_archive(tmp_path: Path) -> None:
    repo, root = _repo_and_root(tmp_path)
    target = root / "releases" / SHA
    entries = [entry for entry in _valid_entries() if entry.name != "apps/web/package.json"]
    runner = FakeRunner(archive=_archive(*entries), manifest_path=target / "manifest.json")

    with pytest.raises(release_build.BuildError, match="missing required files"):
        release_build.build_release(_config(repo, root), runner, lambda: BUILT_AT)

    assert not (target / "manifest.json").exists()


def test_release_lock_is_exclusive_and_private(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    with release_build.release_lock(root):
        lock = root / ".release.lock"
        assert (stat.S_IMODE(lock.stat().st_mode) & 0o077) == 0
        with (
            pytest.raises(release_build.BuildError, match="already held"),
            release_build.release_lock(root),
        ):
            pass

    with release_build.release_lock(root):
        pass


def test_release_lock_rejects_a_symlink(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = _write(tmp_path / "lock-target", b"")
    (root / ".release.lock").symlink_to(target)

    with (
        pytest.raises(release_build.BuildError, match="symlink"),
        release_build.release_lock(root),
    ):
        pass


def test_build_release_refuses_when_the_lock_is_held(tmp_path: Path) -> None:
    repo, root = _repo_and_root(tmp_path)
    root.mkdir()
    runner = FakeRunner()

    with release_build.release_lock(root):
        assert (root / ".release.lock").exists()
        with pytest.raises(release_build.BuildError, match="already held"):
            release_build.build_release(_config(repo, root), runner, lambda: BUILT_AT)

    assert runner.calls == []


@pytest.mark.parametrize("sha", ["", "a" * 39, "A" * 40, "g" * 40, "a" * 41])
def test_build_release_rejects_invalid_sha_before_any_command(tmp_path: Path, sha: str) -> None:
    repo, root = _repo_and_root(tmp_path)
    runner = FakeRunner()

    with pytest.raises(release_build.BuildError, match="40 lowercase hexadecimal"):
        release_build.build_release(_config(repo, root, sha), runner, lambda: BUILT_AT)

    assert runner.calls == []


def test_build_release_rejects_head_mismatch(tmp_path: Path) -> None:
    repo, root = _repo_and_root(tmp_path)
    runner = FakeRunner(sha=OTHER_SHA)

    with pytest.raises(release_build.BuildError, match="HEAD and origin/main"):
        release_build.build_release(_config(repo, root), runner, lambda: BUILT_AT)

    assert runner.kinds == ["git-head", "git-origin"]
    assert not (root / "releases" / SHA).exists()


def test_build_release_rejects_origin_mismatch(tmp_path: Path) -> None:
    repo, root = _repo_and_root(tmp_path)
    runner = FakeRunner(origin=OTHER_SHA)

    with pytest.raises(release_build.BuildError, match="HEAD and origin/main"):
        release_build.build_release(_config(repo, root), runner, lambda: BUILT_AT)

    assert runner.kinds == ["git-head", "git-origin"]


@pytest.mark.parametrize("status", [b" M README.md\n", b"?? untracked.txt\n"])
def test_build_release_rejects_a_dirty_worktree(tmp_path: Path, status: bytes) -> None:
    repo, root = _repo_and_root(tmp_path)
    runner = FakeRunner(status=status)

    with pytest.raises(release_build.BuildError, match="worktree must be clean"):
        release_build.build_release(_config(repo, root), runner, lambda: BUILT_AT)

    assert runner.kinds == ["git-head", "git-origin", "git-status"]


@pytest.mark.parametrize(
    "ci",
    [
        b"not-json",
        b"\xff",
        b"{}",
        b"[]",
        b'[1, "ignored"]',
        json.dumps(
            [{"headSha": OTHER_SHA, "status": "completed", "conclusion": "success"}]
        ).encode(),
        json.dumps([{"headSha": SHA, "status": "in_progress", "conclusion": None}]).encode(),
        json.dumps([{"headSha": SHA, "status": "completed", "conclusion": "failure"}]).encode(),
    ],
)
def test_build_release_requires_successful_ci_for_the_exact_sha(tmp_path: Path, ci: bytes) -> None:
    repo, root = _repo_and_root(tmp_path)
    runner = FakeRunner(ci=ci)

    with pytest.raises(release_build.BuildError, match="GitHub CI check failed"):
        release_build.build_release(_config(repo, root), runner, lambda: BUILT_AT)

    assert runner.kinds[-1] == "ci"
    assert not (root / "releases" / SHA).exists()


def test_build_release_wraps_runner_os_errors(tmp_path: Path) -> None:
    repo, root = _repo_and_root(tmp_path)

    def runner(_command: release_build.Command) -> release_build.CommandResult:
        raise OSError("runner failed")

    with pytest.raises(release_build.BuildError, match="repository identity check failed"):
        release_build.build_release(_config(repo, root), runner, lambda: BUILT_AT)


def test_build_release_rejects_non_ascii_git_output(tmp_path: Path) -> None:
    repo, root = _repo_and_root(tmp_path)

    def runner(_command: release_build.Command) -> release_build.CommandResult:
        return release_build.CommandResult(0, b"\xff\n")

    with pytest.raises(release_build.BuildError, match="repository identity check failed"):
        release_build.build_release(_config(repo, root), runner, lambda: BUILT_AT)


@pytest.mark.parametrize("layout", ["equal", "root_inside_repo", "repo_inside_root"])
def test_build_release_rejects_an_overlapping_release_root(tmp_path: Path, layout: str) -> None:
    if layout == "equal":
        repo = tmp_path / "repo"
        repo.mkdir()
        root = repo
    elif layout == "root_inside_repo":
        repo = tmp_path / "repo"
        repo.mkdir()
        root = repo / "releases"
    else:
        root = tmp_path
        repo = tmp_path / "repo"
        repo.mkdir()
    runner = FakeRunner()

    with pytest.raises(release_build.BuildError, match="must not overlap the repository"):
        release_build.build_release(_config(repo, root), runner, lambda: BUILT_AT)

    assert runner.calls == []


def test_build_release_rejects_a_symlinked_release_root(tmp_path: Path) -> None:
    repo, _ = _repo_and_root(tmp_path)
    real = tmp_path / "real"
    real.mkdir()
    root = tmp_path / "release-link"
    root.symlink_to(real, target_is_directory=True)
    runner = FakeRunner()

    with pytest.raises(release_build.BuildError, match="release root must not be a symlink"):
        release_build.build_release(_config(repo, root), runner, lambda: BUILT_AT)

    assert runner.calls == []


def test_build_release_rejects_a_release_root_that_is_a_file(tmp_path: Path) -> None:
    repo, _ = _repo_and_root(tmp_path)
    root = _write(tmp_path / "release-root", b"not a directory\n")
    runner = FakeRunner()

    with pytest.raises(release_build.BuildError, match="release root must be a directory"):
        release_build.build_release(_config(repo, root), runner, lambda: BUILT_AT)

    assert runner.calls == []


@pytest.mark.parametrize("kind", ["symlink", "file"])
def test_build_release_rejects_an_invalid_releases_path(tmp_path: Path, kind: str) -> None:
    repo, root = _repo_and_root(tmp_path)
    root.mkdir()
    releases = root / "releases"
    if kind == "symlink":
        outside = tmp_path / "outside"
        outside.mkdir()
        releases.symlink_to(outside, target_is_directory=True)
    else:
        releases.write_text("not a directory\n", encoding="utf-8")
    runner = FakeRunner()

    with pytest.raises(release_build.BuildError, match="releases path must be a real directory"):
        release_build.build_release(_config(repo, root), runner, lambda: BUILT_AT)

    assert runner.calls == []


def test_build_release_rejects_an_existing_target(tmp_path: Path) -> None:
    repo, root = _repo_and_root(tmp_path)
    (root / "releases" / SHA).mkdir(parents=True)
    runner = FakeRunner()

    with pytest.raises(release_build.BuildError, match="release target already exists"):
        release_build.build_release(_config(repo, root), runner, lambda: BUILT_AT)

    assert runner.calls == []


def test_build_release_rejects_a_symlinked_target(tmp_path: Path) -> None:
    repo, root = _repo_and_root(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    target = root / "releases" / SHA
    target.parent.mkdir(parents=True)
    target.symlink_to(outside, target_is_directory=True)
    runner = FakeRunner()

    with pytest.raises(release_build.BuildError, match="release target already exists"):
        release_build.build_release(_config(repo, root), runner, lambda: BUILT_AT)

    assert runner.calls == []


def test_build_release_requires_an_existing_repository(tmp_path: Path) -> None:
    root = tmp_path / "release-root"
    runner = FakeRunner()

    with pytest.raises(release_build.BuildError, match="repository does not exist"):
        release_build.build_release(_config(tmp_path / "missing", root), runner, lambda: BUILT_AT)

    assert runner.calls == []
