#!/usr/bin/env python3
"""Build an immutable RIHRP release from a verified main commit."""

from __future__ import annotations

import argparse
import errno
import fcntl
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Final, Protocol, TypedDict

SHA_RE: Final = re.compile(r"[0-9a-f]{40}")
MIGRATION: Final = "0004_research_documents"
MANIFEST_SCHEMA: Final = 1
MANIFEST_NAME: Final = "manifest.json"
SOURCE_REQUIRED: Final = (
    "uv.lock",
    "requirements-production.txt",
    "pyproject.toml",
    "apps/web/package.json",
    "apps/web/package-lock.json",
)
MANIFEST_FILES: Final = (
    "uv.lock",
    "requirements-production.txt",
    "pyproject.toml",
    "apps/web/package-lock.json",
    "apps/web/package.json",
)
MANIFEST_TREES: Final = (
    ("apps/api", True),
    ("infra/migrations", True),
    ("apps/web/dist", False),
)

type JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


class ReleaseManifest(TypedDict):
    schema: int
    sha: str
    migration: str
    built_at: str
    files: dict[str, str]


@dataclass(frozen=True, slots=True)
class BuildConfig:
    expect_sha: str
    repo: Path
    release_root: Path


@dataclass(frozen=True, slots=True)
class Command:
    argv: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str]
    timeout: float = 3600


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: bytes = b""
    stderr: bytes = b""


class Runner(Protocol):
    def __call__(self, command: Command) -> CommandResult: ...


@dataclass
class BuildError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class BuildResult:
    release: Path
    manifest: Path
    api_dir: Path
    api_command: tuple[str, ...]


def utc_now() -> datetime:
    return datetime.now(UTC)


def external_runner(command: Command) -> CommandResult:
    """Run a command without a shell and without exposing its output."""
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            list(command.argv),
            cwd=command.cwd,
            env=dict(command.env),
            capture_output=True,
            check=False,
            timeout=command.timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return CommandResult(returncode=125)
    return CommandResult(result.returncode, result.stdout, result.stderr)


def parse_sha(value: str) -> str:
    if SHA_RE.fullmatch(value) is None:
        raise BuildError("expected SHA must be 40 lowercase hexadecimal characters")
    return value


def paths_overlap(first: Path, second: Path) -> bool:
    return first == second or first.is_relative_to(second) or second.is_relative_to(first)


def api_command(release: Path) -> tuple[str, ...]:
    """Return the release-only API command; the caller appends host settings."""
    return (
        str(release / ".venv/bin/python"),
        "-m",
        "uvicorn",
        "rihrp.main:app",
        "--app-dir",
        str(release / "apps/api"),
    )


def _git_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.pop("GH_REPO", None)
    env.pop("GH_HOST", None)
    env.update(
        GIT_OPTIONAL_LOCKS="0",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_TERMINAL_PROMPT="0",
        LC_ALL="C",
    )
    return env


def _build_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env["PYTHONNOUSERSITE"] = "1"
    return env


def _checked(command: Command, runner: Runner, failure: str) -> bytes:
    try:
        result = runner(command)
    except (OSError, subprocess.SubprocessError):
        raise BuildError(failure) from None
    if result.returncode != 0:
        raise BuildError(failure)
    return result.stdout


def _ascii_output(command: Command, runner: Runner, failure: str) -> str:
    try:
        return _checked(command, runner, failure).decode("ascii")
    except UnicodeDecodeError:
        raise BuildError(failure) from None


def _git(repo: Path, arguments: tuple[str, ...], runner: Runner, failure: str) -> str:
    command = Command(
        ("git", "-C", str(repo), "--no-optional-locks", *arguments),
        repo,
        _git_env(),
    )
    return _ascii_output(command, runner, failure)


