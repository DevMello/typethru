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


class TestLiveStats:
    def test_footer_shows_stats_when_enabled(self):
        ctrl = controller(live_stats=True)
        ctrl.session.type_char("x")
        text = footer_text(ctrl)
        assert "wpm" in text
        assert "100.0%" in text
        assert "typed" in text  # tally still present

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
