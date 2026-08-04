# VERIFICATION — typethru

## v0.2.0 (2026-08-04)

Same method as v0.1.0 below: fresh clone to a scratch directory after the final feature commit, clean venvs, README followed with the documented PyPI adaptation, real TUI driven through `create_pipe_input`, user-level git config isolated via `GIT_CONFIG_GLOBAL`.

| Step | py3.12.4 | py3.10.8 (floor) |
|---|---|---|
| `pip install` from clean venv | exit 0 (editable) | exit 0 (wheel) |
| `pytest` (102 tests) | 102 passed | 102 passed |
| `typethru --version` | `typethru 0.2.0` | `typethru 0.2.0` |
| Feature walk (below) | 5/5 | 5/5 |

Observed feature walk (py3.10 shown; py3.12 identical):

- **V1 — Compose sequences.** A markdown file containing `’ — … “ ” –` was typed end-to-end through the real app using an ASCII-only keystream (`--`, `...`, straight quotes); exit 0, result byte-identical, `accuracy 100.0%`.
- **V2 — Live stats.** Mid-session footer observed: `[^A] apply  [^S] skip  [^Q] quit   100.0% 0wpm 0s   0 typed  0 auto  0 skipped`; with `livestats` off the footer reverts to keys + tally only.
- **V3 — Earned color.** Pygments fragments for `count = 42` reproduce the text exactly with ANSI-palette styles (`fg:ansimagenta` on `42`); the defensive exact-text check is exercised by the suite.
- **V4 — Compose hint.** `^N` during a session wrote `hints = false` to the (isolated) user-level git config; a fresh `Settings.load()` has hints off; session still completed exit 0.
- **V5 — v0.1 regression spot-check.** Quit mid-session leaves the backup; `typethru restore` recovers the captured bytes exactly.

The full v0.1.0 DoD walk items remain covered by the 102-test suite (byte-identity incl. CRLF, error blocking, skip/apply/resume, crash restore, auto-apply, read-only practice, all error paths). Scratch clone deleted after the gate.

---

# v0.1.0 record

Date: 2026-08-04. Platform: Windows 11, git 2.45.2. Run unattended; every result below is an observed output from an executed command, not an expectation.

## Method

1. Fresh clone of this repo to a scratch directory outside the working tree (after the final code commit; the gate was rerun in full following the one fix it caught).
2. README instructions followed literally, with one documented adaptation: the README's `pip install typethru` refers to PyPI, which this run does not publish to; the fresh-clone equivalents used were `pip install -e . pytest` (README Development section, py3.12) and a non-editable wheel install `pip install .` (py3.10, to exercise the packaged install path).
3. Interactive-flow evidence: the real prompt_toolkit `Application` was driven end to end through `create_pipe_input` (real key events through the real bindings, layouts and renderer, against real git repos). No human sat at a terminal during this unattended run; that is the one honesty caveat, and the non-TTY/EOF paths were verified explicitly instead.

## Environments

| Step | py3.12.4 | py3.10.8 (floor) |
|---|---|---|
| `pip install` from clean venv | exit 0 | exit 0 (wheel) |
| `pytest` (74 tests) | 74 passed in 11.66s | 74 passed in 11.66s |
| `typethru --version` | `typethru 0.1.0` | `typethru 0.1.0` |
| DoD walk (below) | 7/7 passed | 7/7 passed |

## Definition-of-done walk (SPEC.md), observed outputs (py3.10 wheel install)

**D1 — Byte-identity.** Repo with 5 agent-edited files (multi-line Python edit, CRLF file with trailing spaces, lockfile, whitespace-only change, file without trailing newline). Fully typed session, keys piped to the real app:

```
exit=0; hashes equal=True; backup dropped=True
typethru session - 5 hunks in 5 files
  typed            3 hunks (3 lines)
  auto-applied     2 hunks (matches package-lock.json, whitespace only)
  accuracy 100.0% - 4340 wpm - 0s
working tree matches the captured state (verified)
```

