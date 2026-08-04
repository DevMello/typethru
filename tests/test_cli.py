"""Integration tests: real git repos, the real TUI driven through a pipe.

These are the SPEC.md definition-of-done checks D1-D8 in executable form.
"""

from __future__ import annotations

import pytest
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from typethru import backup, cli, rules
from conftest import commit_all, git, keystrokes_for

ENTER = "\r"
CTRL_A = "\x01"
CTRL_S = "\x13"
CTRL_Q = "\x11"


def run_gate(repo, keys: str) -> int:
    with create_pipe_input() as pipe:
        pipe.send_text(keys)
        pipe.close()
        return cli.cmd_gate(repo, input=pipe, output=DummyOutput())


def run_practice(repo, spec: str, keys: str) -> int:
    with create_pipe_input() as pipe:
        pipe.send_text(keys)
        pipe.close()
        return cli.cmd_practice(repo, spec, input=pipe, output=DummyOutput())


def tree_state(repo) -> dict[str, bytes]:
    out = {}
    for path in repo.rglob("*"):
        if path.is_file() and ".git" not in path.parts and ".typethru" not in path.name:
            out[path.relative_to(repo).as_posix()] = path.read_bytes()
    return out


@pytest.fixture
def agent_repo(repo):
    """A repo where a simulated agent has just edited several files."""
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_bytes(
        b"def greet(name):\n    return 'hi'\n\n\nprint(greet('x'))\n"
    )
    (repo / "crlf.txt").write_bytes(b"first\r\nsecond\r\nthird\r\n")
    (repo / "package-lock.json").write_bytes(b'{"version": 1}\n')
    (repo / "ws.py").write_bytes(b"x=1\n")
    (repo / "doomed.py").write_bytes(b"print('bye')\n")
    commit_all(repo, "base")

    # The "agent" edits:
    (repo / "src" / "app.py").write_bytes(
        b"def greet(name):\n    return f'hi {name}'\n\n\nprint(greet('x'))\n"
    )
    (repo / "crlf.txt").write_bytes(b"first\r\nSECOND!\r\nthird\r\n")
    (repo / "package-lock.json").write_bytes(b'{"version": 2}\n')
    (repo / "ws.py").write_bytes(b"x = 1\n")
    (repo / "doomed.py").unlink()
    (repo / "new_module.py").write_bytes(b"VALUE = 42\n")
    git(repo, "add", "-N", "new_module.py")
    return repo


class TestGateD1D5:
    def test_full_typed_session_restores_agent_state_exactly(self, agent_repo, capsys):
        agent_state = tree_state(agent_repo)
        files, modes, _ = cli.gate_files(agent_repo)
        keys = ENTER + keystrokes_for(files, rules.Settings.load(agent_repo))
        rc = run_gate(agent_repo, keys)
        assert rc == 0
        assert tree_state(agent_repo) == agent_state  # D1: byte-identical
        assert not backup.exists(agent_repo)
        out = capsys.readouterr().out
        assert "auto-applied" in out                   # D5 reported
        assert "matches the captured state (verified)" in out

    def test_wrong_chars_still_converge(self, agent_repo):
        """D2 at the app level: inject a wrong char + backspace mid-stream."""
        agent_state = tree_state(agent_repo)
        files, modes, _ = cli.gate_files(agent_repo)
        keys = keystrokes_for(files, rules.Settings.load(agent_repo))
        # Corrupt the stream: prepend a wrong char and a backspace before
        # the first real keystroke (wrong char is refused, backspace clears).
        keys = ENTER + "\x7f" + "~" + "\x7f" + keys
        rc = run_gate(agent_repo, keys)
        assert rc == 0
        assert tree_state(agent_repo) == agent_state

    def test_abort_from_plan_changes_nothing(self, agent_repo, capsys):
        before = tree_state(agent_repo)
        rc = run_gate(agent_repo, CTRL_Q)
        assert rc == 0
        assert tree_state(agent_repo) == before
        assert not backup.exists(agent_repo)
        assert "aborted - nothing changed" in capsys.readouterr().out


