# typethru

Apply a git diff by retyping it.

Your coding agent just rewrote four files. `typethru` reverts those changes, then feeds them back to you hunk by hunk: you retype each changed line, with every keystroke verified, until the working tree is byte-identical to what the agent produced. Nothing lands that didn't pass through your fingers.

```bash
pip install typethru && typethru
```

## Why

People who want to keep a mental model of their codebase while using AI agents have converged on the same workflow: don't accept the diff, retype it. Today they do it by hand — configuring agents to "show me every proposed edit in the chat so I can type it in manually" ([Ankur Sethi](https://ankursethi.com/blog/prevent-cognitive-debt-by-manually-retyping-llm-generated-code/)), or reverting the agent's edits and typing from the diff in a split ([Ben Kamens](https://kamens.com/blog/code-with-ai-the-hard-way): "I pine for ways to embrace the brilliance of AI coding tools while still typing things myself").

typethru is that workflow, made safe and ergonomic:

- **Byte-exact**: a finished session reproduces the agent's output exactly — CRLF, trailing whitespace, missing final newlines and all. Reconstruction splices the captured bytes; your typing is the gate, never the source of truth.
- **Crash-safe**: the agent's version is backed up under `.git/typethru/` before anything is reverted. `typethru restore` brings it back at any point, including after a crash.
- **No busywork**: lockfiles, generated paths, binary files, whitespace-only hunks and pure deletions apply automatically. Leading indentation and trailing whitespace are pre-filled. Pasting is ignored.
- **Not a game**: no ranks, streaks or live WPM. Accuracy and speed appear once, in the final summary.

Honesty note: whether retyping builds comprehension is debated. typethru takes no position — it serves people who have already chosen the practice. If reading diffs works for you, use a review tool like [hunk](https://github.com/modem-dev/hunk) instead.

## Install

```bash
pip install typethru
```

Python 3.10+, any platform with a terminal (Windows, macOS, Linux). Requires `git` on PATH. One dependency (`prompt_toolkit`).

## Use

**Gate mode** — after your agent has edited the working tree:

```bash
typethru
```

A plan screen lists what will be typed and what auto-applies, then the session begins. Per hunk: type the changed lines (`Enter` advances each completed line), or `Ctrl-A` to apply a hunk without typing, `Ctrl-S` to skip it, `Ctrl-Q` to quit. Quit or skip leaves the remaining hunks unapplied; rerun `typethru` to continue, or:

```bash
typethru restore        # jump straight to the agent's version
typethru restore --drop # discard the backup, keep the tree as-is
```

**Practice mode** — type an existing commit's diff, read-only:

```bash
typethru practice HEAD          # the last commit
typethru practice main..feature # any range
```

## Configuration

Via `git config`:

```bash
git config typethru.indent type                 # also type leading indentation (default: auto-filled)
git config --add typethru.autoapply "generated/*"  # extra auto-apply globs
```

Defaults auto-apply: `*.lock`, `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `Cargo.lock`, `uv.lock`, `poetry.lock`, `go.sum`, `*.min.*`, `dist/*`, `build/*`, `node_modules/*`. `NO_COLOR` is respected.

## Current limitations

- The session covers all tracked changes vs `HEAD` — it cannot separate pre-existing manual edits from the agent's. Run it when the pending diff is the thing you want to earn back.
- New files are included only when git knows about them (`git add -N newfile.py`); untracked files are listed and left alone.
- Staged changes are unstaged for the session (re-stage with `git add` afterwards).
- Renames appear as a deletion plus a new file. Merge/rebase states are refused. Submodules are left alone.
- Minimum terminal size 80x24. As a full-screen TUI it is not usable with a screen reader; there is no non-visual equivalent in v0.1.

## Development

```bash
git clone https://github.com/DevMello/typethru && cd typethru
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e . pytest
pytest
```

MIT. See `SPEC.md` for scope, `DECISIONS.md` for the reasoning behind the sharp edges.
