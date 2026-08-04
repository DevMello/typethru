"""Session state machine.

Pure logic: no terminal, no git, no filesystem. The TUI feeds keystrokes in
and renders state out; the CLI supplies a writer callback that persists a
file whenever one of its hunks is applied. Tests drive this directly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from .diffmodel import DiffLine, FileDiff, Hunk
from .rules import Settings, file_auto_reason, hunk_auto_reason

# Item outcomes
PENDING = "pending"
TYPED = "typed"
AUTO = "auto"
APPLIED = "applied"   # applied without typing (Ctrl-A)
SKIPPED = "skipped"

# Characters AI output is full of and keyboards are not. Each maps to the key
# sequence that produces it; a prefix of the sequence is held as a pending
# partial until it completes or a wrong key lands as an error.
COMPOSE = {
    "—": "--",    # em dash
    "–": "--",    # en dash
    "…": "...",   # ellipsis
    "‘": "'",     # left single curly quote
    "’": "'",     # right single curly quote (the apostrophe AI loves)
    "“": '"',     # left double curly quote
    "”": '"',     # right double curly quote
    " ": " ",     # non-breaking space
}


@dataclass
class SessionItem:
    file: FileDiff
    hunk: Hunk
    auto_reason: str | None = None
    outcome: str = PENDING


@dataclass
class LineState:
    target: str            # full decoded line content, no newline
    start: int             # first index the user must type (after auto-indent)
    end: int               # one past the last index the user must type
    typed: int = 0         # correctly typed chars, absolute index = start + typed
    error: str | None = None  # pending wrong character, shown at the cursor cell
    pending: str = ""      # partial compose sequence for the expected character

    @property
    def cursor(self) -> int:
        return self.start + self.typed

    @property
    def complete(self) -> bool:
        return self.cursor >= self.end and self.error is None and not self.pending


@dataclass
class Stats:
    correct: int = 0
    errors: int = 0
    typed_chars: int = 0
    started: float = field(default_factory=time.monotonic)
    ended: float | None = None

    @property
    def elapsed(self) -> float:
        end = self.ended if self.ended is not None else time.monotonic()
        return max(end - self.started, 0.0)

    @property
    def accuracy(self) -> float | None:
        total = self.correct + self.errors
        return (self.correct / total * 100.0) if total else None

    @property
    def wpm(self) -> float | None:
        minutes = self.elapsed / 60.0
        if minutes <= 0 or not self.typed_chars:
            return None
        return (self.typed_chars / 5.0) / minutes


class Session:
    """Drives one gate or practice session over a list of FileDiffs."""

    def __init__(
        self,
        files: list[FileDiff],
        settings: Settings,
        writer: Callable[[FileDiff, set[int]], None] | None = None,
    ) -> None:
        self.settings = settings
        self.writer = writer
        self.items: list[SessionItem] = []
        self.applied: dict[str, set[int]] = {}
        self.stats = Stats()
        self.finished = False
        for fd in files:
            self.applied[fd.path] = set()
            freason = file_auto_reason(fd, settings)
            for hunk in fd.hunks:
                reason = freason or hunk_auto_reason(hunk)
                self.items.append(SessionItem(file=fd, hunk=hunk, auto_reason=reason))
        self._pos = 0
        self._line_idx = 0
        self._line: LineState | None = None

    # -- session lifecycle -------------------------------------------------

    def start(self) -> None:
        """Resolve auto items, then position on the first typeable hunk."""
        for item in self.items:
            if item.auto_reason is not None:
                item.outcome = AUTO
                self._apply(item)
        self._advance_to_pending(from_index=0)

    def _advance_to_pending(self, from_index: int) -> None:
        for i in range(from_index, len(self.items)):
            if self.items[i].outcome == PENDING:
                self._pos = i
                self._line_idx = 0
                self._load_line()
                return
        self._pos = len(self.items)
        self._line = None
        self._finish()

    def _finish(self) -> None:
        if not self.finished:
            self.finished = True
            self.stats.ended = time.monotonic()

    # -- current position --------------------------------------------------

    @property
    def current(self) -> SessionItem | None:
        if self._pos < len(self.items):
            return self.items[self._pos]
        return None

    @property
    def current_line(self) -> LineState | None:
        return self._line

    @property
    def current_line_index(self) -> int:
        return self._line_idx

    def add_lines(self) -> list[DiffLine]:
        item = self.current
        return item.hunk.add_lines if item else []

    def _load_line(self) -> None:
        adds = self.add_lines()
        if self._line_idx >= len(adds):
            self._line = None
            return
        target = adds[self._line_idx].text
        if target.strip():
            start = (len(target) - len(target.lstrip())) if self.settings.auto_indent else 0
            end = len(target.rstrip())
        else:
            # Blank or whitespace-only line: nothing to type, Enter advances.
            start = end = 0
        self._line = LineState(target=target, start=start, end=end)

    # -- keystrokes --------------------------------------------------------

    def type_char(self, char: str) -> None:
        line = self._line
        if line is None or self.finished:
            return
        if line.cursor >= line.end:
            # Line already complete except Enter; extra typing is an error.
            self.stats.errors += 1
            line.error = char
            return
        expected = line.target[line.cursor]
        if not line.pending and char == expected:
            self._accept(line, advance=True)
            return
        seq = COMPOSE.get(expected)
        if seq is not None:
            candidate = line.pending + char
            if candidate == seq:
                line.pending = ""
                self._accept(line, advance=True)
                return
            if seq.startswith(candidate):
                line.pending = candidate
                self._accept(line, advance=False)
                return
        self.stats.errors += 1
        line.error = char

    def _accept(self, line: LineState, advance: bool) -> None:
        if line.error is not None:
            line.error = None
        if advance:
            line.typed += 1
        self.stats.correct += 1
        self.stats.typed_chars += 1

    def backspace(self) -> None:
        line = self._line
        if line is None or self.finished:
            return
        if line.error is not None:
            line.error = None
        elif line.pending:
            line.pending = line.pending[:-1]
        elif line.typed > 0:
            line.typed -= 1

    def enter(self) -> None:
        line = self._line
        if line is None or self.finished:
            return
        if not line.complete:
            return
        self._line_idx += 1
        adds = self.add_lines()
        if self._line_idx >= len(adds):
            item = self.current
            assert item is not None
            item.outcome = TYPED
            self._apply(item)
            self._advance_to_pending(self._pos + 1)
        else:
            self._load_line()

    def apply_current(self) -> None:
        item = self.current
        if item is None or self.finished:
            return
        item.outcome = APPLIED
        self._apply(item)
        self._advance_to_pending(self._pos + 1)

    def skip_current(self) -> None:
        item = self.current
        if item is None or self.finished:
            return
        item.outcome = SKIPPED
        self._advance_to_pending(self._pos + 1)

    def quit(self) -> None:
        self._finish()

    # -- application -------------------------------------------------------

    def _apply(self, item: SessionItem) -> None:
        self.applied[item.file.path].add(item.hunk.index)
        if self.writer is not None:
            self.writer(item.file, self.applied[item.file.path])

    # -- reporting ---------------------------------------------------------

    def counts(self) -> dict[str, int]:
        out = {TYPED: 0, AUTO: 0, APPLIED: 0, SKIPPED: 0, PENDING: 0}
        for item in self.items:
            out[item.outcome] += 1
        return out

    def typed_line_total(self) -> int:
        return sum(
            len(item.hunk.add_lines) for item in self.items if item.outcome == TYPED
        )

    def unresolved(self) -> int:
        c = self.counts()
        return c[SKIPPED] + c[PENDING]
