"""Command-line entry point and session orchestration.

Commands:
    typethru                    gate mode (or resume, when a backup exists)
    typethru practice <rev>     read-only session over an existing commit/range
    typethru restore [--drop]   recover (or discard) the captured post-state
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

from . import __version__, backup, diffmodel, engine, gitio, rules, summary, tui

MIN_COLS, MIN_ROWS = 80, 24


class UsageError(Exception):
    """Printed as `typethru: <msg>` on stderr; exit code 2."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="typethru",
        description="Apply a git diff by retyping it.",
    )
    parser.add_argument("--version", action="version", version=f"typethru {__version__}")
    sub = parser.add_subparsers(dest="command")
    practice_p = sub.add_parser("practice", help="type an existing commit's diff, read-only")
    practice_p.add_argument("rev", help="commit, or range like A..B")
    restore_p = sub.add_parser("restore", help="recover the captured post-state from the last session")
    restore_p.add_argument("--drop", action="store_true", help="discard the backup, keep the tree as-is")
    args = parser.parse_args(argv)

    try:
        root = gitio.repo_root()
        if args.command == "restore":
            return cmd_restore(root, drop=args.drop)
        if args.command == "practice":
            return cmd_practice(root, args.rev)
        return cmd_gate(root)
    except (UsageError, gitio.GitError, backup.BackupError) as exc:
        print(f"typethru: {exc}", file=sys.stderr)
        return 2


# -- restore ---------------------------------------------------------------


def cmd_restore(root: Path, drop: bool) -> int:
    if not backup.exists(root):
        raise UsageError("no session backup found")
    if drop:
        backup.drop(root)
        print("backup discarded - working tree left as-is")
        return 0
    paths = backup.restore(root)
    print(f"restored the captured state of {len(paths)} file{'s' if len(paths) != 1 else ''}")
    return 0


# -- gate / resume ---------------------------------------------------------


def gate_files(root: Path):
    """Capture the pending worktree changes as FileDiffs.

    Returns (files, modes, left_alone). Raises UsageError on a clean tree.
    Deterministic given repo state; tests rely on that to script keystrokes.
    """
    entries = gitio.status_entries(root)
    untracked = [e.path for e in entries if e.index == "?"]
    left_alone = list(untracked) + [
        e.path + " (submodule)" for e in entries if e.submodule and e.index != "?"
    ]
    tracked = [
        e for e in entries
        if e.index != "?" and not e.submodule and (e.index.strip() or e.worktree.strip())
    ]
    files: list[diffmodel.FileDiff] = []
    modes: dict[str, int | None] = {}
    for entry in tracked:
        abs_path = root / entry.path
        target = abs_path.read_bytes() if abs_path.is_file() else None
        base = gitio.head_content(root, entry.path)
        if base == target:
            continue
        modes[entry.path] = abs_path.stat().st_mode if abs_path.is_file() else None
        files.append(diffmodel.compute_file_diff(entry.path, base, target))
    files = [fd for fd in files if fd.hunks]
    if not files:
        raise UsageError("working tree is clean - nothing to type")
    return files, modes, left_alone


def cmd_gate(root: Path, input=None, output=None) -> int:
    op = gitio.in_progress_operation(root)
    if op:
        raise UsageError(f"{op} in progress - finish it first")
    if backup.exists(root):
        return _resume(root, input=input, output=output)

    settings = rules.Settings.load(root)
    files, modes, left_alone = gate_files(root)

    session = engine.Session(files, settings, writer=_writer(root, modes))
    if not _has_typeable(session):
        raise UsageError("only binary or auto-apply changes pending - nothing to type (leave them to git as usual)")

    def on_begin() -> None:
        backup.create(root, [(fd.path, fd.target, modes.get(fd.path)) for fd in files])
        gitio.unstage(root, [fd.path for fd in files])
        for fd in files:
            gitio.write_file(root, fd.path, fd.base, modes.get(fd.path))
        session.start()

    config = tui.TuiConfig(
        mode="gate",
        plan=_plan_entries(session),
        untracked=left_alone,
        on_begin=on_begin,
    )
    return _run_session(root, session, files, config, input=input, output=output)


def _resume(root: Path, input=None, output=None) -> int:
    settings = rules.Settings.load(root)
    manifest = backup.load(root)
    files: list[diffmodel.FileDiff] = []
    modes: dict[str, int | None] = {}
    for bf in manifest:
        target = backup.target_content(root, bf)
        abs_path = root / bf.path
        base = abs_path.read_bytes() if abs_path.is_file() else None
        if base == target:
            continue
        modes[bf.path] = bf.mode
        files.append(diffmodel.compute_file_diff(bf.path, base, target))
    files = [fd for fd in files if fd.hunks]
    if not files:
        backup.drop(root)
        print("session already complete - backup cleared")
        return 0

    session = engine.Session(files, settings, writer=_writer(root, modes))
    config = tui.TuiConfig(
        mode="resume",
        plan=_plan_entries(session),
        untracked=[],
        on_begin=session.start,
    )
    return _run_session(root, session, files, config, input=input, output=output)


