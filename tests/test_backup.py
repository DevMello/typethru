import pytest

from typethru import backup
from conftest import commit_all


class TestBackup:
    def test_roundtrip(self, repo):
        (repo / "a.py").write_bytes(b"base\n")
        commit_all(repo)
        backup.create(repo, [("a.py", b"agent version\n", None), ("gone.py", None, None)])
        assert backup.exists(repo)
        files = backup.load(repo)
        assert [f.path for f in files] == ["a.py", "gone.py"]
        assert backup.target_content(repo, files[0]) == b"agent version\n"
        assert backup.target_content(repo, files[1]) is None

    def test_restore_writes_and_deletes(self, repo):
        (repo / "a.py").write_bytes(b"base\n")
        (repo / "gone.py").write_bytes(b"still here\n")
        commit_all(repo)
        backup.create(repo, [("a.py", b"agent\n", None), ("gone.py", None, None)])
        restored = backup.restore(repo)
        assert set(restored) == {"a.py", "gone.py"}
        assert (repo / "a.py").read_bytes() == b"agent\n"
        assert not (repo / "gone.py").exists()
        assert not backup.exists(repo)

    def test_double_create_refused(self, repo):
        commit_all_dummy(repo)
        backup.create(repo, [("a.py", b"x\n", None)])
        with pytest.raises(backup.BackupError):
            backup.create(repo, [("a.py", b"y\n", None)])

    def test_drop(self, repo):
        commit_all_dummy(repo)
        backup.create(repo, [("a.py", b"x\n", None)])
        backup.drop(repo)
        assert not backup.exists(repo)

    def test_load_without_backup(self, repo):
        commit_all_dummy(repo)
        with pytest.raises(backup.BackupError):
            backup.load(repo)


def commit_all_dummy(repo):
    (repo / "seed.txt").write_bytes(b"seed\n")
    commit_all(repo)
