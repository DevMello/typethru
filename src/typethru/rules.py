"""Auto-apply classification.

A file or hunk is auto-applied when typing it would exercise fingers, not
comprehension: binary or non-UTF-8 content, deletions, lockfiles and other
generated paths, and whitespace-only hunks.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import PurePosixPath

from . import diffmodel, gitio

DEFAULT_AUTO_GLOBS = [
    "*.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "Cargo.lock",
    "uv.lock",
    "poetry.lock",
    "go.sum",
    "*.min.*",
    "dist/*",
    "build/*",
    "node_modules/*",
]


@dataclass
class Settings:
    auto_globs: list[str]
    auto_indent: bool = True
    live_stats: bool = True
    highlight: bool = True
    hints: bool = True
    delta: bool = True

    @classmethod
    def load(cls, root) -> "Settings":
        globs = list(DEFAULT_AUTO_GLOBS)
        globs.extend(gitio.config_get_all(root, "typethru.autoapply"))
        indent = gitio.config_get(root, "typethru.indent")
        return cls(
            auto_globs=globs,
            auto_indent=(indent != "type"),
            live_stats=_config_bool(root, "typethru.livestats", default=True),
            highlight=_config_bool(root, "typethru.highlight", default=True),
            hints=_config_bool(root, "typethru.hints", default=True),
            delta=_config_bool(root, "typethru.delta", default=True),
        )


def _config_bool(root, key: str, default: bool) -> bool:
    value = gitio.config_get(root, key)
    if value is None:
        return default
    return value.strip().lower() not in ("false", "off", "0", "no")


def path_auto_reason(path: str, globs: list[str]) -> str | None:
    """Return a reason string when `path` matches an auto-apply glob."""
    name = PurePosixPath(path).name
    for pattern in globs:
        if fnmatch(path, pattern) or fnmatch(name, pattern):
            return f"matches {pattern}"
    return None


def file_auto_reason(fd: diffmodel.FileDiff, settings: Settings) -> str | None:
    """File-level auto-apply reason, or None when the file is typeable."""
    if fd.target is None:
        return "file deleted"
    if diffmodel.is_binary(fd.base) or diffmodel.is_binary(fd.target):
        return "binary"
    if not diffmodel.is_utf8(fd.base) or not diffmodel.is_utf8(fd.target):
        return "not UTF-8"
    reason = path_auto_reason(fd.path, settings.auto_globs)
    if reason is not None:
        return reason
    return None


def hunk_auto_reason(hunk: diffmodel.Hunk) -> str | None:
    """Hunk-level auto-apply reason for hunks inside typeable files."""
    if not hunk.add_lines:
        return "deletion only"
    if hunk.is_whitespace_only():
        return "whitespace only"
    return None