def _run_session(root, session, files, config, input=None, output=None) -> int:
    if input is None:
        _check_terminal()
    controller = tui.Controller(session, config)
    result = tui.run(controller, input=input, output=output)
    if result == "abort":
        print("aborted - nothing changed")
        return 0

    verified: bool | None = None
    if session.unresolved() == 0:
        verified = _verify(root, files)
        if verified:
            backup.drop(root)
    print(summary.render(session, "session", verified))
    if verified is False:
        return 1
    return 0 if session.unresolved() == 0 else 1


def _verify(root: Path, files) -> bool:
    for fd in files:
        abs_path = root / fd.path
        current = abs_path.read_bytes() if abs_path.is_file() else None
        if current != fd.target:
            return False
    return True


def _writer(root: Path, modes: dict[str, int | None]):
    def write(fd: diffmodel.FileDiff, applied: set[int]) -> None:
        gitio.write_file(root, fd.path, fd.reconstruct(applied), modes.get(fd.path))
    return write


def _has_typeable(session: engine.Session) -> bool:
    return any(item.auto_reason is None for item in session.items)


def _plan_entries(session: engine.Session) -> list[tui.PlanEntry]:
    by_path: dict[str, tui.PlanEntry] = {}
    for item in session.items:
        entry = by_path.setdefault(item.file.path, tui.PlanEntry(path=item.file.path, typeable=0, auto=0))
        if item.auto_reason is None:
            entry.typeable += 1
        else:
            entry.auto += 1
            if item.auto_reason not in entry.auto_reasons:
                entry.auto_reasons.append(item.auto_reason)
    return list(by_path.values())


# -- practice --------------------------------------------------------------


def cmd_practice(root: Path, spec: str, input=None, output=None) -> int:
    settings = rules.Settings.load(root)
    if re.search(r"\.\.", spec):
        base_spec, target_spec = re.split(r"\.{2,3}", spec, maxsplit=1)
    else:
        base_spec, target_spec = f"{spec}^", spec

    target_rev = gitio.rev_parse_commit(root, target_spec)
    if target_rev is None:
        raise UsageError(f"cannot resolve revision '{target_spec}'")
    base_rev = gitio.rev_parse_commit(root, base_spec)
    if base_rev is None:
        if "^" in base_spec and gitio.rev_parse_commit(root, base_spec.rstrip("^")) is not None:
            base_rev = gitio.empty_tree(root)  # root commit: diff against nothing
        else:
            raise UsageError(f"cannot resolve revision '{base_spec}'")

    files: list[diffmodel.FileDiff] = []
    for status, path in gitio.diff_name_status(root, base_rev, target_rev):
        base = gitio.rev_content(root, base_rev, path)
        target = gitio.rev_content(root, target_rev, path)
        if base == target:
            continue
        files.append(diffmodel.compute_file_diff(path, base, target))
    files = [fd for fd in files if fd.hunks]
    if not files:
        raise UsageError(f"no changes in '{spec}' - nothing to type")

    session = engine.Session(files, settings, writer=None)
    if not _has_typeable(session):
        raise UsageError(f"only binary or auto-apply changes in '{spec}' - nothing to type")
    config = tui.TuiConfig(
        mode="practice",
        plan=_plan_entries(session),
        untracked=[],
        on_begin=session.start,
        subtitle=spec,
    )
    if input is None:
        _check_terminal()
    controller = tui.Controller(session, config)
    result = tui.run(controller, input=input, output=output)
    if result == "abort":
        print("aborted")
        return 0
    print(summary.render(session, "practice", verified=None))
    return 0 if session.unresolved() == 0 else 1


# -- shared ----------------------------------------------------------------


def _check_terminal() -> None:
    if os.environ.get("TYPETHRU_SKIP_TERMINAL_CHECK"):
        return
    if not sys.stdin.isatty():
        raise UsageError("needs an interactive terminal - run typethru from a real terminal")
    size = shutil.get_terminal_size()
    if size.columns < MIN_COLS or size.lines < MIN_ROWS:
        raise UsageError(
            f"terminal too small (need {MIN_COLS}x{MIN_ROWS}, have {size.columns}x{size.lines})"
        )


if __name__ == "__main__":
    sys.exit(main())
