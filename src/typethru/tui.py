"""The full-screen typing interface.

A thin adapter: all decisions live in engine.Session; this module renders
state and forwards keystrokes. Input and output are injectable so tests can
drive the real Application through a pipe (DECISIONS.md #3).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable

from prompt_toolkit.application import Application
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.containers import ConditionalContainer, ScrollOffsets
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.screen import Point
from prompt_toolkit.styles import Style

from . import engine, highlight
from .summary import _fmt_elapsed

GUTTER = 6


def _styles() -> Style:
    if os.environ.get("NO_COLOR"):
        return Style.from_dict(
            {
                "dim": "",
                "ghost": "",
                "del": "",
                "delmark": "",
                "err": "reverse",
                "done": "bold",
                "donemark": "bold",
                "path": "bold",
            }
        )
    return Style.from_dict(
        {
            "dim": "fg:ansibrightblack",
            "ghost": "fg:ansibrightblack",
            "del": "fg:ansired",
            "delmark": "fg:ansired",
            "err": "fg:ansired reverse",
            "done": "",
            "donemark": "fg:ansigreen",
            "path": "bold",
        }
    )


@dataclass
class PlanEntry:
    path: str
    typeable: int
    auto: int
    auto_reasons: list[str] = field(default_factory=list)
    est_chars: int = 0


def _fmt_minutes(minutes: float) -> str:
    if minutes < 1:
        return "<1m"
    m = round(minutes)
    if m >= 60:
        return f"{m // 60}h{m % 60:02d}m"
    return f"{m}m"


@dataclass
class TuiConfig:
    mode: str                    # "gate" | "resume" | "practice"
    plan: list[PlanEntry]
    untracked: list[str]
    on_begin: Callable[[], None] | None = None  # gate: backup + revert happen here
    subtitle: str = ""
    on_dismiss_hints: Callable[[], None] | None = None  # persist "never show again"
    est_wpm: float | None = None  # historical median wpm driving the estimate


class Controller:
    def __init__(self, session: engine.Session, config: TuiConfig) -> None:
        self.session = session
        self.config = config
        self.state = "plan"
        self._cursor: Point | None = None
        self._hl_enabled = session.settings.highlight and not os.environ.get("NO_COLOR")
        self._hl_cache: dict[str, list | None] = {}

    def _highlighted(self, item: engine.SessionItem, dline) -> list[tuple[str, str]] | None:
        """Syntax fragments for a completed line, or None to render plain."""
        if not self._hl_enabled or dline.target_lineno is None:
            return None
        path = item.file.path
        if path not in self._hl_cache:
            target = item.file.target
            try:
                text = target.decode("utf-8") if target is not None else ""
            except UnicodeDecodeError:
                text = ""
            self._hl_cache[path] = highlight.highlight_file(path, text) if text else None
        return highlight.line_fragments(self._hl_cache[path], dline.target_lineno, dline.text)

    # -- plan screen -------------------------------------------------------

    def plan_fragments(self):
        cfg = self.config
        out = []
        title = {"gate": "typethru", "resume": "typethru - resuming", "practice": f"typethru practice {cfg.subtitle} - read-only"}[cfg.mode]
        out.append(("class:path", title))
        out.append(("", "\n\n"))
        wpm = cfg.est_wpm
        for entry in cfg.plan:
            out.append(("", f"  {entry.path}"))
            bits = []
            if entry.typeable:
                bits.append(f"{entry.typeable} hunk{'s' if entry.typeable != 1 else ''}")
                if wpm:
                    bits.append(f"~{_fmt_minutes(entry.est_chars / 5 / wpm)}")
            for reason in entry.auto_reasons:
                bits.append(f"auto: {reason}")
            out.append(("class:dim", "   " + " - ".join(bits) + "\n"))
        for path in cfg.untracked:
            out.append(("class:dim", f"  {path}   untracked, left alone\n"))
        out.append(("", "\n"))
        if wpm:
            total = sum(e.est_chars for e in cfg.plan) / 5 / wpm
            out.append(("class:dim", f"estimated typing: ~{_fmt_minutes(total)} at {wpm:.0f} wpm\n\n"))
        if cfg.mode == "gate":
            out.append(("", "Your working tree will be reverted while you type; staged changes are unstaged.\n"))
            out.append(("class:dim", "Backup: .git/typethru/\n\n"))
        elif cfg.mode == "resume":
            out.append(("", "Continuing toward the captured state.\n\n"))
        out.append(("class:dim", "Enter begin - ^Q abort"))
        return out

    # -- typing screen -----------------------------------------------------

    def header_fragments(self):
        item = self.session.current
        if item is None:
            return [("class:dim", "typethru")]
        pos = self.session.items.index(item) + 1
        adds = len(item.hunk.add_lines)
        line_no = min(self.session.current_line_index + 1, adds)
        left = [
            ("class:dim", "typethru  "),
            ("class:path", item.file.path),
            ("class:dim", f"  hunk {pos}/{len(self.session.items)}"),
        ]
        right_text = f"line {line_no}/{adds}"
        return left + [("class:dim", "  |  " + right_text)]

    def body_fragments(self):
        self._cursor = None
        item = self.session.current
        if item is None:
            return [("class:dim", "session complete")]
        out = []
        adds_seen = 0
        row = 0
        line_state = self.session.current_line
        for dline in item.hunk.display:
            gutter = f"{dline.target_lineno:>{GUTTER}}" if dline.target_lineno else " " * GUTTER
            if dline.kind == "ctx":
                out.append(("class:dim", f"{gutter}     {dline.text}\n"))
            elif dline.kind == "del":
                out.append(("class:dim", gutter))
                out.append(("class:delmark", "  -  "))
                out.append(("class:del", f"{dline.text}\n"))
            else:  # add
                idx = adds_seen
                adds_seen += 1
                current_idx = self.session.current_line_index
                if idx < current_idx:
                    out.append(("class:dim", gutter))
                    out.append(("class:donemark", "  +  "))
                    frags = self._highlighted(item, dline)
                    if frags is None:
                        out.append(("class:done", f"{dline.text}\n"))
                    else:
                        out.extend(frags)
                        out.append(("", "\n"))
                elif idx == current_idx and line_state is not None:
                    out.append(("class:dim", gutter))
                    out.append(("class:dim", "  +  "))
                    if line_state.repeat_fill:
                        self._cursor = Point(x=GUTTER + 5 + line_state.cursor, y=row)
                        out.append(("", line_state.target))
                        out.append(("class:dim", "  (repeat - Enter)\n"))
                        row += 1
                        continue
                    prefix_cols = GUTTER + 5
                    typed_end = line_state.cursor
                    out.append(("", line_state.target[: typed_end]))
                    col = prefix_cols + typed_end
                    if line_state.pending:
                        out.append(("", line_state.pending))
                        col += len(line_state.pending)
                    if line_state.error is not None:
                        shown = line_state.error if line_state.error.isprintable() else "?"
                        out.append(("class:err", shown))
                        col += 1
                    self._cursor = Point(x=col, y=row)
                    # Ghost only what must be typed; a pre-filled delta suffix
                    # (and trailing whitespace) renders in default ink.
                    required_end = max(line_state.end, typed_end)
                    out.append(("class:ghost", line_state.target[typed_end:required_end]))
                    out.append(("", line_state.target[required_end:] + "\n"))
                else:
                    out.append(("class:dim", gutter))
                    out.append(("class:dim", "  +  "))
                    out.append(("class:ghost", f"{dline.text}\n"))
            row += 1
        return out

    def cursor_position(self):
        return self._cursor

    def hint_visible(self) -> bool:
        """The compose hint shows whenever the current hunk contains a
        character that needs a compose sequence, until dismissed for good."""
        if self.state != "typing" or not self.session.settings.hints:
            return False
        item = self.session.current
        if item is None:
            return False
        return any(
            ch in engine.COMPOSE for line in item.hunk.add_lines for ch in line.text
        )

    def dismiss_hints(self) -> None:
        self.session.settings.hints = False
        if self.config.on_dismiss_hints is not None:
            self.config.on_dismiss_hints()

    def hint_fragments(self):
        return [
            (
                "class:dim",
                'hint: type — as --, … as ..., curly quotes as \' and "   [^N] never show again',
            )
        ]

    def footer_fragments(self):
        counts = self.session.counts()
        parts = ["[^A] apply  [^S] skip  [^Q] quit"]
        if self.session.settings.live_stats:
            stats = self.session.stats
            acc = f"{stats.accuracy:.1f}%" if stats.accuracy is not None else "--%"
            wpm = f"{stats.wpm:.0f}wpm" if stats.wpm is not None else "0wpm"
            parts.append(f"{acc} {wpm} {_fmt_elapsed(stats.elapsed)}")
        parts.append(
            f"{counts[engine.TYPED]} typed  {counts[engine.AUTO]} auto  {counts[engine.SKIPPED]} skipped"
        )
        return [("class:dim", "   ".join(parts))]


def build_app(controller: Controller, input=None, output=None):
    session = controller.session
    in_plan = Condition(lambda: controller.state == "plan")
    in_typing = Condition(lambda: controller.state == "typing")

    kb = KeyBindings()

    def maybe_finish(event) -> None:
        if session.finished:
            event.app.exit(result="done")

    @kb.add("enter", filter=in_plan)
    def _begin(event):
        if controller.config.on_begin is not None:
            controller.config.on_begin()
        controller.state = "typing"
        if session.finished:
            event.app.exit(result="done")

    @kb.add("c-q", filter=in_plan)
    @kb.add("c-c", filter=in_plan)
    def _abort(event):
        event.app.exit(result="abort")

    @kb.add("<any>", filter=in_typing)
    def _type(event):
        for ch in event.data or "":
            if ch.isprintable():
                session.type_char(ch)

    @kb.add("tab", filter=in_typing)
    def _tab(event):
        session.type_char("\t")

    @kb.add("backspace", filter=in_typing)
    def _backspace(event):
        session.backspace()

    @kb.add("enter", filter=in_typing)
    def _enter(event):
        session.enter()
        maybe_finish(event)

    @kb.add("c-a", filter=in_typing)
    def _apply(event):
        session.apply_current()
        maybe_finish(event)

    @kb.add("c-s", filter=in_typing)
    def _skip(event):
        session.skip_current()
        maybe_finish(event)

    @kb.add("c-q", filter=in_typing)
    @kb.add("c-c", filter=in_typing)
    def _quit(event):
        session.quit()
        event.app.exit(result="quit")

    @kb.add("c-n", filter=in_typing)
    def _dismiss_hints(event):
        controller.dismiss_hints()

    @kb.add(Keys.BracketedPaste)
    def _paste(event):
        """Pasting is ignored: the point is typing."""

    def plan_or_body():
        if controller.state == "plan":
            return controller.plan_fragments()
        return controller.body_fragments()

    body_control = FormattedTextControl(
        plan_or_body,
        get_cursor_position=lambda: controller.cursor_position() if controller.state == "typing" else None,
        show_cursor=True,
        focusable=True,
    )
    body = Window(
        content=body_control,
        wrap_lines=False,
        scroll_offsets=ScrollOffsets(top=5, bottom=5),
        dont_extend_height=False,
    )
    header = Window(
        content=FormattedTextControl(lambda: controller.header_fragments() if controller.state == "typing" else [("class:dim", "")]),
        height=Dimension.exact(1),
    )
    footer = Window(
        content=FormattedTextControl(lambda: controller.footer_fragments() if controller.state == "typing" else [("class:dim", "")]),
        height=Dimension.exact(1),
    )
    hint = ConditionalContainer(
        Window(content=FormattedTextControl(controller.hint_fragments), height=Dimension.exact(1)),
        filter=Condition(controller.hint_visible),
    )
    root = HSplit([header, Window(height=Dimension.exact(1)), body, Window(height=Dimension.exact(1)), hint, footer])
    return Application(
        layout=Layout(root, focused_element=body),
        key_bindings=kb,
        style=_styles(),
        full_screen=True,
        mouse_support=False,
        # The elapsed clock in the footer needs a periodic repaint; without
        # live stats the screen only changes on keystrokes.
        refresh_interval=1.0 if session.settings.live_stats else None,
        input=input,
        output=output,
    )


def run(controller: Controller, input=None, output=None) -> str:
    """Run the TUI; returns "done", "quit", or "abort"."""
    app = build_app(controller, input=input, output=output)
    try:
        result = app.run()
    except (EOFError, KeyboardInterrupt):
        # Input died mid-session (terminal closed, pipe exhausted). Treat as
        # quit: the session summary still prints and the backup is retained.
        if controller.state == "plan":
            return "abort"
        controller.session.quit()
        return "quit"
    return result or "quit"