class TestComposeEndToEnd:
    def test_ai_punctuation_file_typed_through_pipe(self, repo):
        """A doc full of em dashes, curly quotes and ellipses — typed with
        only keys a keyboard has."""
        (repo / "NOTES.md").write_bytes(b"# Notes\n")
        commit_all(repo)
        agent_text = (
            "# Notes\n"
            "It’s not a bug — it’s a feature… “obviously”.\n"
            "Range 1–5 covered.\n"
        ).encode()
        (repo / "NOTES.md").write_bytes(agent_text)
        files, _, _ = cli.gate_files(repo)
        keys = ENTER + keystrokes_for(files, rules.Settings.load(repo))
        assert "—" not in keys and "’" not in keys and "…" not in keys
        rc = run_gate(repo, keys)
        assert rc == 0
        assert (repo / "NOTES.md").read_bytes() == agent_text


class TestSkipApplyResumeD3D4:
    @pytest.fixture
    def two_hunk_repo(self, repo):
        base = b"".join(b"line%d\n" % i for i in range(30))
        (repo / "f.py").write_bytes(base)
        commit_all(repo, "base")
        target = base.replace(b"line2\n", b"CHANGED2\n").replace(b"line25\n", b"CHANGED25\n")
        (repo / "f.py").write_bytes(target)
        return repo, base, target

    def test_skip_then_apply_untyped(self, two_hunk_repo, capsys):
        repo, base, target = two_hunk_repo
        rc = run_gate(repo, ENTER + CTRL_S + CTRL_A)
        assert rc == 1  # a hunk is unresolved
        content = (repo / "f.py").read_bytes()
        assert b"line2\n" in content          # skipped hunk not applied
        assert b"CHANGED25\n" in content      # applied-untyped hunk landed
        assert backup.exists(repo)            # backup retained
        out = capsys.readouterr().out
        assert "applied untyped  1 hunk" in out
        assert "skipped          1" in out
        assert 'run "typethru" to continue' in out

    def test_resume_completes_and_verifies(self, two_hunk_repo):
        repo, base, target = two_hunk_repo
        run_gate(repo, ENTER + CTRL_S + CTRL_A)
        # Resume: remaining diff is current tree -> captured target.
        from typethru.diffmodel import compute_file_diff
        current = (repo / "f.py").read_bytes()
        remaining = [compute_file_diff("f.py", current, target)]
        keys = ENTER + keystrokes_for(remaining, rules.Settings.load(repo))
        rc = run_gate(repo, keys)
        assert rc == 0
        assert (repo / "f.py").read_bytes() == target
        assert not backup.exists(repo)

    def test_quit_then_restore_recovers_agent_state(self, two_hunk_repo):
        repo, base, target = two_hunk_repo
        rc = run_gate(repo, ENTER + CTRL_Q)  # quit immediately after begin
        assert rc == 1
        assert backup.exists(repo)           # D4: backup survives the death
        rc = cli.cmd_restore(repo, drop=False)
        assert rc == 0
        assert (repo / "f.py").read_bytes() == target
        assert not backup.exists(repo)

    def test_restore_drop_keeps_tree(self, two_hunk_repo):
        repo, base, target = two_hunk_repo
        run_gate(repo, ENTER + CTRL_Q)
        current = (repo / "f.py").read_bytes()
        rc = cli.cmd_restore(repo, drop=True)
        assert rc == 0
        assert (repo / "f.py").read_bytes() == current
        assert not backup.exists(repo)


class TestPracticeD6:
    def test_practice_leaves_tree_untouched(self, repo, capsys):
        (repo / "a.py").write_bytes(b"def f():\n    return 1\n")
        commit_all(repo, "one")
        (repo / "a.py").write_bytes(b"def f():\n    return 2\n")
        commit_all(repo, "two")
        before = tree_state(repo)

        from typethru.diffmodel import compute_file_diff
        files = [
            compute_file_diff(
                "a.py", b"def f():\n    return 1\n", b"def f():\n    return 2\n"
            )
        ]
        keys = ENTER + keystrokes_for(files, rules.Settings.load(repo))
        rc = run_practice(repo, "HEAD~1..HEAD", keys)
        assert rc == 0
        assert tree_state(repo) == before
        status = git(repo, "status", "--porcelain").stdout
        assert status == b""
        assert "practice" in capsys.readouterr().out

    def test_practice_single_commit(self, repo):
        (repo / "a.py").write_bytes(b"x = 1\n")
        commit_all(repo, "one")
        (repo / "a.py").write_bytes(b"x = 1\ny = 2\n")
        commit_all(repo, "two")
        from typethru.diffmodel import compute_file_diff
        files = [compute_file_diff("a.py", b"x = 1\n", b"x = 1\ny = 2\n")]
        keys = ENTER + keystrokes_for(files, rules.Settings.load(repo))
        assert run_practice(repo, "HEAD", keys) == 0


