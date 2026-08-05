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
    built over `files`.

    Drives a shadow Session one keystroke at a time and records what it
    demanded, so the script stays correct for every typing feature (compose,
    delta regions, repeat fill) without duplicating engine logic."""
    settings = settings or rules.Settings(auto_globs=list(rules.DEFAULT_AUTO_GLOBS))
    shadow = engine.Session(files, settings, writer=None)
    shadow.start()
    keys: list[str] = []
    guard = 0
    while not shadow.finished:
        guard += 1
        assert guard < 100_000, "keystroke generator did not converge"
        line = shadow.current_line
        assert line is not None
        if line.complete:
            shadow.enter()
            keys.append("\r")
            continue
        expected = line.target[line.cursor]
        seq = engine.COMPOSE.get(expected, expected)
        key = seq[len(line.pending)] if expected in engine.COMPOSE else expected
        shadow.type_char(key)
        keys.append(key)
    assert shadow.stats.errors == 0, "generator produced a wrong key"
    return "".join(keys)
