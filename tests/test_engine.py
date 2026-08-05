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


class TestCompose:
    def test_em_dash_typed_as_two_hyphens(self):
        s, _ = session_for(b"a\n", "a\nx — y\n".encode())
        for ch in "x ":
            s.type_char(ch)
        s.type_char("-")
        line = s.current_line
        assert line.pending == "-"
        assert not line.complete
        s.type_char("-")
        assert line.pending == ""
        assert line.target[line.cursor - 1] == "—"
        for ch in " y":
            s.type_char(ch)
        s.enter()
        assert s.finished

    def test_direct_em_dash_still_accepted(self):
        s, _ = session_for(b"a\n", "a\n—\n".encode())
        s.type_char("—")
        s.enter()
        assert s.finished

    def test_wrong_key_mid_compose_is_error(self):
        s, _ = session_for(b"a\n", "a\n—x\n".encode())
        s.type_char("-")
        s.type_char("z")
        line = s.current_line
        assert line.error == "z"
        assert line.pending == "-"
        s.backspace()          # clears the error, keeps the partial
        assert line.error is None and line.pending == "-"
        s.type_char("-")
        s.type_char("x")
        s.enter()
        assert s.finished

    def test_backspace_unwinds_pending(self):
        s, _ = session_for(b"a\n", "a\n…\n".encode())  # ellipsis = ...
        s.type_char(".")
        s.type_char(".")
        assert s.current_line.pending == ".."
        s.backspace()
        assert s.current_line.pending == "."
        s.type_char(".")
        s.type_char(".")
        s.enter()
        assert s.finished

    def test_curly_quotes_and_nbsp(self):
        target = "a\n‘q’ “w” z\n".encode()
        s, _ = session_for(b"a\n", target)
        for key in ["'", "q", "'", " ", '"', "w", '"', " ", "z"]:
            s.type_char(key)
        s.enter()
        assert s.finished
        assert s.stats.errors == 0

    def test_compose_keystrokes_count_toward_stats(self):
        s, _ = session_for(b"a\n", "a\n—\n".encode())
        s.type_char("-")
        s.type_char("-")
        s.enter()
        assert s.stats.correct == 2  # two keystrokes for one character


class TestDeltaTyping:
    def test_small_edit_types_only_the_change(self):
        s, _ = session_for(
            b"total = compute_sum(values)\n", b"total = compute_avg(values)\n"
        )
        line = s.current_line
        assert (line.start, line.end) == (16, 19)
        assert line.target[line.start : line.end] == "avg"
        for ch in "avg":
            s.type_char(ch)
        s.enter()
        assert s.finished

    def test_typing_through_prefilled_suffix_is_harmless(self):
        s, _ = session_for(
            b"total = compute_sum(values)\n", b"total = compute_avg(values)\n"
        )
        for ch in "avg(values)":  # keeps typing past the required region
            s.type_char(ch)
        assert s.current_line.error is None
        assert s.stats.errors == 0
        s.enter()
        assert s.finished

    def test_dissimilar_replacement_types_full_line(self):
        s, _ = session_for(b"import os\n", b"return calculate_totals(frame)\n")
        line = s.current_line
        assert (line.start, line.end) == (0, len("return calculate_totals(frame)"))

    def test_pure_insertion_has_no_pair(self):
        s, _ = session_for(b"a\n", b"a\nnew line here\n")
        line = s.current_line
        assert (line.start, line.end) == (0, len("new line here"))

    def test_delta_disabled_by_config(self):
        s, _ = session_for(
            b"total = compute_sum(values)\n",
            b"total = compute_avg(values)\n",
            delta=False,
        )
        line = s.current_line
        assert (line.start, line.end) == (0, len("total = compute_avg(values)"))

    def test_indent_still_prefilled_alongside_delta(self):
        s, _ = session_for(
            b"    return self.parse(data)\n", b"    return self.render(data)\n"
        )
        line = s.current_line
        # common prefix "    return self." (16), suffix "(data)" then diverge
        assert line.start == 16
        assert line.target[line.start : line.end] == "render"


class TestRepeatFill:
    def test_identical_line_autofills_second_time(self):
        base = b"".join(b"line%d\n" % i for i in range(30))
        target = base.replace(b"line2\n", b"line2\nimport logging\n").replace(
            b"line25\n", b"line25\nimport logging\n"
        )
        s, fd = session_for(base, target)
        type_line(s)                       # first occurrence: typed for real
        line = s.current_line
        assert line.repeat_fill
        assert line.complete               # Enter is enough
        s.enter()
        assert s.finished
        assert s.repeat_lines == 1
        assert fd.reconstruct(s.applied[fd.path]) == target

    def test_typing_a_repeat_line_anyway_is_harmless(self):
        base = b"a\n"
        target = b"a\nimport logging\n\nimport logging\n"
        s, _ = session_for(base, target)
        type_line(s)                       # first occurrence
        s.enter()                          # blank line
        line = s.current_line
        assert line.repeat_fill
        for ch in "import log":
            s.type_char(ch)
        assert s.stats.errors == 0
        s.enter()
        assert s.finished

    def test_different_indent_same_content_still_fills(self):
        base = b"a\n"
        target = b"a\nfoo()\n\n    foo()\n"
        s, _ = session_for(base, target)
        type_line(s)
        s.enter()
        assert s.current_line.repeat_fill  # stripped text matches

    def test_disabled_by_config(self):
        base = b"a\n"
        target = b"a\nimport logging\n\nimport logging\n"
        s, _ = session_for(base, target, repeatfill=False)
        type_line(s)
        s.enter()
        assert not s.current_line.repeat_fill

    def test_repeat_lines_not_reseeded(self):
        # A repeat-filled line must not count as "typed" for later lines.
        s, _ = session_for(b"a\n", b"a\nx = 1\n\nx = 1\n\nx = 1\n")
        type_line(s)
        s.enter()
        s.enter()   # second occurrence: repeat
        s.enter()   # blank
        assert s.current_line.repeat_fill  # third also repeats
        s.enter()
        assert s.finished
        assert s.repeat_lines == 2


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