def _verify_git(config: BuildConfig, repo: Path, runner: Runner) -> None:
    identity_failure = "repository identity check failed"
    head = _git(repo, ("rev-parse", "--verify", "HEAD"), runner, identity_failure).strip()
    origin = _git(
        repo,
        ("rev-parse", "--verify", "refs/remotes/origin/main"),
        runner,
        identity_failure,
    ).strip()
    if head != config.expect_sha or origin != config.expect_sha:
        raise BuildError("HEAD and origin/main must equal the expected SHA")
    status = _git(
        repo,
        ("status", "--porcelain=v1", "--untracked-files=all"),
        runner,
        "repository worktree check failed",
    )
    if status:
        raise BuildError("repository worktree must be clean")


def _verify_ci(config: BuildConfig, repo: Path, runner: Runner) -> None:
    failure = "GitHub CI check failed"
    command = Command(
        (
            "gh",
            "run",
            "list",
            "--repo",
            "Kensan196948G/RIHRP-Research-Studio",
            "--branch",
            "main",
            "--event",
            "push",
            "--commit",
            config.expect_sha,
            "--workflow",
            "ci.yml",
            "--json",
            "headSha,conclusion,status",
            "--limit",
            "10",
        ),
        repo,
        _git_env(),
    )
    try:
        raw: JsonValue = json.loads(_checked(command, runner, failure))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise BuildError(failure) from None
    if not isinstance(raw, list):
        raise BuildError(failure)
    if raw and all(
        isinstance(item, dict)
        and item.get("headSha") == config.expect_sha
        and item.get("status") == "completed"
        and item.get("conclusion") == "success"
        for item in raw
    ):
        return
    raise BuildError(failure)


def _lexists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        raise BuildError("release path cannot be inspected") from None
    return True


@contextmanager
def release_lock(root: Path) -> Iterator[None]:
    """Hold the nonblocking release-root lock for the complete build."""
    flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        descriptor = os.open(root / ".release.lock", flags, 0o600)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise BuildError("release lock must not be a symlink") from None
        raise BuildError("release lock cannot be opened") from None
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                raise BuildError("release lock is already held") from None
            raise BuildError("release lock cannot be acquired") from None
        yield
    finally:
        os.close(descriptor)


def _canonical_paths(config: BuildConfig) -> tuple[Path, Path]:
    repo = config.repo.expanduser().resolve()
    raw_root = config.release_root.expanduser()
    if raw_root.is_symlink():
        raise BuildError("release root must not be a symlink")
    root = raw_root.resolve()
    if not repo.is_dir():
        raise BuildError("repository does not exist")
    if paths_overlap(root, repo):
        raise BuildError("release root must not overlap the repository")
    if _lexists(root) and not root.is_dir():
        raise BuildError("release root must be a directory")
    try:
        root.mkdir(parents=True, exist_ok=True)
        os.chmod(root, 0o700)
    except OSError:
        raise BuildError("release root cannot be created") from None
    if root.is_symlink() or not root.is_dir():
        raise BuildError("release root must be a real directory")
    return repo, root


def _reserve_target(root: Path, sha: str) -> Path:
    releases = root / "releases"
    if _lexists(releases) and (releases.is_symlink() or not releases.is_dir()):
        raise BuildError("releases path must be a real directory")
    try:
        releases.mkdir(mode=0o700, exist_ok=True)
        os.chmod(releases, 0o700)
    except OSError:
        raise BuildError("releases path cannot be created") from None
    target = releases / sha
    if _lexists(target):
        raise BuildError("release target already exists")
    try:
        target.mkdir(mode=0o700)
    except FileExistsError:
        raise BuildError("release target already exists") from None
    except OSError:
        raise BuildError("release target cannot be created") from None
    return target


def _archive_member_name(member: tarfile.TarInfo) -> str:
    name = member.name.rstrip("/") if member.isdir() else member.name
    if not name or "\\" in name:
        raise BuildError("source archive contains an unsafe path")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise BuildError("source archive contains an unsafe path")
    for part in path.parts:
        if part == ".env" or (part.startswith(".env.") and part != ".env.example"):
            raise BuildError("source archive contains a forbidden environment file")
    if name == MANIFEST_NAME:
        raise BuildError("source archive reserves the release manifest path")
    return name


