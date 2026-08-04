"""Session backup: the captured post-state, stored before any mutation.

The backup lives in `<git-dir>/typethru/`. Content files are written first
and the manifest last, so a manifest's presence means the backup is complete.
Recovery is a dumb copy-back (DECISIONS.md #6): no diff math on the recovery
path.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from . import gitio

MANIFEST = "manifest.json"


class BackupError(Exception):
    pass


@dataclass(frozen=True)
class BackupFile:
    path: str            # repo-relative
    content_name: str | None  # file name inside backup dir; None = deleted in target
    mode: int | None


def backup_dir(root: Path) -> Path:
    return gitio.git_dir(root) / "typethru"


def exists(root: Path) -> bool:
    return (backup_dir(root) / MANIFEST).exists()


def create(root: Path, captures: list[tuple[str, bytes | None, int | None]]) -> None:
    """captures: (repo-relative path, target content or None for deleted, mode)."""
    bdir = backup_dir(root)
    if (bdir / MANIFEST).exists():
        raise BackupError("a backup already exists")
    bdir.mkdir(parents=True, exist_ok=True)
    files: list[dict] = []
    for i, (path, content, mode) in enumerate(captures):
        content_name = None
        if content is not None:
            content_name = f"{i}.bin"
            _write_synced(bdir / content_name, content)
        files.append({"path": path, "content": content_name, "mode": mode})
    manifest = {
        "version": 1,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "files": files,
    }
    _write_synced(bdir / MANIFEST, json.dumps(manifest, indent=2).encode("utf-8"))


def load(root: Path) -> list[BackupFile]:
    mpath = backup_dir(root) / MANIFEST
    if not mpath.exists():
        raise BackupError("no session backup found")
    try:
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        return [
            BackupFile(path=f["path"], content_name=f["content"], mode=f.get("mode"))
            for f in manifest["files"]
        ]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise BackupError(f"backup manifest is unreadable: {exc}") from exc


def target_content(root: Path, bf: BackupFile) -> bytes | None:
    if bf.content_name is None:
        return None
    blob = backup_dir(root) / bf.content_name
    if not blob.exists():
        raise BackupError(f"backup blob missing for {bf.path}")
    return blob.read_bytes()


def restore(root: Path) -> list[str]:
    """Copy the captured post-state back over the working tree, then drop
    the backup. Returns the restored paths."""
    files = load(root)
    for bf in files:
        gitio.write_file(root, bf.path, target_content(root, bf), bf.mode)
    drop(root)
    return [bf.path for bf in files]


def drop(root: Path) -> None:
    bdir = backup_dir(root)
    if not bdir.exists():
        return
    for child in bdir.iterdir():
        child.unlink()
    bdir.rmdir()


def _write_synced(path: Path, data: bytes) -> None:
    with open(path, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