SHA-256 of every file equal to the captured agent state, including CRLF, trailing whitespace, and the missing final newline. (WPM is honest nonsense for piped input.)

**D2 — Verification.** Keystream `X`, `Enter`, `Backspace`, `b = 2`, `Enter`: the wrong `X` was held as a pending error, the early `Enter` was refused (file only converged because the later correct typing was accepted), final content `b'a = 1\nb = 2\n'`, summary `accuracy 83.3%` (5 correct, 1 error). Exit 0.

**D3 — Per-hunk outcomes.** Two-hunk file; keys `^S` then `^A`: hunk 1 (`line2`) still un-applied in the file, hunk 2 (`CHANGED25`) landed; summary `applied untyped 1 hunk / skipped 1`; exit 1 with `1 hunk not applied - run "typethru" to continue or "typethru restore" to jump to the captured state`. Resume-and-complete over a retained backup is covered by `test_resume_completes_and_verifies` (passed on both interpreters).

**D4 — Crash safety.** Input pipe died mid-line after session start ("process death"): worktree left at the reverted base (`b'one\ntwo\nthree\n'`), backup survived. `typethru restore` printed `restored the captured state of 1 file`; recovered bytes identical to the agent state; backup cleared. (First gate run caught a real bug here: the death path raised a raw EOFError traceback. Fixed - non-TTY stdin now refused before mutation, mid-session EOF ends as a quit - and the entire gate was rerun from a new fresh clone.)

**D5 — Auto-apply.** Observed in D1's summary: `auto-applied 2 hunks (matches package-lock.json, whitespace only)`; lockfile content was the agent version without any typing.

**D6 — Practice is read-only.** `practice HEAD~1..HEAD` fully typed: exit 0, tree hash unchanged, `git status --porcelain` empty.

**D7 — Failure legibility** (real `typethru.exe` binary, subprocess):

```
[not a repo]         exit=2  typethru: not a git repository (run inside the repo the agent edited)
[clean tree]         exit=2  typethru: working tree is clean - nothing to type
[merge in progress]  exit=2  typethru: merge in progress - finish it first
[binary-only diff]   exit=2  typethru: only binary or auto-apply changes pending - nothing to type (leave them to git as usual)
[restore, no backup] exit=2  typethru: no session backup found
[practice bad rev]   exit=2  typethru: cannot resolve revision 'no-such-rev'
[non-UTF-8 only diff] exit=2 typethru: only binary or auto-apply changes pending - nothing to type (leave them to git as usual)
```

No tracebacks on any case. Additionally `needs an interactive terminal` verified by test (non-TTY stdin, nothing mutated).

**D8 — Fresh install.** Clean venvs on 3.10 and 3.12; `pip install` exit 0; `typethru --help` renders the three-command usage (captured during the walk).

## Test suite shape

74 tests: diffmodel (splitting/hunking/reconstruction incl. CRLF and missing-newline round-trips), rules (globs, binary/non-UTF-8/deleted classification, whitespace-only hunks), engine (keystroke model: errors, backspace, Enter gating, auto-indent, trailing-whitespace autofill, blank lines, tabs, apply/skip/quit, stats), backup (roundtrip, restore-with-delete, double-create refusal), and CLI integration (real repos + real TUI via pipe: full typed session byte-identity, corrupted keystream convergence, plan abort, skip/apply/resume, quit-restore, restore --drop, practice modes, unstaging, and all error paths).

## Known honest gaps

- No human-at-keyboard session occurred in this run; interactive evidence is pipe-driven through the real application stack. First manual session may still surface cosmetic rendering issues (colors, cursor visibility) on specific terminals.
- Raw mintty (Git Bash without winpty) is refused by the TTY check rather than supported.
- Windows-only host for this gate; POSIX paths are exercised by CI-style tests only, not a live POSIX terminal.

Scratch clone deleted after the gate.
