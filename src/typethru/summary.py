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
        "accuracy": stats.accuracy,
        "wpm": stats.wpm,
        "elapsed": round(stats.elapsed, 1),
        "files": session.typed_by_file(),
        "complete": session.unresolved() == 0,
        "verified": verified,
    }
