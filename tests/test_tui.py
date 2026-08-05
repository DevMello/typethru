from typethru import engine, tui
from typethru.diffmodel import compute_file_diff
from typethru.rules import DEFAULT_AUTO_GLOBS, Settings


def controller(live_stats: bool = True) -> tui.Controller:
    fd = compute_file_diff("f.py", b"a\n", b"a\nx = 1\n")
    settings = Settings(auto_globs=list(DEFAULT_AUTO_GLOBS), live_stats=live_stats)
    session = engine.Session([fd], settings, writer=None)
    session.start()
    ctrl = tui.Controller(session, tui.TuiConfig(mode="gate", plan=[], untracked=[]))
    ctrl.state = "typing"
    return ctrl


def footer_text(ctrl: tui.Controller) -> str:
    return "".join(text for _, text in ctrl.footer_fragments())


def em_dash_controller(hints: bool = True) -> tui.Controller:
    fd = compute_file_diff("f.md", b"a\n", "a\nx — y\n".encode())
    settings = Settings(auto_globs=list(DEFAULT_AUTO_GLOBS), hints=hints)
    session = engine.Session([fd], settings, writer=None)
    session.start()
    ctrl = tui.Controller(session, tui.TuiConfig(mode="gate", plan=[], untracked=[]))
    ctrl.state = "typing"
    return ctrl


class TestComposeHint:
    def test_hint_shows_when_hunk_has_composable_chars(self):
        ctrl = em_dash_controller()
        assert ctrl.hint_visible()
        text = "".join(t for _, t in ctrl.hint_fragments())
        assert "--" in text and "never show again" in text
        assert len(text) <= 80

    def test_no_hint_on_plain_ascii_hunk(self):
        ctrl = controller()  # "x = 1" hunk
        assert not ctrl.hint_visible()

    def test_hints_config_off(self):
        ctrl = em_dash_controller(hints=False)
        assert not ctrl.hint_visible()

    def test_dismiss_stops_showing_and_calls_persist(self):
        calls = []
        ctrl = em_dash_controller()
        ctrl.config.on_dismiss_hints = lambda: calls.append(True)
        ctrl.dismiss_hints()
        assert not ctrl.hint_visible()
        assert calls == [True]


class TestEstimatedTime:
    def test_plan_shows_per_file_and_total_estimate(self):
        fd = compute_file_diff("f.py", b"a\n", b"a\n" + b"x" * 200 + b"\n")
        settings = Settings(auto_globs=list(DEFAULT_AUTO_GLOBS))
        session = engine.Session([fd], settings, writer=None)
        entry = tui.PlanEntry(path="f.py", typeable=1, auto=0, est_chars=2000)
        ctrl = tui.Controller(
            session,
            tui.TuiConfig(mode="gate", plan=[entry], untracked=[], est_wpm=40.0),
        )
        text = "".join(t for _, t in ctrl.plan_fragments())
        assert "~10m" in text                       # 2000 chars / 5 / 40wpm
        assert "estimated typing: ~10m at 40 wpm" in text

    def test_no_estimate_without_wpm(self):
        session = engine.Session([], Settings(auto_globs=[]), writer=None)
        ctrl = tui.Controller(
            session, tui.TuiConfig(mode="gate", plan=[], untracked=[], est_wpm=None)
        )
        text = "".join(t for _, t in ctrl.plan_fragments())
        assert "estimated typing" not in text

    def test_fmt_minutes(self):
        assert tui._fmt_minutes(0.4) == "<1m"
        assert tui._fmt_minutes(14.4) == "14m"
        assert tui._fmt_minutes(65) == "1h05m"


class TestExpandContext:
    def test_expand_widens_and_preserves_typing_state(self):
        base = b"".join(b"line%d\n" % i for i in range(40))
        target = base.replace(b"line20\n", b"CHANGED\n")
        fd = compute_file_diff("f.py", base, target)
        settings = Settings(auto_globs=list(DEFAULT_AUTO_GLOBS))
        session = engine.Session([fd], settings, writer=None)
        session.start()
        session.type_char("C")
        ctrl = tui.Controller(session, tui.TuiConfig(mode="gate", plan=[], untracked=[]))
        ctrl.state = "typing"
        before = len(session.current.hunk.display)
        adds_before = [ln.text for ln in session.current.hunk.add_lines]
        line_before = session.current_line.target
        ctrl.expand_context()
        after = len(session.current.hunk.display)
        assert after == before + 10  # 5 more above, 5 more below
        assert [ln.text for ln in session.current.hunk.add_lines] == adds_before
        assert session.current_line.target == line_before
        assert session.current_line.typed == 1  # in-progress typing untouched

    def test_expand_clamps_at_file_bounds(self):
        fd = compute_file_diff("f.py", b"a\nb\n", b"a\nB\nb\n")
        settings = Settings(auto_globs=list(DEFAULT_AUTO_GLOBS))
        session = engine.Session([fd], settings, writer=None)
        session.start()
        ctrl = tui.Controller(session, tui.TuiConfig(mode="gate", plan=[], untracked=[]))
        ctrl.state = "typing"
        for _ in range(5):
            ctrl.expand_context()
        texts = [ln.text for ln in session.current.hunk.display]
        assert texts == ["a", "B", "b"]  # whole file, no phantom lines


class TestLiveStats:
    def test_footer_shows_stats_when_enabled(self):
        ctrl = controller(live_stats=True)
        ctrl.session.type_char("x")
        text = footer_text(ctrl)
        assert "wpm" in text
        assert "100.0%" in text
        assert "T0 A0 S0" in text  # compact tally still present

    def test_accuracy_updates_with_errors(self):
        ctrl = controller(live_stats=True)
        ctrl.session.type_char("x")
        ctrl.session.type_char("q")  # wrong
        assert "50.0%" in footer_text(ctrl)

    def test_placeholder_before_first_keystroke(self):
        ctrl = controller(live_stats=True)
        text = footer_text(ctrl)
        assert "--%" in text and "0wpm" in text

    def test_footer_quiet_when_disabled(self):
        ctrl = controller(live_stats=False)
        text = footer_text(ctrl)
        assert "wpm" not in text and "%" not in text
        assert "typed" in text

    def test_footer_fits_min_width(self):
        ctrl = controller(live_stats=True)
        ctrl.session.type_char("x")
        assert len(footer_text(ctrl)) <= 80

    def test_refresh_interval_follows_setting(self):
        from prompt_toolkit.input import DummyInput
        from prompt_toolkit.output import DummyOutput

        app_on = tui.build_app(controller(live_stats=True), input=DummyInput(), output=DummyOutput())
        app_off = tui.build_app(controller(live_stats=False), input=DummyInput(), output=DummyOutput())
        assert app_on.refresh_interval == 1.0
        assert not app_off.refresh_interval
