# typethru — SPEC

## One-liner

Applies a git diff to your working tree by making you retype the changed lines, with per-keystroke verification, so no agent-generated change lands without passing through your fingers.

## The gap

Developers who use AI coding agents but want to keep a mental model of their codebase have converged on the same workflow: **don't accept the diff — retype it**. Today they do it entirely by hand:

- Ankur Sethi, ["Prevent cognitive debt by manually retyping LLM-generated code"](https://ankursethi.com/blog/prevent-cognitive-debt-by-manually-retyping-llm-generated-code/) (HN front page 2026-08-03, 461 points / 373 comments, [thread](https://news.ycombinator.com/item?id=49153374)): configures his agents with "show me every proposed edit in the chat so I can type it in manually" and "do not run commands that modify project files".
- Ben Kamens, ["Code with AI the Hard Way"](https://kamens.com/blog/code-with-ai-the-hard-way): does a manual git dance — "grabbing the diff, reverting its changes without committing, and opening the diff to use as inspiration" — and writes "**I pine for ways to embrace the brilliance of AI coding tools while still typing things myself**", wishing for tools "buffering output to some other place I consume for inspiration".
- In the HN thread: TremendousJudge reviews "function by function" with write permissions off; danielvaughn retyped a generated TreeSitter grammar until he could write it unaided.
- gittype (the code-typing game, 1.5K stars) has an open, unimplemented feature request since 2025-09: "feat: add typing mode for git commit/diff added lines" — users asking for diff-typing even inside a game.
- Context: ["Don't be a meat proxy"](https://news.ycombinator.com/item?id=49151933) (1,724 points) — the accept-without-reading loop is the failure mode this workflow exists to avoid.

The workflow is real, practiced independently by multiple named people, and completely untooled: the state of the art is "revert the agent's edits, open the diff in a split, and type into the editor by hand, eyeballing for drift".

**Honesty note:** whether retyping produces comprehension is contested (same threads: jolt42, moffkalast argue typing without thinking teaches little). typethru does not claim pedagogy. It makes an existing, chosen practice ergonomic and safe. If you don't want the workflow, this tool is not for you.

## Prior art (and why it doesn't cover this)

| Tool | What it is | Why it's not this |
|---|---|---|
| hunk (modem-dev/hunk, 8.1K stars, active) | Review-first terminal diff viewer for agent code | Read-and-approve. No transcription; doesn't gate application on typing |
| tuicr (agavra/tuicr, 2.4K stars, active) | Code-review TUI, approve/reject hunks | Same category as hunk — reading, not typing |
| gittype (unhappychoice/gittype, 1.5K stars, active) | Typing *game* on snippets extracted from repos | Doesn't operate on diffs (open issue, unshipped); never modifies your tree; game framing (WPM ranks, themes) |
| `git add -p` / `git apply` | Hunk-level staging/application | Zero typing mechanics; one keypress accepts a hunk |
| typing.io, monkeytype, ttyper, retype-project | Typing practice tools | Practice corpora, not your pending diff; no application semantics |
| PyPI `retype` | Type-annotation migration tool | Unrelated; name coincidence |

Registry check (2026-08-04): `typethru` is unclaimed on PyPI, npm, and crates.io. GitHub searches for the primitive ("type diff apply", "retype llm code", "typing tutor diff", etc.) return nothing.

## Scope: in (v0.1.0)

1. **Gate mode** (`typethru`): capture the diff of tracked files (worktree vs HEAD, staged + unstaged), back up the post-state, revert to the pre-state, then run a hunk-by-hunk type-through session. Each completed hunk is spliced back into the file. When every hunk is typed or explicitly resolved, the worktree is byte-identical to what the agent left.
2. **Typing mechanics**: per-keystroke verification against the target line; wrong characters must be corrected before the line completes; leading indentation auto-fills (configurable); deletions and context lines are displayed, not typed. Per-hunk choices: type it, apply without typing (counted), or skip (leave unapplied).
3. **Safety**: the captured post-state is stored under `.git/typethru/` before anything is reverted. `typethru restore` recovers it at any point, including after a crash or Ctrl-C. The gate refuses to start if a previous session's backup exists un-restored.
4. **Auto-apply rules**: binary files, whitespace-only hunks, and configurable glob patterns (lockfiles, generated dirs) apply without typing and are reported as such.
5. **Practice mode** (`typethru practice <rev|range>`): the same typing session over an existing commit's diff, read-only — never touches the worktree.
6. **Session summary**: hunks typed / auto-applied / applied-untyped / skipped, character accuracy, WPM, elapsed time. Plain text, ASCII-only.

## Scope: out

- No LLM calls, API keys, or network access — ever.
- No comprehension quizzes, explanations, or AI-generated annotations.
- No scores, ranks, titles, streaks, leaderboards, or themes (gittype's turf).
- No editor or IDE integration; no watch mode or daemon.
- No GitHub/PR integration; no review comments.
- No patch-file input in v0.1 (git worktree and revision modes only).
- No merge-conflict states (refuses to run mid-merge/rebase with a clear message).
- No untracked-file discovery: new files the agent created are included only if added to the index (`git add -N` or staged); otherwise they are listed as "untracked, left alone".
- No submodule content sessions.
- No fuzzy/partial line matching — a line is done when it is exactly right.
- No config file formats beyond one optional `[tool.typethru]` table in `pyproject.toml` or `~/.config/typethru.toml` for auto-apply globs and indentation setting.

## Definition of done (run each; record observed output)

- **D1 — Byte-identity:** in a repo with programmatic multi-file edits (simulated agent run), a scripted session that types every hunk correctly ends with the worktree byte-identical to the agent's result (hash comparison), including CRLF/trailing-whitespace fidelity.
- **D2 — Verification:** a scripted session that sends wrong characters is blocked at the mistake; the wrong character is displayed as an error and must be corrected; the hunk cannot complete otherwise.
- **D3 — Per-hunk outcomes:** skipping hunk N leaves exactly hunk N unapplied in the file; applying-without-typing lands it and the summary counts typed/auto/applied-untyped/skipped correctly.
- **D4 — Crash safety:** killing the process mid-session leaves the backup intact; `typethru restore` recovers the full post-state exactly; the tool refuses to start a new gate session over an un-restored backup.
- **D5 — Auto-apply:** a whitespace-only hunk and a `package-lock.json` change apply without typing and are reported as auto-applied.
- **D6 — Practice ro:** `typethru practice HEAD~1..HEAD` runs a full session and the worktree hash is unchanged after.
- **D7 — Failure legibility:** not-a-git-repo, clean worktree, mid-merge state, binary-only diff, and non-UTF-8 file each produce a one-line actionable error and exit 2 (usage errors) — no tracebacks.
- **D8 — Fresh install:** `pip install .` in a clean venv on Python 3.10 and 3.12 provides the `typethru` command; `typethru --help` renders.

## Shape

Interactive terminal application (TUI) — structurally required: the product is keystroke-level interaction. Python >= 3.10, one pinned dependency (`prompt_toolkit`) for cross-platform keyboard/render handling; git operations via the `git` CLI (no libgit dependency). Windows, macOS, Linux.