def validate_source_archive(data: bytes) -> tuple[str, ...]:
    """Validate a git archive and return its member names without extracting it."""
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
            members = archive.getmembers()
    except (tarfile.TarError, OSError, EOFError):
        raise BuildError("source archive is invalid") from None
    names: list[str] = []
    regular: set[str] = set()
    for member in members:
        name = _archive_member_name(member)
        if member.issym() or member.islnk():
            raise BuildError("source archive must not contain links")
        if not (member.isfile() or member.isdir()):
            raise BuildError("source archive contains a non-regular entry")
        if name in names:
            raise BuildError("source archive contains duplicate paths")
        names.append(name)
        if member.isfile():
            regular.add(name)
    missing = [path for path in SOURCE_REQUIRED if path not in regular]
    if missing:
        raise BuildError("source archive is missing required files")
    if not any(name.startswith("apps/api/") for name in regular):
        raise BuildError("source archive is missing the API tree")
    if not any(name.startswith("infra/migrations/") for name in regular):
        raise BuildError("source archive is missing the migrations tree")
    return tuple(names)


def extract_source_archive(data: bytes, release: Path) -> None:
    """Validate and safely extract one git tar archive into a fresh release."""
    validate_source_archive(data)
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
            archive.extractall(release, filter="data")
    except (tarfile.TarError, OSError):
        raise BuildError("source archive extraction failed") from None


def _regular_file(path: Path) -> bool:
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except OSError:
        return False


def _require_regular(release: Path, relative: str) -> Path:
    path = release / relative
    if not _regular_file(path):
        raise BuildError(f"release is missing required regular file: {relative}")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        raise BuildError("release file cannot be hashed") from None
    return digest.hexdigest()


def _raise_walk_error(error: OSError) -> None:
    raise error


def _tree_hashes(release: Path, relative: str, exclude_python_cache: bool) -> dict[str, str]:
    root = release / relative
    try:
        if root.is_symlink() or not stat.S_ISDIR(root.lstat().st_mode):
            raise BuildError(f"release tree is not a real directory: {relative}")
        files: dict[str, str] = {}
        for directory, dirnames, filenames in os.walk(root, onerror=_raise_walk_error):
            base = Path(directory)
            for dirname in dirnames:
                if (base / dirname).is_symlink():
                    raise BuildError(f"release tree contains a symlink: {relative}")
            for filename in filenames:
                path = base / filename
                if path.is_symlink() or not _regular_file(path):
                    raise BuildError(
                        f"release tree contains a symlink or non-regular file: {relative}"
                    )
                if exclude_python_cache and path.suffix == ".pyc":
                    continue
                key = path.relative_to(release).as_posix()
                files[key] = _sha256(path)
            if exclude_python_cache:
                dirnames[:] = [name for name in dirnames if name != "__pycache__"]
    except OSError:
        raise BuildError(f"release tree cannot be read: {relative}") from None
    if not files:
        raise BuildError(f"release tree is empty: {relative}")
    return files


def collect_manifest_files(release: Path) -> dict[str, str]:
    """Hash every required file and regular file in the manifest trees."""
    files = {relative: _sha256(_require_regular(release, relative)) for relative in MANIFEST_FILES}
    for relative, exclude_python_cache in MANIFEST_TREES:
        files.update(_tree_hashes(release, relative, exclude_python_cache))
    _require_regular(release, "apps/web/dist/index.html")
    return dict(sorted(files.items()))


def _utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise BuildError("manifest clock must return an aware datetime")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def create_manifest(release: Path, sha: str, built_at: datetime) -> ReleaseManifest:
    """Create the manifest value after all release artifacts are complete."""
    return {
        "schema": MANIFEST_SCHEMA,
        "sha": parse_sha(sha),
        "migration": MIGRATION,
        "built_at": _utc_timestamp(built_at),
        "files": collect_manifest_files(release),
    }


def write_manifest(release: Path, manifest: ReleaseManifest) -> Path:
    """Atomically publish the manifest as the release completion marker."""
    target = release / MANIFEST_NAME
    if _lexists(target):
        raise BuildError("release manifest already exists")
    try:
        descriptor, temporary = tempfile.mkstemp(
            dir=release,
            prefix=".manifest.",
            suffix=".tmp",
        )
    except OSError:
        raise BuildError("release manifest cannot be created") from None
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except OSError:
        raise BuildError("release manifest cannot be published") from None
    return target