class TestErrorsD7:
    def test_not_a_repo(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        rc = cli.main([])
        assert rc == 2
        assert "not a git repository" in capsys.readouterr().err

    def test_clean_tree(self, repo, monkeypatch, capsys):
        (repo / "a.py").write_bytes(b"x\n")
        commit_all(repo)
        monkeypatch.chdir(repo)
        rc = cli.main([])
        assert rc == 2
        assert "working tree is clean - nothing to type" in capsys.readouterr().err

    def test_merge_in_progress(self, repo, monkeypatch, capsys):
        (repo / "a.py").write_bytes(b"x\n")
        commit_all(repo)
        (repo / ".git" / "MERGE_HEAD").write_text("deadbeef\n")
        (repo / "a.py").write_bytes(b"y\n")
        monkeypatch.chdir(repo)
        rc = cli.main([])
        assert rc == 2
        assert "merge in progress - finish it first" in capsys.readouterr().err

    def test_only_auto_changes(self, repo, monkeypatch, capsys):
        (repo / "package-lock.json").write_bytes(b"{}\n")
        commit_all(repo)
        (repo / "package-lock.json").write_bytes(b'{"v":2}\n')
        monkeypatch.chdir(repo)
        rc = cli.main([])
        assert rc == 2
        assert "only binary or auto-apply changes" in capsys.readouterr().err

    def test_restore_without_backup(self, repo, monkeypatch, capsys):
        (repo / "a.py").write_bytes(b"x\n")
        commit_all(repo)
        monkeypatch.chdir(repo)
        rc = cli.main(["restore"])
        assert rc == 2
        assert "no session backup found" in capsys.readouterr().err

    def test_practice_bad_rev(self, repo, monkeypatch, capsys):
        (repo / "a.py").write_bytes(b"x\n")
        commit_all(repo)
        monkeypatch.chdir(repo)
        rc = cli.main(["practice", "nonexistent-branch"])
        assert rc == 2
        assert "cannot resolve revision" in capsys.readouterr().err

    def test_non_tty_stdin_refused_before_mutation(self, repo, monkeypatch, capsys):
        (repo / "a.py").write_bytes(b"x = 1\n")
        commit_all(repo)
        (repo / "a.py").write_bytes(b"x = 2\n")
        monkeypatch.chdir(repo)
        monkeypatch.delenv("TYPETHRU_SKIP_TERMINAL_CHECK", raising=False)
        rc = cli.main([])  # pytest's stdin is not a TTY
        assert rc == 2
        assert "needs an interactive terminal" in capsys.readouterr().err
        assert (repo / "a.py").read_bytes() == b"x = 2\n"  # nothing touched
        assert not backup.exists(repo)

    def test_binary_only_change(self, repo, monkeypatch, capsys):
        (repo / "img.bin").write_bytes(b"\x00\x01old")
        commit_all(repo)
        (repo / "img.bin").write_bytes(b"\x00\x01new")
        monkeypatch.chdir(repo)
        rc = cli.main([])
        assert rc == 2
        assert "only binary or auto-apply" in capsys.readouterr().err


class TestUnstagingAndIndex:
    def test_staged_changes_are_unstaged_for_session(self, repo):
        (repo / "a.py").write_bytes(b"x = 1\n")
        commit_all(repo)
        (repo / "a.py").write_bytes(b"x = 2\n")
        git(repo, "add", "a.py")
        files, _, _ = cli.gate_files(repo)
        keys = ENTER + keystrokes_for(files, rules.Settings.load(repo))
        rc = run_gate(repo, keys)
        assert rc == 0
        assert (repo / "a.py").read_bytes() == b"x = 2\n"
        # The change survived but is no longer staged.
        staged = git(repo, "diff", "--cached", "--name-only").stdout
        assert staged == b""
