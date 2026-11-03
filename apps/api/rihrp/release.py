"""起動時のリリース成果物整合性検証。

検証は起動時に一度だけ行う。起動後のファイル改竄を継続的に検出するものではない。
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Final, NoReturn

from pydantic import BaseModel, ConfigDict, Field, ValidationError

MANIFEST_NAME: Final = "manifest.json"
EXPECTED_SCHEMA: Final = 1
EXPECTED_MIGRATION: Final = "0004_research_documents"
_MIGRATION_IDS: Final = frozenset({EXPECTED_MIGRATION})
_SHA_RE: Final = re.compile(r"[0-9a-f]{40}")
_HASH_RE: Final = re.compile(r"[0-9a-f]{64}")
_INVENTORY_DIRS: Final = ("apps/api", "infra/migrations", "apps/web/dist")
_INVENTORY_FILES: Final = (
    "uv.lock",
    "requirements-production.txt",
    "pyproject.toml",
    "apps/web/package-lock.json",
    "apps/web/package.json",
)


@dataclass
class ReleaseValidationError(RuntimeError):
    """公開して安全な理由コードだけを持つ起動エラー。"""

    reason: str

    def __str__(self) -> str:
        return f"release integrity validation failed: {self.reason}"


class _ReleaseManifest(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    schema_version: int = Field(alias="schema")
    sha: str
    migration: str
    built_at: str
    files: dict[str, str]


def _fail(reason: str) -> NoReturn:
    raise ReleaseValidationError(reason)


def _path_without_symlinks(root: Path, relative: str) -> Path:
    current = root
    for part in PurePosixPath(relative).parts:
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            _fail("required_path_missing")
        except OSError:
            _fail("required_path_unreadable")
        if stat.S_ISLNK(mode):
            _fail("symlink_forbidden")
    return current


def _required_directory(root: Path, relative: str) -> Path:
    path = _path_without_symlinks(root, relative)
    if not stat.S_ISDIR(path.lstat().st_mode):
        _fail("required_directory_missing")
    return path


def _required_file(root: Path, relative: str) -> Path:
    path = _path_without_symlinks(root, relative)
    if not stat.S_ISREG(path.lstat().st_mode):
        _fail("required_file_missing")
    return path


def _inventory_tree(root: Path, relative_dir: str, *, migrations: bool) -> set[str]:
    directory = _required_directory(root, relative_dir)
    inventory: set[str] = set()
    for current, directory_names, file_names in os.walk(directory, followlinks=False):
        current_path = Path(current)
        directory_names.sort()
        file_names.sort()
        for name in (*directory_names, *file_names):
            candidate = current_path / name
            try:
                mode = candidate.lstat().st_mode
            except OSError:
                _fail("required_path_unreadable")
            if stat.S_ISLNK(mode):
                _fail("symlink_forbidden")
        for name in file_names:
            candidate = current_path / name
            relative = candidate.relative_to(root).as_posix()
            if migrations and ("__pycache__" in candidate.parts or candidate.suffix == ".pyc"):
                continue
            if not stat.S_ISREG(candidate.lstat().st_mode):
                _fail("required_file_invalid")
            inventory.add(relative)
    if not inventory:
        _fail("required_directory_empty")
    return inventory


def _required_inventory(root: Path) -> dict[str, Path]:
    inventory: dict[str, Path] = {}
    for relative_dir in _INVENTORY_DIRS:
        for relative in _inventory_tree(
            root,
            relative_dir,
            migrations=relative_dir != "apps/web/dist",
        ):
            inventory[relative] = _required_file(root, relative)
    for relative in _INVENTORY_FILES:
        inventory[relative] = _required_file(root, relative)
    _required_file(root, "apps/web/dist/index.html")
    return inventory


def _file_sha256(path: Path) -> str:
    try:
        with path.open("rb") as source:
            return hashlib.file_digest(source, "sha256").hexdigest()
    except OSError:
        _fail("required_path_unreadable")


def validate_release(
    release_dir: str | Path | None = None,
    release_sha: str | None = None,
    *,
    root: str | Path | None = None,
) -> dict[str, str]:
    """検証済みリリースの公開識別子だけを返す。

    引数を省略した場合は ``RIHRP_RELEASE_DIR`` と ``RIHRP_RELEASE_SHA`` を使う。
    """

    release_dir = release_dir if release_dir is not None else os.environ.get("RIHRP_RELEASE_DIR")
    release_sha = release_sha if release_sha is not None else os.environ.get("RIHRP_RELEASE_SHA")
    if release_dir is None or release_sha is None:
        _fail("release_configuration_incomplete")
    if _SHA_RE.fullmatch(release_sha) is None:
        _fail("release_sha_invalid")

    supplied_dir = Path(release_dir)
    if supplied_dir.is_symlink():
        _fail("symlink_forbidden")
    try:
        resolved_dir = supplied_dir.resolve(strict=True)
    except OSError:
        _fail("release_directory_missing")
    if not resolved_dir.is_dir():
        _fail("release_directory_missing")
    if resolved_dir.name != release_sha:
        _fail("release_directory_name_mismatch")

    runtime_root = (
        Path(root).resolve(strict=True) if root is not None else Path(__file__).resolve().parents[3]
    )
    if resolved_dir != runtime_root:
        _fail("release_root_mismatch")

    manifest_path = _required_file(runtime_root, MANIFEST_NAME)
    try:
        if manifest_path.stat().st_size > 8 * 1024 * 1024:
            _fail("manifest_too_large")
        manifest_bytes = manifest_path.read_bytes()
    except OSError:
        _fail("manifest_unreadable")
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    try:
        manifest = _ReleaseManifest.model_validate_json(manifest_bytes)
    except (ValidationError, UnicodeDecodeError):
        _fail("manifest_invalid")

    if manifest.schema_version != EXPECTED_SCHEMA:
        _fail("manifest_schema_mismatch")
    if manifest.sha != release_sha:
        _fail("manifest_sha_mismatch")
    if manifest.migration not in _MIGRATION_IDS:
        _fail("manifest_migration_mismatch")
    try:
        built_at = datetime.fromisoformat(manifest.built_at)
    except ValueError:
        _fail("manifest_built_at_invalid")
    if built_at.tzinfo is None or built_at.utcoffset() != timedelta(0):
        _fail("manifest_built_at_invalid")
    if any(_HASH_RE.fullmatch(digest) is None for digest in manifest.files.values()):
        _fail("manifest_hash_invalid")

    inventory = _required_inventory(runtime_root)
    if set(manifest.files) != set(inventory):
        _fail("manifest_inventory_mismatch")
    for relative, path in inventory.items():
        if manifest.files[relative] != _file_sha256(path):
            _fail("manifest_file_hash_mismatch")

    return {"sha": release_sha, "manifest_sha256": manifest_sha256}
