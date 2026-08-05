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
- **Delta typing**: when the agent rewrote a line rather than wrote a new one, the unchanged prefix and suffix pre-fill and you type only the span that changed. A one-variable rename costs you one variable, not sixty characters (`git config typethru.delta false` to always type full lines).
- **Repeat fill**: a line you already typed verbatim this session pre-fills on its next appearance - Enter accepts it. Repetition isn't comprehension (`git config typethru.repeatfill false`).
- **Estimated typing time**: the plan screen prices each file (`~4m`) and the whole session at your historical median WPM, so "apply as-is" is a decision made with information. A generated migration that would cost 3.2 hours says so up front.
- **AI punctuation is typeable**: model output is full of characters keyboards don't have. Compose them from keys you do have: `--` produces an em or en dash (`—` `–`), `...` produces an ellipsis (`…`), straight quotes produce curly ones (`'` -> `’`, `"` -> `“`), space produces a non-breaking space. Typing the real character directly also works, if you know the incantation for your OS. A one-line hint appears whenever the current hunk contains such a character; `Ctrl-N` dismisses it forever (persisted via `git config --global typethru.hints false`).
- **Not a game**: no ranks, no streaks, no confetti. The footer shows live accuracy, WPM and elapsed time (turn it off with `git config typethru.livestats false` if you'd rather find out at the end).
- **Earned color**: lines you've completed render with syntax highlighting (hundreds of languages via Pygments, detected from the filename); untyped ghost text stays gray. Color arrives as you finish each line. `git config typethru.highlight false` or `NO_COLOR` disables it.

Honesty note: whether retyping builds comprehension is debated. typethru takes no position — it serves people who have already chosen the practice. If reading diffs works for you, use a review tool like [hunk](https://github.com/modem-dev/hunk) instead.

## Install

```bash
pip install typethru
```

Python 3.10+, any platform with a terminal (Windows, macOS, Linux). Requires `git` on PATH. Two dependencies (`prompt_toolkit`, `pygments`).

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

During a session `Ctrl-E` widens the current hunk's context window by five lines per press, when three lines aren't enough to tell what a change means.

**Practice mode** — type existing commits' diffs, read-only:

```bash
typethru practice HEAD              # the last commit
typethru practice main..feature     # any range
typethru practice -n 20 --path src/auth  # the last 20 commits that touched a subsystem, oldest first
```

The `-n` form runs one session per commit with the commit named in the header — typing your way through the history of an unfamiliar area is a genuinely good way to meet a codebase.

**Stats and receipts**:

```bash
typethru stats    # lines typed, time at the keys, accuracy, most-retyped files - past tense, no streaks
typethru receipt  # "Typed-thru: 9/9 hunks, accuracy 97.4%, 41 wpm" for your commit message
```

Every session is recorded in `.git/typethru/history.jsonl` (local, per-repo, never transmitted). After a fully-typed, verified session the summary offers the receipt line — paste it into a commit message as a small, honest "I actually read this" stamp.

## Configuration

Via `git config`:

```bash
git config typethru.indent type                 # also type leading indentation (default: auto-filled)
git config --add typethru.autoapply "generated/*"  # extra auto-apply globs
git config typethru.livestats false             # no live accuracy/wpm/elapsed in the footer
git config typethru.highlight false             # no syntax highlighting on completed lines
git config typethru.delta false                 # always type full lines, never just the changed span
git config typethru.repeatfill false            # repeated lines must be typed every time
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
