from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from typethru import engine, rules


def git(repo: Path, *args: str, data: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=repo, input=data, capture_output=True, check=True
    )


@pytest.fixture(autouse=True)
def isolated_global_config(tmp_path_factory, monkeypatch):
    """Point git's --global scope at a throwaway file so hint dismissal
    (and any other user-level write) never touches the real ~/.gitconfig."""
    path = tmp_path_factory.mktemp("gitconfig") / "config"
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(path))
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.name", "Test")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "commit.gpgsign", "false")
    git(path, "config", "core.autocrlf", "false")
    return path


def commit_all(repo: Path, message: str = "commit") -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


def keystrokes_for(files, settings: rules.Settings | None = None) -> str:
    """The exact key sequence that types every pending hunk of a session
    built over `files`, mirroring the CLI's deterministic construction."""
    settings = settings or rules.Settings(auto_globs=list(rules.DEFAULT_AUTO_GLOBS))
    shadow = engine.Session(files, settings, writer=None)
    keys: list[str] = []
    for item in shadow.items:
        if item.auto_reason is not None:
            continue
        for line in item.hunk.add_lines:
            text = line.text
            if text.strip():
                start = len(text) - len(text.lstrip()) if settings.auto_indent else 0
                end = len(text.rstrip())
                for ch in text[start:end]:
                    keys.append(engine.COMPOSE.get(ch, ch))
            keys.append("\r")
    return "".join(keys)
