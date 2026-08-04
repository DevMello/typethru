# DESIGN — typethru terminal grammar

Register: product. Surface: full-screen TUI plus plain-text exit output. This document locks the screen grammar before implementation; the component structure follows it.

## Theme

Scene sentence: a developer at 11pm in a dim room, inside the terminal theme they already live in, doing focused transcription for 2 to 20 minutes. Verdict: **typethru has no theme — it inherits the user's**. Never set a background color; never assume dark or light. All styling is expressed as ANSI attributes (default ink, dim, bold, reverse, and the named colors red/green), which every terminal palette remaps to itself. This is the Restrained strategy translated to a TTY: tinted-neutral equivalent = the user's own palette; accent budget spent only on red (errors, deletions) and green (earned lines, final verdict).

## Inks

| Ink | ANSI | Used for | Never used for |
|---|---|---|---|
| default | (none) | code being typed, file path (bold) | chrome |
| dim | `\e[2m` | context lines, untyped ghost text, all chrome labels, key hints | errors |
| red | 31 | mistyped character cells (with reverse), deletion lines and their `-` marker | anything decorative |
| green | 32 | `+` marker of completed lines, final "matches captured state" verdict | progress bars, celebration |

Monochrome / `NO_COLOR` degradation: red -> reverse video, green -> bold; `-`/`+` markers and position carry every meaning on their own. No information is color-only.

## Screen regions (min 80x24)

```
typethru  src/parser.py  hunk 3/9                                       line 2/5

   140     def parse_hunk(lines):
   141  -      return [l for l in lines if l]
   142  +  result = []
   143  +  for line in lines:_                        <- typed part default, rest dim
   144  +      if line.strip():

[^A] apply as-is   [^S] skip hunk   [^Q] quit                 3 typed - 1 auto
```

1. **Header (1 line):** `typethru` dim, file path bold, `hunk m/n` dim; right-aligned `line j/k`. Positional only, never a percentage, never a grade.
2. **Body:** the current hunk, one screen line per diff line. Gutter = 6-char line number (position in the resulting file; blank for deletions) + 2-char marker column (`-` red, `+` green when the line is done, dim `+` when pending) + 2 spaces. No frames, no box drawing; separation is whitespace. Long lines truncate with a dim `>` in the last column (typing continues past the fold; the view scrolls horizontally to keep the cursor visible).
3. **Active line:** typed prefix in default ink, wrong characters as red reverse cells (they occupy the cell they tried to fill), block cursor at the insertion point, untyped remainder dim. Pre-filled indentation renders in default ink immediately.
4. **Footer (1 line):** key chords left, dim, in the fixed order apply / skip / quit. Right: running tally `N typed - N auto - N skipped`, dim, counts only.
5. Hunks that don't fit vertically scroll to keep the active line in the middle third. No other region ever moves.

## Flow

- **Plan screen (gate mode only):** before any mutation, one plain screen: list of files with hunk counts, auto-apply annotations (`auto: lockfile`, `auto: whitespace`), the sentence `Your working tree will be reverted while you type. Backup: .git/typethru/`, then `Enter begin - ^Q abort`. Abort leaves the tree untouched.
- **Session:** hunks strictly sequential; a completed hunk advances automatically after its last line's Enter. No inter-hunk ceremony.
- **Exit output (all modes, printed after leaving the alternate screen):** plain ASCII lines, human- and script-readable:

```
typethru session - 9 hunks in 4 files
  typed            6 hunks (142 lines)
  auto-applied     2 hunks (lockfile, whitespace)
  applied untyped  1 hunk
  skipped          0
  accuracy 97.4% - 41 wpm - 12m30s
working tree matches the captured state (verified)
```

Accuracy and WPM appear here only, past tense. In practice mode the header gains `practice <range> - read-only` and the verdict line is omitted. If hunks remain (quit/skip): `3 hunks not applied - run "typethru" to continue or "typethru restore" to jump to the captured state`, exit code 1.

## Keys (complete set, v0.1)

| Key | Meaning |
|---|---|
| printable char | type it (Tab types a literal tab where the target has one) |
| Backspace | delete last typed character (not into pre-filled indent) |
| Enter | advance when the line is exactly complete; otherwise no-op |
| Ctrl-A | apply current hunk without typing (counted as such) |
| Ctrl-S | skip current hunk (left unapplied) |
| Ctrl-Q / Ctrl-C | end session; typed hunks stay, summary prints, backup retained |

No modes, no remapping, no hidden chords.

## Error copy (exit 2, one line, stderr)

- `typethru: not a git repository (run inside the repo the agent edited)`
- `typethru: working tree is clean - nothing to type`
- `typethru: merge or rebase in progress - finish it first`
- `typethru: unfinished session backup found - run "typethru restore" (recover captured state) or "typethru restore --drop" (keep tree as-is)`
- `typethru: only binary or auto-apply changes pending - nothing to type (use "git add" as usual)`
- `typethru: terminal too small (need 80x24, have {w}x{h})`
- `typethru: needs an interactive terminal - run typethru from a real terminal`

Pattern: `typethru: <what> - <what to do>`. No stack traces on any user-reachable path.

## v0.2 revisions

- **Live stats (operator-requested).** v0.1 held that accuracy and WPM appear only in the final summary. v0.2 shows `accuracy wpm elapsed` in the footer by default, dim, between the key hints and the tally. The principle ("progress is positional, not judgmental") loses this round to the operator's preference for feedback; the compromise is placement and ink — it sits at the screen edge, in chrome gray, and never animates beyond a once-per-second repaint. `git config typethru.livestats false` restores the v0.1 quiet footer.
- **Compose hints.** Characters without keys (em/en dash, ellipsis, curly quotes, NBSP) accept compose sequences; the pending partial renders in default ink at the cursor. The column shift when `--` collapses into `—` is accepted (same class as the error-cell shift). A dim one-line hint (`hint: type — as --, ...`) sits above the footer whenever the current hunk contains a composable character; `^N` dismisses it permanently (user-level git config). The hint is chrome, so it lives at the screen edge in dim ink and appears/disappears only on hunk transitions, never mid-line.
- **Earned color (syntax highlighting).** Completed add lines render with ANSI-palette syntax highlighting; the active line and ghosts stay monochrome. Color arrives when a line is done — highlighting doubles as the completion state. `git config typethru.highlight false` or `NO_COLOR` disables.

## Refinement log

- **critique:** first draft had a live WPM counter in the footer; removed - grades mid-session violate principle 2 (quieter). Box-drawing frame around the hunk removed - dashboard chrome anti-reference; whitespace separates.
- **polish:** gutter reduced from old+new line numbers to a single resulting-file number; deletions get a blank number, keeping the eye on where code lands, not where it came from.
- **distill:** dropped per-line checkmarks (a completed line's full brightness IS its state), dropped press-any-key between hunks, dropped any start-screen art. The plan screen survives distill because it is consent, not decoration.
- **quieter:** completion verdict is one green line, not a banner; the tally never uses exclamation marks.
- **implementation review (fragment render check):** the active line's `+` marker stays dim until the line is done (green is earned, not anticipated). Two accepted deviations: the footer tally sits after a fixed gap rather than hard right-aligned (one control, no width math), and the "dim" ink is realized as ANSI bright-black because prompt_toolkit has no dim attribute; in `NO_COLOR` mode ghosts fall back to default ink and position/markers carry the state. Pasting is ignored via a bracketed-paste no-op binding: the point is typing.
