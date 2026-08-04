# Product

## Register

product

## Users

A developer at 11pm who just watched their coding agent rewrite four files, and wants to earn that diff back before it becomes their code. Terminal-native, keyboard-only, often tired, often in a dim room, on Windows Terminal, iTerm2, or a Linux console over SSH. They chose a deliberately slower workflow on purpose; the tool's job is to remove every cost of that choice except the typing itself.

They are mid-session when typethru runs: the agent has finished, the diff is pending, and the next thing they do is either absorb it or regret it. Sessions run 2 to 20 minutes. Interruption is normal (Ctrl-C, laptop lid); resuming safely matters more than finishing fast.

## Product Purpose

typethru applies a git diff by having the developer retype the changed lines with per-keystroke verification. Success: the working tree ends byte-identical to what the agent produced, and the developer can say where every change lives. It replaces a manual ritual (revert the diff, open it in a split, type into the editor, eyeball for drift) practiced by real people today with zero tooling.

## Brand Personality

Calm, exacting, quiet. The feeling to evoke is the one the workflow itself is about: unhurried attention. The user is doing focused transcription work; the interface is a well-lit desk, not a coach, not a game show. Earned confidence at the end, never celebration.

## Anti-references

- Monkeytype and typing-race aesthetics: neon accents, live WPM counters ticking in the corner, confetti. Nothing races the user.
- gittype's game framing: ranks, developer titles, ASCII-art trophies, streaks. typethru has no opinion about how good you are.
- CI walls of red: error states that shame. A mistyped character is information about one character, rendered at one character's scale.
- Dense dashboard chrome: box-drawing borders around everything, double-line frames, badges. The typing surface should be the quietest, emptiest region on screen.

## Design Principles

1. **The typing surface is sacred.** Nothing animates, ticks, or repaints near the cursor except the user's own keystrokes. All meta-information (progress, file name, keys) lives at the screen edges.
2. **Progress is positional, not judgmental.** Show where you are (hunk 3 of 9, line 2 of 5); never grade mid-session. Accuracy and WPM appear once, in the final summary, in past tense.
3. **Errors are one character big.** A wrong keystroke marks that character and waits. No flashing, no sound, no message. Correcting it erases the record from the screen (the summary still counts it, honestly).
4. **Leave the terminal like we found it.** Alternate screen, restored on every exit path including crashes; scrollback intact; exit output is plain lines a human or script can read.
5. **Every keystroke has exactly one meaning.** Printable characters type. A short, fixed set of control chords does everything else, displayed on screen at all times. No modes, no vim-emulation, no configurable keymaps in v0.1.

## Accessibility & Inclusion

- Never color-only: every state that uses color also differs by glyph or position (errors are marked by the character cell itself plus a gutter marker; deletions carry a `-` prefix).
- Respects `NO_COLOR` and low-color terminals: full session works in monochrome via weight and glyphs.
- Minimum 80x24 terminal; degrade by truncating chrome, never the code line being typed.
- No animation anywhere, so reduced-motion is the default state, not a mode.
- Honest limitation, documented in README: a full-screen typing TUI is not usable with a screen reader; the practice and gate flows have no non-visual equivalent in v0.1.
