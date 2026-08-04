from typethru import engine
from typethru.diffmodel import compute_file_diff
from typethru.rules import DEFAULT_AUTO_GLOBS, Settings


def settings(**kw) -> Settings:
    return Settings(auto_globs=list(DEFAULT_AUTO_GLOBS), **kw)


def session_for(base: bytes, target: bytes, path: str = "f.py", writer=None, **kw):
    fd = compute_file_diff(path, base, target)
    s = engine.Session([fd], settings(**kw), writer=writer)
    s.start()
    return s, fd


def type_line(s: engine.Session) -> None:
    line = s.current_line
    for ch in line.target[line.start : line.end]:
        s.type_char(ch)
    s.enter()


class TestTyping:
    def test_correct_typing_completes_hunk(self):
        writes = []
        s, fd = session_for(b"a\nb\n", b"a\nB2\n", writer=lambda f, ap: writes.append(set(ap)))
        assert s.current is not None
        type_line(s)
        assert s.finished
        assert s.counts()[engine.TYPED] == 1
        assert writes and writes[-1] == {0}

    def test_wrong_char_blocks_until_corrected(self):
        s, _ = session_for(b"a\n", b"a\nxy\n")
        s.type_char("q")
        line = s.current_line
        assert line.error == "q"
        assert line.typed == 0
        s.type_char("x")  # still wrong path: error must be cleared by backspace? No:
        # a correct char clears the pending error and advances.
        assert line.error is None
        assert line.typed == 1

    def test_backspace_clears_error_then_typed(self):
        s, _ = session_for(b"a\n", b"a\nxy\n")
        s.type_char("x")
        s.type_char("q")
        line = s.current_line
        assert line.error == "q" and line.typed == 1
        s.backspace()
        assert line.error is None and line.typed == 1
        s.backspace()
        assert line.typed == 0

    def test_enter_refused_until_complete(self):
        s, _ = session_for(b"a\n", b"a\nxy\n")
        s.type_char("x")
        s.enter()
        assert not s.finished
        assert s.current_line.typed == 1
        s.type_char("y")
        s.enter()
        assert s.finished

    def test_extra_typing_past_end_is_error(self):
        s, _ = session_for(b"a\n", b"a\nx\n")
        s.type_char("x")
        s.type_char("z")
        assert s.current_line.error == "z"
        assert not s.current_line.complete
        s.backspace()
        s.enter()
        assert s.finished

    def test_auto_indent_prefills(self):
        s, _ = session_for(b"def f():\n", b"def f():\n    return 1\n")
        line = s.current_line
        assert line.start == 4
        assert line.cursor == 4
        for ch in "return 1":
            s.type_char(ch)
        s.enter()
        assert s.finished

    def test_indent_typed_when_configured(self):
        s, _ = session_for(
            b"def f():\n", b"def f():\n    return 1\n", auto_indent=False
        )
        assert s.current_line.start == 0

    def test_trailing_whitespace_not_required(self):
        s, _ = session_for(b"a\n", b"a\nx.  \n")
        line = s.current_line
        assert line.target == "x.  "
        assert line.end == 2

    def test_blank_line_needs_only_enter(self):
        s, _ = session_for(b"a\nb\n", b"a\nnew1\n\nnew2\nb\n")
        type_line(s)          # new1
        assert s.current_line.target == ""
        s.enter()             # blank line
        type_line(s)          # new2
        assert s.finished

    def test_tab_char_typed(self):
        s, _ = session_for(b"a\n", b"a\nx\ty\n")
        for ch in "x\ty":
            s.type_char(ch)
        s.enter()
        assert s.finished


class TestOutcomes:
    def test_apply_without_typing(self):
        writes = []
        s, _ = session_for(b"a\n", b"a\nx\n", writer=lambda f, ap: writes.append(set(ap)))
        s.apply_current()
        assert s.finished
        assert s.counts()[engine.APPLIED] == 1
        assert writes[-1] == {0}

    def test_skip_leaves_unapplied(self):
        writes = []
        s, _ = session_for(b"a\n", b"a\nx\n", writer=lambda f, ap: writes.append(set(ap)))
        s.skip_current()
        assert s.finished
        assert s.counts()[engine.SKIPPED] == 1
        assert not writes
        assert s.unresolved() == 1

    def test_quit_midway(self):
        s, _ = session_for(b"a\n", b"a\nx\ny\n")
        s.type_char("x")
        s.quit()
        assert s.finished
        assert s.unresolved() == 1

    def test_whitespace_only_hunk_is_auto(self):
        writes = []
        s, _ = session_for(
            b"x = 1\n", b"x  =  1\n", writer=lambda f, ap: writes.append(set(ap))
        )
        assert s.finished
        assert s.counts()[engine.AUTO] == 1
        assert writes[-1] == {0}

    def test_lockfile_is_auto(self):
        fd = compute_file_diff("package-lock.json", b"{}\n", b'{"a":1}\n')
        s = engine.Session([fd], settings(), writer=None)
        s.start()
        assert s.finished
        assert s.counts()[engine.AUTO] == 1

    def test_multi_hunk_order(self):
        base = b"".join(b"line%d\n" % i for i in range(30))
        target = base.replace(b"line2\n", b"A\n").replace(b"line25\n", b"B\n")
        s, fd = session_for(base, target)
        assert s.current.hunk.index == 0
        type_line(s)
        assert s.current.hunk.index == 1
        type_line(s)
        assert s.finished
        assert fd.reconstruct(s.applied[fd.path]) == target


class TestStats:
    def test_accuracy_counts_errors(self):
        s, _ = session_for(b"a\n", b"a\nxy\n")
        s.type_char("q")   # error
        s.type_char("x")   # correct
        s.type_char("y")   # correct
        s.enter()
        assert s.stats.errors == 1
        assert s.stats.correct == 2
        assert abs(s.stats.accuracy - (2 / 3 * 100)) < 0.01

    def test_wpm_positive_after_typing(self):
        s, _ = session_for(b"a\n", b"a\nhello\n")
        type_line(s)
        assert s.stats.wpm is None or s.stats.wpm > 0

    def test_typed_line_total(self):
        s, _ = session_for(b"a\n", b"a\nx\ny\n")
        type_line(s)
        type_line(s)
        assert s.typed_line_total() == 2
