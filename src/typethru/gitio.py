"""Thin wrappers around the git CLI.

Every git interaction in typethru goes through this module so the rest of
the code never builds a git command line. All functions raise GitError with
a human-readable message on failure; callers translate to exit-2 errors.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(Exception):
    """A git invocation failed or the repository is in an unusable state."""


def _run(args: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitError("git executable not found on PATH") from exc
    if check and proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", "replace").strip()
        raise GitError(f"git {' '.join(args[:2])} failed: {stderr or proc.returncode}")
    return proc


def repo_root(cwd: Path | None = None) -> Path:
    proc = _run(["rev-parse", "--show-toplevel"], cwd=cwd, check=False)
    if proc.returncode != 0:
        raise GitError("not a git repository (run inside the repo the agent edited)")
    return Path(proc.stdout.decode("utf-8", "replace").strip())


def git_dir(root: Path) -> Path:
    proc = _run(["rev-parse", "--git-dir"], cwd=root)
    path = Path(proc.stdout.decode("utf-8", "replace").strip())
    return path if path.is_absolute() else root / path


def in_progress_operation(root: Path) -> str | None:
    """Return 'merge', 'rebase', or 'cherry-pick' if one is underway, else None."""
    gdir = git_dir(root)
    if (gdir / "MERGE_HEAD").exists():
        return "merge"
    if (gdir / "rebase-merge").exists() or (gdir / "rebase-apply").exists():
        return "rebase"
    if (gdir / "CHERRY_PICK_HEAD").exists():
        return "cherry-pick"
    return None


def head_commit(root: Path) -> str | None:
    """The HEAD commit sha, or None on an unborn branch (fresh repo)."""
    proc = _run(["rev-parse", "--verify", "-q", "HEAD"], cwd=root, check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode().strip()


@dataclass(frozen=True)
class StatusEntry:
    path: str          # repo-relative, forward slashes
    index: str         # index status letter (porcelain v1)
    worktree: str      # worktree status letter
    submodule: bool


def status_entries(root: Path) -> list[StatusEntry]:
    """Tracked-change entries from `git status`, renames split into D+A.

    Untracked files (??) and ignored files are returned too; callers filter.
    """
    proc = _run(
        ["status", "--porcelain=v1", "-z", "--no-renames", "--untracked-files=normal"],
        cwd=root,
    )
    raw = proc.stdout.decode("utf-8", "replace")
    entries: list[StatusEntry] = []
    sub_paths = _submodule_paths(root)
    for record in raw.split("\0"):
        if not record:
            continue
        if len(record) < 4:
            continue
        index, worktree, path = record[0], record[1], record[3:]
        entries.append(
            StatusEntry(
                path=path,
                index=index,
                worktree=worktree,
                submodule=path.rstrip("/") in sub_paths,
            )
        )
    return entries


def _submodule_paths(root: Path) -> set[str]:
    if not (root / ".gitmodules").exists():
        return set()
    proc = _run(
        ["config", "--file", ".gitmodules", "--get-regexp", r"submodule\..*\.path"],
        cwd=root,
        check=False,
    )
    paths: set[str] = set()
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split(" ", 1)
        if len(parts) == 2:
            paths.add(parts[1].strip())
    return paths


def head_content(root: Path, path: str) -> bytes | None:
    """File content at HEAD, or None if the path does not exist in HEAD."""
    proc = _run(["cat-file", "-p", f"HEAD:{path}"], cwd=root, check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout


def unstage(root: Path, paths: list[str]) -> None:
    if not paths:
        return
    head = head_commit(root)
    if head is None:
        # Unborn branch: removing from the index is the only "unstage".
        _run(["rm", "--cached", "-q", "--", *paths], cwd=root, check=False)
        return
    _run(["restore", "--staged", "--", *paths], cwd=root)


def rev_parse_commit(root: Path, rev: str) -> str | None:
    proc = _run(["rev-parse", "--verify", "-q", f"{rev}^{{commit}}"], cwd=root, check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode().strip()


def empty_tree(root: Path) -> str:
    proc = subprocess.run(
        ["git", "mktree"], cwd=root, input=b"", capture_output=True, check=True
    )
    return proc.stdout.decode().strip()


def rev_content(root: Path, rev: str, path: str) -> bytes | None:
    proc = _run(["cat-file", "-p", f"{rev}:{path}"], cwd=root, check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout


def recent_commits(root: Path, n: int, paths: list[str] | None = None) -> list[tuple[str, str]]:
    """(sha, subject) of the last n commits from HEAD, newest first,
    optionally limited to commits touching the given paths."""
    args = ["log", "-n", str(n), "--format=%H%x00%s"]
    if paths:
        args += ["--", *paths]
    proc = _run(args, cwd=root)
    out: list[tuple[str, str]] = []
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        if "\x00" in line:
            sha, subject = line.split("\x00", 1)
            out.append((sha, subject))
    return out


def diff_name_status(root: Path, base: str, target: str) -> list[tuple[str, str]]:
    """(status letter, path) pairs between two revisions, renames split."""
    proc = _run(
        ["diff", "--name-status", "-z", "--no-renames", base, target], cwd=root
    )
    fields = proc.stdout.decode("utf-8", "replace").split("\0")
    out: list[tuple[str, str]] = []
    i = 0
    while i + 1 < len(fields):
        status, path = fields[i], fields[i + 1]
        if status:
            out.append((status[0], path))
        i += 2
    return out


def config_get_all(root: Path, key: str) -> list[str]:
    proc = _run(["config", "--get-all", key], cwd=root, check=False)
    if proc.returncode != 0:
        return []
    return [ln for ln in proc.stdout.decode("utf-8", "replace").splitlines() if ln.strip()]


def config_get(root: Path, key: str) -> str | None:
    values = config_get_all(root, key)
    return values[-1] if values else None


def config_set_global(key: str, value: str) -> None:
    """Persist a user-level setting (honors GIT_CONFIG_GLOBAL)."""
    _run(["config", "--global", key, value])


def write_file(root: Path, path: str, content: bytes | None, mode: int | None = None) -> None:
    """Write repo-relative `path` to `content`; None means delete the file."""
    abs_path = root / path
    if content is None:
        if abs_path.exists():
            abs_path.unlink()
        return
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = abs_path.with_name(abs_path.name + ".typethru-tmp")
    tmp.write_bytes(content)
    if mode is not None and os.name != "nt":
        os.chmod(tmp, mode)
    os.replace(tmp, abs_path)
