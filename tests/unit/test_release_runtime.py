"""Unit tests for startup release integrity validation.

The tests use temporary release trees only. They never connect to a database,
start the application, or read a real release.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from tools import release_build

from rihrp.release import ReleaseValidationError, validate_release
from rihrp.routers import health

SHA = "a" * 40
OTHER_SHA = "b" * 40
MIGRATION = "0004_research_documents"
BUILT_AT = "2026-11-03T12:00:00.000000Z"


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


@pytest.fixture
def release_dir(tmp_path: Path) -> Path:
    root = tmp_path / SHA
    root.mkdir()
    _write(root / "uv.lock", b"lock-v1\n")
    _write(root / "requirements-production.txt", b"fastapi==0.115\n")
    _write(root / "pyproject.toml", b'[project]\nname = "rihrp"\n')
    _write(root / "apps/web/package-lock.json", b'{"lockfileVersion": 3}\n')
    _write(root / "apps/web/package.json", b"{}\n")
    _write(root / "apps/api/rihrp/__init__.py", b'__version__ = "0.1.0"\n')
    _write(root / "apps/api/rihrp/main.py", b"app = object()\n")
    _write(
        root / "infra/migrations/versions/0004_research_documents.py",
        b'revision = "0004_research_documents"\n',
    )
    _write(root / "apps/web/dist/index.html", b"<html>release</html>\n")
    _write(root / "apps/web/dist/assets/app.js", b"console.log('release');\n")
    files = release_build.collect_manifest_files(root)
    manifest = {
        "schema": 1,
        "sha": SHA,
        "migration": MIGRATION,
        "built_at": BUILT_AT,
        "files": files,
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _read_manifest(root: Path) -> dict[str, object]:
    data = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _write_manifest(root: Path, manifest: dict[str, object]) -> None:
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _files(manifest: dict[str, object]) -> dict[str, str]:
    return cast(dict[str, str], manifest["files"])


def _reject(release_dir: Path, reason: str) -> None:
    with pytest.raises(ReleaseValidationError) as excinfo:
        validate_release(release_dir, SHA, root=release_dir)
    assert excinfo.value.reason == reason


def test_validate_release_accepts_complete_release(release_dir: Path) -> None:
    identity = validate_release(release_dir, SHA, root=release_dir)
    manifest_bytes = (release_dir / "manifest.json").read_bytes()

    assert identity == {
        "sha": SHA,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }


def test_fixture_manifest_covers_required_inventory(release_dir: Path) -> None:
    manifest = _read_manifest(release_dir)
    files = _files(manifest)

    assert manifest["schema"] == 1
    assert manifest["sha"] == SHA
    assert manifest["migration"] == MIGRATION
    assert manifest["built_at"] == BUILT_AT
    assert {
        "uv.lock",
        "requirements-production.txt",
        "pyproject.toml",
        "apps/web/package-lock.json",
        "apps/web/package.json",
        "apps/api/rihrp/main.py",
        "infra/migrations/versions/0004_research_documents.py",
        "apps/web/dist/index.html",
        "apps/web/dist/assets/app.js",
    } <= set(files)


def test_manifest_hashes_match_independent_sha256(release_dir: Path) -> None:
    files = _files(_read_manifest(release_dir))

    assert files["uv.lock"] == hashlib.sha256(b"lock-v1\n").hexdigest()
    assert files["pyproject.toml"] == hashlib.sha256(b'[project]\nname = "rihrp"\n').hexdigest()
    assert (
        files["apps/web/dist/index.html"] == hashlib.sha256(b"<html>release</html>\n").hexdigest()
    )


@pytest.mark.parametrize(
    "relative",
    ["uv.lock", "apps/api/rihrp/main.py", "apps/web/dist/assets/app.js"],
)
def test_tampered_release_file_is_rejected(release_dir: Path, relative: str) -> None:
    (release_dir / relative).write_bytes(b"tampered\n")

    _reject(release_dir, "manifest_file_hash_mismatch")


def test_manifest_omission_is_rejected(release_dir: Path) -> None:
    manifest = _read_manifest(release_dir)
    del _files(manifest)["apps/web/dist/assets/app.js"]
    _write_manifest(release_dir, manifest)

    _reject(release_dir, "manifest_inventory_mismatch")


def test_manifest_extra_entry_is_rejected(release_dir: Path) -> None:
    manifest = _read_manifest(release_dir)
    _files(manifest)["apps/api/ghost.py"] = "0" * 64
    _write_manifest(release_dir, manifest)

    _reject(release_dir, "manifest_inventory_mismatch")


@pytest.mark.parametrize(
    "key",
    ["../outside.py", "/absolute/outside.py", "apps/api/../outside.py"],
)
def test_manifest_unsafe_path_is_rejected(release_dir: Path, key: str) -> None:
    manifest = _read_manifest(release_dir)
    _files(manifest)[key] = "0" * 64
    _write_manifest(release_dir, manifest)

    _reject(release_dir, "manifest_inventory_mismatch")


def test_missing_inventory_file_is_rejected(release_dir: Path) -> None:
    (release_dir / "apps/web/dist/assets/app.js").unlink()

    _reject(release_dir, "manifest_inventory_mismatch")


def test_extra_inventory_file_is_rejected(release_dir: Path) -> None:
    _write(release_dir / "apps/api/ghost.py", b"ghost\n")

    _reject(release_dir, "manifest_inventory_mismatch")


def test_symlinked_release_directory_is_rejected(tmp_path: Path, release_dir: Path) -> None:
    link = tmp_path / "release-link"
    link.symlink_to(release_dir, target_is_directory=True)

    with pytest.raises(ReleaseValidationError) as excinfo:
        validate_release(link, SHA, root=release_dir)

    assert excinfo.value.reason == "symlink_forbidden"


def test_symlinked_manifest_is_rejected(tmp_path: Path, release_dir: Path) -> None:
    target = tmp_path / "manifest-target.json"
    (release_dir / "manifest.json").rename(target)
    (release_dir / "manifest.json").symlink_to(target)

    _reject(release_dir, "symlink_forbidden")


def test_symlinked_required_file_is_rejected(tmp_path: Path, release_dir: Path) -> None:
    target = tmp_path / "uv.lock.target"
    (release_dir / "uv.lock").rename(target)
    (release_dir / "uv.lock").symlink_to(target)

    _reject(release_dir, "symlink_forbidden")


def test_symlinked_inventory_directory_is_rejected(tmp_path: Path, release_dir: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (release_dir / "apps/api/linked").symlink_to(outside, target_is_directory=True)

    _reject(release_dir, "symlink_forbidden")


@pytest.mark.parametrize("present", ["dir", "sha", "none"])
def test_partial_release_environment_is_rejected(
    release_dir: Path, monkeypatch: pytest.MonkeyPatch, present: str
) -> None:
    monkeypatch.delenv("RIHRP_RELEASE_DIR", raising=False)
    monkeypatch.delenv("RIHRP_RELEASE_SHA", raising=False)
    if present == "dir":
        monkeypatch.setenv("RIHRP_RELEASE_DIR", str(release_dir))
    elif present == "sha":
        monkeypatch.setenv("RIHRP_RELEASE_SHA", SHA)

    with pytest.raises(ReleaseValidationError) as excinfo:
        validate_release(root=release_dir)

    assert excinfo.value.reason == "release_configuration_incomplete"


def test_release_environment_is_used_when_arguments_are_omitted(
    release_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RIHRP_RELEASE_DIR", str(release_dir))
    monkeypatch.setenv("RIHRP_RELEASE_SHA", SHA)

    identity = validate_release(root=release_dir)

    assert identity["sha"] == SHA


@pytest.mark.parametrize("sha", ["", "a" * 39, "A" * 40, "g" * 40, "a" * 41])
def test_invalid_release_sha_is_rejected(release_dir: Path, sha: str) -> None:
    with pytest.raises(ReleaseValidationError) as excinfo:
        validate_release(release_dir, sha, root=release_dir)

    assert excinfo.value.reason == "release_sha_invalid"


def test_release_directory_basename_must_equal_sha(tmp_path: Path, release_dir: Path) -> None:
    renamed = tmp_path / OTHER_SHA
    release_dir.rename(renamed)

    with pytest.raises(ReleaseValidationError) as excinfo:
        validate_release(renamed, SHA, root=renamed)

    assert excinfo.value.reason == "release_directory_name_mismatch"


def test_release_root_must_match_directory(tmp_path: Path, release_dir: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()

    with pytest.raises(ReleaseValidationError) as excinfo:
        validate_release(release_dir, SHA, root=other)

    assert excinfo.value.reason == "release_root_mismatch"


def test_missing_release_directory_is_rejected(tmp_path: Path) -> None:
    missing = tmp_path / SHA

    with pytest.raises(ReleaseValidationError) as excinfo:
        validate_release(missing, SHA, root=missing)

    assert excinfo.value.reason == "release_directory_missing"


def test_missing_manifest_is_rejected(release_dir: Path) -> None:
    (release_dir / "manifest.json").unlink()

    _reject(release_dir, "required_path_missing")


def test_invalid_manifest_json_is_rejected(release_dir: Path) -> None:
    (release_dir / "manifest.json").write_text("{", encoding="utf-8")

    _reject(release_dir, "manifest_invalid")


def test_manifest_must_be_an_object(release_dir: Path) -> None:
    (release_dir / "manifest.json").write_text("[]", encoding="utf-8")

    _reject(release_dir, "manifest_invalid")


def test_manifest_schema_must_be_one(release_dir: Path) -> None:
    manifest = _read_manifest(release_dir)
    manifest["schema"] = 2
    _write_manifest(release_dir, manifest)

    _reject(release_dir, "manifest_schema_mismatch")


def test_manifest_schema_type_is_strict(release_dir: Path) -> None:
    manifest = _read_manifest(release_dir)
    manifest["schema"] = "1"
    _write_manifest(release_dir, manifest)

    _reject(release_dir, "manifest_invalid")


def test_manifest_sha_must_match_release_sha(release_dir: Path) -> None:
    manifest = _read_manifest(release_dir)
    manifest["sha"] = OTHER_SHA
    _write_manifest(release_dir, manifest)

    _reject(release_dir, "manifest_sha_mismatch")


def test_manifest_migration_must_be_expected(release_dir: Path) -> None:
    manifest = _read_manifest(release_dir)
    manifest["migration"] = "0003_audit_truncate"
    _write_manifest(release_dir, manifest)

    _reject(release_dir, "manifest_migration_mismatch")


def test_manifest_built_at_is_required(release_dir: Path) -> None:
    manifest = _read_manifest(release_dir)
    manifest["built_at"] = ""
    _write_manifest(release_dir, manifest)

    _reject(release_dir, "manifest_built_at_invalid")


def test_manifest_missing_required_key_is_rejected(release_dir: Path) -> None:
    manifest = _read_manifest(release_dir)
    del manifest["built_at"]
    _write_manifest(release_dir, manifest)

    _reject(release_dir, "manifest_invalid")


@pytest.mark.parametrize("digest", ["0" * 63, "A" * 64, "not-a-digest"])
def test_manifest_hash_values_must_be_lowercase_sha256(release_dir: Path, digest: str) -> None:
    manifest = _read_manifest(release_dir)
    _files(manifest)["uv.lock"] = digest
    _write_manifest(release_dir, manifest)

    _reject(release_dir, "manifest_hash_invalid")


def _request(state: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=state))


def test_healthz_without_release_state_keeps_legacy_payload() -> None:
    assert health.healthz(_request(SimpleNamespace())) == {"status": "ok"}


def test_healthz_with_none_release_identity_keeps_legacy_payload() -> None:
    request = _request(SimpleNamespace(release_identity=None))

    assert health.healthz(request) == {"status": "ok"}


def test_healthz_with_release_identity_includes_it() -> None:
    identity = {"sha": SHA, "manifest_sha256": "f" * 64}
    request = _request(SimpleNamespace(release_identity=identity))

    assert health.healthz(request) == {"status": "ok", "release": identity}
