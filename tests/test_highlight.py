from typethru import engine, highlight, tui
from typethru.diffmodel import compute_file_diff
from typethru.rules import DEFAULT_AUTO_GLOBS, Settings

PY_SOURCE = (
    'def greet(name):\n'
    '    """Say hi.\n'
    '    Second doc line.\n'
    '    """\n'
    '    count = 42\n'
    '    return f"hi {name}"\n'
)


class TestHighlightFile:
    def test_lines_reproduce_source_exactly(self):
        per_line = highlight.highlight_file("x.py", PY_SOURCE)
        assert per_line is not None
        for i, expected in enumerate(PY_SOURCE.splitlines()):
            frags = highlight.line_fragments(per_line, i + 1, expected)
            assert frags is not None, f"line {i + 1} did not reproduce"
            assert "".join(t for _, t in frags) == expected

    def test_keyword_and_number_styled(self):
        per_line = highlight.highlight_file("x.py", PY_SOURCE)
        line1 = highlight.line_fragments(per_line, 1, "def greet(name):")
        assert any("ansiblue" in style and "def" in text for style, text in line1)
        line5 = highlight.line_fragments(per_line, 5, "    count = 42")
        assert any("ansimagenta" in style and "42" in text for style, text in line5)

    def test_multiline_string_interior_styled_as_string(self):
        per_line = highlight.highlight_file("x.py", PY_SOURCE)
        line3 = highlight.line_fragments(per_line, 3, "    Second doc line.")
        assert line3 is not None
        assert any("ansigreen" in style for style, _ in line3)

    def test_unknown_extension_returns_none(self):
        assert highlight.highlight_file("data.qzx", "whatever\n") is None

    def test_mismatched_text_rejected(self):
        per_line = highlight.highlight_file("x.py", PY_SOURCE)
        assert highlight.line_fragments(per_line, 1, "something else") is None

    def test_out_of_range_lineno(self):
        per_line = highlight.highlight_file("x.py", PY_SOURCE)
        assert highlight.line_fragments(per_line, 999, "x") is None


def controller_with_completed_line(highlight_on: bool) -> tui.Controller:
    fd = compute_file_diff("f.py", b"pass\n", b"pass\ncount = 42\nx = 1\n")
    settings = Settings(auto_globs=list(DEFAULT_AUTO_GLOBS), highlight=highlight_on)
    session = engine.Session([fd], settings, writer=None)
    session.start()
    line = session.current_line
    for ch in line.target[line.start : line.end]:
        session.type_char(ch)
    session.enter()  # first add line is now completed, second is active
    ctrl = tui.Controller(session, tui.TuiConfig(mode="gate", plan=[], untracked=[]))
    ctrl.state = "typing"
    return ctrl


class TestEarnedColor:
    def test_completed_line_gets_syntax_fragments(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        ctrl = controller_with_completed_line(highlight_on=True)
        body = ctrl.body_fragments()
        assert any("ansimagenta" in style for style, _ in body)

    def test_ghost_lines_stay_ghost(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        ctrl = controller_with_completed_line(highlight_on=True)
        body = ctrl.body_fragments()
        ghost_texts = [t for s, t in body if s == "class:ghost"]
        assert any("x = 1" in t for t in ghost_texts)  # pending line unhighlighted

    def test_highlight_config_off(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        ctrl = controller_with_completed_line(highlight_on=False)
        body = ctrl.body_fragments()
        assert not any("ansimagenta" in style for style, _ in body)
        assert any(style == "class:done" for style, _ in body)

    def test_no_color_disables(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        ctrl = controller_with_completed_line(highlight_on=True)
        body = ctrl.body_fragments()
        assert not any("ansimagenta" in style for style, _ in body)