def _build_command(
    arguments: tuple[str, ...],
    cwd: Path,
    runner: Runner,
    failure: str,
) -> None:
    _checked(Command(arguments, cwd, _build_env()), runner, failure)


def verify_migration_contract(release: Path) -> None:
    """Refuse schema additions or edits in this intentionally 0004-only deployer."""
    try:
        contract = json.loads(Path(__file__).with_name("migration-0004-contract.json").read_text())[
            "files"
        ]
    except (OSError, ValueError, KeyError):
        raise BuildError("known migration contract is unavailable") from None
    actual = _tree_hashes(release, "infra/migrations/versions", True)
    if actual != contract:
        raise BuildError("migration contents differ from the approved 0004 contract")


def build_release(
    config: BuildConfig,
    runner: Runner = external_runner,
    clock: Callable[[], datetime] = utc_now,
) -> BuildResult:
    """Build one immutable release and publish its manifest last."""
    sha = parse_sha(config.expect_sha)
    repo, root = _canonical_paths(config)
    with release_lock(root):
        releases = root / "releases"
        if _lexists(releases) and (releases.is_symlink() or not releases.is_dir()):
            raise BuildError("releases path must be a real directory")
        target = releases / sha
        if _lexists(target):
            raise BuildError("release target already exists")
        _verify_git(config, repo, runner)
        _verify_ci(config, repo, runner)
        target = _reserve_target(root, sha)

        archive = _checked(
            Command(
                ("git", "-C", str(repo), "--no-optional-locks", "archive", "--format=tar", sha),
                repo,
                _git_env(),
            ),
            runner,
            "source archive command failed",
        )
        extract_source_archive(archive, target)
        for relative in SOURCE_REQUIRED:
            _require_regular(target, relative)
        verify_migration_contract(target)

        venv = target / ".venv"
        venv_python = venv / "bin/python"
        _build_command(
            (sys.executable, "-m", "venv", "--copies", str(venv)),
            target,
            runner,
            "virtual environment creation failed",
        )
        _build_command(
            (
                "uv",
                "pip",
                "sync",
                "--require-hashes",
                "--python",
                str(venv_python),
                str(target / "requirements-production.txt"),
            ),
            target,
            runner,
            "Python dependency sync failed",
        )
        web = target / "apps/web"
        _build_command(("npm", "ci"), web, runner, "npm ci failed")
        _build_command(("npm", "run", "build"), web, runner, "web build failed")

        manifest = create_manifest(target, sha, clock())
        manifest_path = write_manifest(target, manifest)
        return BuildResult(
            release=target,
            manifest=manifest_path,
            api_dir=target / "apps/api",
            api_command=api_command(target),
        )


def _sha_argument(value: str) -> str:
    try:
        return parse_sha(value)
    except BuildError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="release_build.py")
    parser.add_argument("--expect-sha", required=True, type=_sha_argument)
    parser.add_argument(
        "--release-root",
        type=Path,
        default=Path.home() / ".local/share/rihrp",
    )
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    return parser


def main(
    argv: list[str] | None = None,
    runner: Runner = external_runner,
    clock: Callable[[], datetime] = utc_now,
) -> int:
    args = _parser().parse_args(argv)
    print(f"building release {args.expect_sha}", file=sys.stderr)
    try:
        result = build_release(
            BuildConfig(args.expect_sha, args.repo, args.release_root),
            runner,
            clock,
        )
    except BuildError as exc:
        print(f"release build failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "release": str(result.release),
                "manifest": str(result.manifest),
                "api_app_dir": str(result.api_dir),
                "api_command": list(result.api_command),
                "api_environment": {
                    "RIHRP_RELEASE_SHA": args.expect_sha,
                    "RIHRP_RELEASE_DIR": str(result.release),
                    "RIHRP_WEB_DIST": str(result.release / "apps/web/dist"),
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
