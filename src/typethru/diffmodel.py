"""Diff computation and byte-exact reconstruction.

typethru never parses unified diff text. A session holds the full base and
target contents of every file; hunks are derived with difflib and applying a
hunk means selecting the target lines for that region. Because reconstruction
always splices original bytes, "all hunks applied" is byte-identical to the
captured target by construction (DECISIONS.md #18).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

CONTEXT = 3


def split_lines(data: bytes) -> list[bytes]:
    """Split into lines keeping line endings; preserves CRLF and a missing
    trailing newline exactly."""
    if not data:
        return []
    lines = data.split(b"\n")
    out = [line + b"\n" for line in lines[:-1]]
    if lines[-1] != b"":
        out.append(lines[-1])
    return out


@dataclass(frozen=True)
class DiffLine:
    kind: str            # "ctx" | "del" | "add"
    data: bytes          # raw line bytes including any newline
    target_lineno: int | None  # 1-based line number in the target file (ctx/add)
    paired_data: bytes | None = None  # replaced base line this add corresponds to

    @property
    def text(self) -> str:
        return self.data.decode("utf-8").rstrip("\r\n")

    @property
    def paired_text(self) -> str | None:
        if self.paired_data is None:
            return None
        try:
            return self.paired_data.decode("utf-8").rstrip("\r\n")
        except UnicodeDecodeError:
            return None


@dataclass
class Hunk:
    index: int                     # 0-based within the file
    base_span: tuple[int, int]     # [start, end) line indices in base
    target_span: tuple[int, int]   # [start, end) line indices in target
    display: list[DiffLine] = field(default_factory=list)

    @property
    def add_lines(self) -> list[DiffLine]:
        return [ln for ln in self.display if ln.kind == "add"]

    @property
    def del_lines(self) -> list[DiffLine]:
        return [ln for ln in self.display if ln.kind == "del"]

    def is_whitespace_only(self) -> bool:
        """True when removing all whitespace makes both sides equal."""
        old = b"".join(ln.data for ln in self.del_lines)
        new = b"".join(ln.data for ln in self.add_lines)
        return _strip_ws(old) == _strip_ws(new)


def _strip_ws(data: bytes) -> bytes:
    return bytes(b for b in data if b not in b" \t\r\n\f\v")


@dataclass
class FileDiff:
    path: str
    base: bytes | None     # None: file absent in base (new file)
    target: bytes | None   # None: file absent in target (deleted by agent)
    hunks: list[Hunk] = field(default_factory=list)

    def reconstruct(self, applied: set[int]) -> bytes | None:
        """Content after applying the hunks whose indices are in `applied`.

        Returns None only for a deleted file whose (single) hunk is applied.
        """
        if self.target is None:
            # Deletion: applied -> gone, not applied -> base survives.
            return None if 0 in applied and self.hunks else self.base
        base_lines = split_lines(self.base or b"")
        target_lines = split_lines(self.target)
        if not self.hunks:
            return self.base
        out: list[bytes] = []
        base_pos = 0
        for hunk in self.hunks:
            b_start, b_end = hunk.base_span
            t_start, t_end = hunk.target_span
            out.extend(base_lines[base_pos:b_start])
            if hunk.index in applied:
                out.extend(target_lines[t_start:t_end])
            else:
                out.extend(base_lines[b_start:b_end])
            base_pos = b_end
        out.extend(base_lines[base_pos:])
        return b"".join(out)


def compute_file_diff(path: str, base: bytes | None, target: bytes | None) -> FileDiff:
    fd = FileDiff(path=path, base=base, target=target)
    if target is None:
        if base is not None:
            fd.hunks = [_deletion_hunk(base)]
        return fd
    base_lines = split_lines(base or b"")
    target_lines = split_lines(target)
    matcher = SequenceMatcher(a=base_lines, b=target_lines, autojunk=False)
    opcodes = matcher.get_opcodes()
    changed = [op for op in opcodes if op[0] != "equal"]
    if not changed:
        return fd

    # Group changes: merge two change opcodes when the equal run between them
    # is short enough that their context windows would overlap.
    groups: list[list[tuple[str, int, int, int, int]]] = []
    current: list[tuple[str, int, int, int, int]] = []
    for op in opcodes:
        tag, i1, i2, j1, j2 = op
        if tag == "equal":
            if current and (i2 - i1) <= 2 * CONTEXT:
                current.append(op)
            elif current:
                groups.append(current)
                current = []
            continue
        current.append(op)
    if current:
        groups.append(current)

    for idx, group in enumerate(groups):
        # Trim leading/trailing equal opcodes that slipped into the group.
        while group and group[0][0] == "equal":
            group.pop(0)
        while group and group[-1][0] == "equal":
            group.pop()
        b_start, b_end = group[0][1], group[-1][2]
        t_start, t_end = group[0][3], group[-1][4]
        display: list[DiffLine] = []
        ctx_before = min(CONTEXT, t_start)
        for k in range(t_start - ctx_before, t_start):
            display.append(DiffLine("ctx", target_lines[k], k + 1))
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                for k in range(j1, j2):
                    display.append(DiffLine("ctx", target_lines[k], k + 1))
            else:
                for k in range(i1, i2):
                    display.append(DiffLine("del", base_lines[k], None))
                for offset, k in enumerate(range(j1, j2)):
                    # In a replace block, the k-th added line most plausibly
                    # rewrites the k-th deleted one; the engine uses the pair
                    # for delta typing when the two are similar enough.
                    paired = base_lines[i1 + offset] if tag == "replace" and offset < (i2 - i1) else None
                    display.append(DiffLine("add", target_lines[k], k + 1, paired_data=paired))
        ctx_after = min(CONTEXT, len(target_lines) - t_end)
        for k in range(t_end, t_end + ctx_after):
            display.append(DiffLine("ctx", target_lines[k], k + 1))
        fd.hunks.append(
            Hunk(index=idx, base_span=(b_start, b_end), target_span=(t_start, t_end), display=display)
        )
    return fd


def _deletion_hunk(base: bytes) -> Hunk:
    lines = split_lines(base)
    display = [DiffLine("del", data, None) for data in lines]
    return Hunk(index=0, base_span=(0, len(lines)), target_span=(0, 0), display=display)


def is_binary(data: bytes | None) -> bool:
    if data is None:
        return False
    return b"\0" in data[:8000]


def is_utf8(data: bytes | None) -> bool:
    if data is None:
        return True
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True
