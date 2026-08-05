"""Session history: one JSON line per finished session, per repository.

Lives at `.git/typethru/history.jsonl`, beside (never inside) the backup.
Everything here is best-effort: a failure to record history must never
break a session that just finished.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

from . import backup

HISTORY = "history.jsonl"

DEFAULT_WPM = 40.0
# Piped/robot sessions produce absurd WPM; estimates stay believable.
ESTIMATE_WPM_FLOOR = 10.0
ESTIMATE_WPM_CAP = 120.0


def history_path(root: Path) -> Path:
    return backup.state_dir(root) / HISTORY


def record(root: Path, entry: dict) -> None:
    """Append one session entry; best-effort."""
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **entry}
    try:
        path = history_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError as exc:
        print(f"typethru: could not record session history: {exc}", file=sys.stderr)


def load(root: Path) -> list[dict]:
    path = history_path(root)
    if not path.exists():
        return []
    entries: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue  # a corrupt line loses one session, not the log
            if isinstance(parsed, dict):
                entries.append(parsed)
    except OSError:
        return []
    return entries


def median_wpm(root: Path) -> float:
    """Median WPM of recent sessions, clamped to a believable estimation
    range; DEFAULT_WPM when there is no usable history."""
    values = [
        e["wpm"] for e in load(root)[-10:]
        if isinstance(e.get("wpm"), (int, float)) and e["wpm"] > 0
    ]
    if not values:
        return DEFAULT_WPM
    return min(max(statistics.median(values), ESTIMATE_WPM_FLOOR), ESTIMATE_WPM_CAP)


def last_receipt(root: Path) -> str | None:
    """The trailer for the most recent complete, verified gate session."""
    for entry in reversed(load(root)):
        if entry.get("mode") == "practice" or not entry.get("complete"):
            continue
        if entry.get("verified") is not True:
            continue
        return format_receipt(entry)
    return None


def format_receipt(entry: dict) -> str:
    hunks = entry.get("hunks", {})
    typed = hunks.get("typed", 0)
    auto = hunks.get("auto", 0)
    applied = hunks.get("applied", 0)
    total = typed + auto + applied + hunks.get("skipped", 0)
    parts = [f"Typed-thru: {typed}/{total} hunks"]
    extras = []
    if auto:
        extras.append(f"{auto} auto")
    if applied:
        extras.append(f"{applied} untyped")
    if extras:
        parts[0] += f" ({', '.join(extras)})"
    if isinstance(entry.get("accuracy"), (int, float)):
        parts.append(f"accuracy {entry['accuracy']:.1f}%")
    if isinstance(entry.get("wpm"), (int, float)):
        parts.append(f"{entry['wpm']:.0f} wpm")
    return ", ".join(parts)
