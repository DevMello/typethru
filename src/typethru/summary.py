"""Plain-text exit output (DESIGN.md: exit output)."""

from __future__ import annotations

from . import engine, history


def _fmt_elapsed(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s" if m else f"{s}s"


def render(session: engine.Session, mode: str, verified: bool | None) -> str:
    counts = session.counts()
    files = {item.file.path for item in session.items}
    total = len(session.items)
    lines = [f"typethru {mode} - {total} hunk{'s' if total != 1 else ''} in {len(files)} file{'s' if len(files) != 1 else ''}"]

    typed = counts[engine.TYPED]
    lines.append(f"  typed            {typed} hunk{'s' if typed != 1 else ''} ({session.typed_line_total()} lines)")
    if session.repeat_lines:
        lines.append(f"  repeated lines   {session.repeat_lines} auto-filled")

    auto = counts[engine.AUTO]
    if auto:
        reasons = sorted({item.auto_reason for item in session.items if item.outcome == engine.AUTO and item.auto_reason})
        lines.append(f"  auto-applied     {auto} hunk{'s' if auto != 1 else ''} ({', '.join(reasons)})")
    if counts[engine.APPLIED]:
        lines.append(f"  applied untyped  {counts[engine.APPLIED]} hunk{'s' if counts[engine.APPLIED] != 1 else ''}")
    if counts[engine.SKIPPED] or counts[engine.PENDING]:
        lines.append(f"  skipped          {counts[engine.SKIPPED] + counts[engine.PENDING]}")

    stats = session.stats
    parts = []
    if stats.accuracy is not None:
        parts.append(f"accuracy {stats.accuracy:.1f}%")
    if stats.wpm is not None:
        parts.append(f"{stats.wpm:.0f} wpm")
    parts.append(_fmt_elapsed(stats.elapsed))
    lines.append("  " + " - ".join(parts))

    if verified is True:
        lines.append("working tree matches the captured state (verified)")
        lines.append(f'receipt: {history.format_receipt(session_entry(session, verified))} ("typethru receipt" reprints)')
    elif verified is False:
        lines.append("warning: working tree does NOT match the captured state - backup kept, run \"typethru restore\"")
    unresolved = session.unresolved()
    if unresolved and mode == "session":
        lines.append(
            f'{unresolved} hunk{"s" if unresolved != 1 else ""} not applied - run "typethru" to continue or "typethru restore" to jump to the captured state'
        )
    return "\n".join(lines)


def render_practice_run(done: list[tuple[str, engine.Session]], total: int, skipped: int) -> str:
    """Aggregate summary for a multi-commit practice run."""
    lines = [f"typethru practice - {len(done)} of {total} commit{'s' if total != 1 else ''}"]
    for label, session in done:
        counts = session.counts()
        bits = [f"{counts[engine.TYPED]} hunk{'s' if counts[engine.TYPED] != 1 else ''} typed"]
        if session.stats.accuracy is not None:
            bits.append(f"{session.stats.accuracy:.1f}%")
        if session.unresolved():
            bits.append(f"{session.unresolved()} unresolved")
        lines.append(f"  {label[:48]:<48} {' - '.join(bits)}")
    if skipped:
        lines.append(f"  ({skipped} commit{'s' if skipped != 1 else ''} had nothing typeable)")
    sessions = [s for _, s in done]
    typed = sum(s.counts()[engine.TYPED] for s in sessions)
    line_total = sum(s.typed_line_total() for s in sessions)
    correct = sum(s.stats.correct for s in sessions)
    errors = sum(s.stats.errors for s in sessions)
    chars = sum(s.stats.typed_chars for s in sessions)
    elapsed = sum(s.stats.elapsed for s in sessions)
    parts = [f"total: {typed} hunk{'s' if typed != 1 else ''} ({line_total} lines)"]
    if correct + errors:
        parts.append(f"accuracy {correct / (correct + errors) * 100:.1f}%")
    if chars and elapsed > 0:
        parts.append(f"{chars / 5 / (elapsed / 60):.0f} wpm")
    parts.append(_fmt_elapsed(elapsed))
    lines.append("  " + " - ".join(parts))
    return "\n".join(lines)


def practice_run_entry(sessions: list[engine.Session]) -> dict:
    """One aggregate history record for a multi-commit practice run."""
    correct = sum(s.stats.correct for s in sessions)
    errors = sum(s.stats.errors for s in sessions)
    chars = sum(s.stats.typed_chars for s in sessions)
    elapsed = sum(s.stats.elapsed for s in sessions)
    files: dict[str, int] = {}
    for s in sessions:
        for path, count in s.typed_by_file().items():
            files[path] = files.get(path, 0) + count
    return {
        "mode": "practice",
        "hunks": {
            "typed": sum(s.counts()[engine.TYPED] for s in sessions),
            "auto": sum(s.counts()[engine.AUTO] for s in sessions),
            "applied": sum(s.counts()[engine.APPLIED] for s in sessions),
            "skipped": sum(s.unresolved() for s in sessions),
        },
        "lines_typed": sum(s.typed_line_total() for s in sessions),
        "repeat_lines": sum(s.repeat_lines for s in sessions),
        "accuracy": (correct / (correct + errors) * 100) if correct + errors else None,
        "wpm": (chars / 5 / (elapsed / 60)) if chars and elapsed > 0 else None,
        "elapsed": round(elapsed, 1),
        "files": files,
        "complete": all(s.unresolved() == 0 for s in sessions),
        "verified": None,
    }


def session_entry(session: engine.Session, verified: bool | None, mode: str = "session") -> dict:
    """The history-record shape for a finished session."""
    counts = session.counts()
    stats = session.stats
    return {
        "mode": mode,
        "hunks": {
            "typed": counts[engine.TYPED],
            "auto": counts[engine.AUTO],
            "applied": counts[engine.APPLIED],
            "skipped": counts[engine.SKIPPED] + counts[engine.PENDING],
        },
        "lines_typed": session.typed_line_total(),
        "repeat_lines": session.repeat_lines,
        "accuracy": stats.accuracy,
        "wpm": stats.wpm,
        "elapsed": round(stats.elapsed, 1),
        "files": session.typed_by_file(),
        "complete": session.unresolved() == 0,
        "verified": verified,
    }
