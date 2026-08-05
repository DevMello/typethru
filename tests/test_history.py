import json

from typethru import backup, history
from conftest import commit_all


def seed(repo):
    (repo / "seed.txt").write_bytes(b"s\n")
    commit_all(repo)


class TestRecordLoad:
    def test_roundtrip(self, repo):
        seed(repo)
        history.record(repo, {"mode": "session", "wpm": 41.0})
        history.record(repo, {"mode": "practice", "wpm": 38.0})
        entries = history.load(repo)
        assert len(entries) == 2
        assert entries[0]["mode"] == "session"
        assert "ts" in entries[0]

    def test_corrupt_line_skipped(self, repo):
        seed(repo)
        history.record(repo, {"mode": "session"})
        with open(history.history_path(repo), "a", encoding="utf-8") as fh:
            fh.write("{not json\n")
        history.record(repo, {"mode": "session"})
        assert len(history.load(repo)) == 2

    def test_empty(self, repo):
        seed(repo)
        assert history.load(repo) == []


class TestMedianWpm:
    def test_default_when_empty(self, repo):
        seed(repo)
        assert history.median_wpm(repo) == history.DEFAULT_WPM

    def test_median_of_recent(self, repo):
        seed(repo)
        for wpm in (30.0, 40.0, 50.0):
            history.record(repo, {"wpm": wpm})
        assert history.median_wpm(repo) == 40.0

    def test_robot_sessions_capped(self, repo):
        seed(repo)
        history.record(repo, {"wpm": 4896.0})
        assert history.median_wpm(repo) == history.ESTIMATE_WPM_CAP


class TestReceipt:
    def test_format(self):
        entry = {
            "hunks": {"typed": 6, "auto": 2, "applied": 1, "skipped": 0},
            "accuracy": 97.4,
            "wpm": 41.2,
        }
        text = history.format_receipt(entry)
        assert text == "Typed-thru: 6/9 hunks (2 auto, 1 untyped), accuracy 97.4%, 41 wpm"

    def test_last_receipt_skips_practice_and_incomplete(self, repo):
        seed(repo)
        history.record(repo, {"mode": "session", "complete": True, "verified": True,
                              "hunks": {"typed": 3, "auto": 0, "applied": 0, "skipped": 0},
                              "accuracy": 99.0, "wpm": 40.0})
        history.record(repo, {"mode": "practice", "complete": True, "verified": None,
                              "hunks": {"typed": 9, "auto": 0, "applied": 0, "skipped": 0}})
        history.record(repo, {"mode": "session", "complete": False, "verified": None,
                              "hunks": {"typed": 1, "auto": 0, "applied": 0, "skipped": 2}})
        assert history.last_receipt(repo) == "Typed-thru: 3/3 hunks, accuracy 99.0%, 40 wpm"

    def test_no_receipt(self, repo):
        seed(repo)
        assert history.last_receipt(repo) is None


class TestBackupLayoutCompat:
    def test_drop_preserves_history(self, repo):
        seed(repo)
        history.record(repo, {"mode": "session"})
        backup.create(repo, [("a.py", b"x\n", None)])
        backup.drop(repo)
        assert not backup.exists(repo)
        assert len(history.load(repo)) == 1

    def test_old_layout_backup_still_readable(self, repo):
        seed(repo)
        old_dir = backup.state_dir(repo)
        old_dir.mkdir(parents=True, exist_ok=True)
        (old_dir / "0.bin").write_bytes(b"old agent state\n")
        manifest = {"version": 1, "created_at": "x",
                    "files": [{"path": "a.py", "content": "0.bin", "mode": None}]}
        (old_dir / backup.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
        assert backup.exists(repo)
        files = backup.load(repo)
        assert backup.target_content(repo, files[0]) == b"old agent state\n"
        backup.restore(repo)
        assert (repo / "a.py").read_bytes() == b"old agent state\n"
        assert not backup.exists(repo)
