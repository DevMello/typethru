from typethru.diffmodel import compute_file_diff
from typethru.rules import (
    DEFAULT_AUTO_GLOBS,
    Settings,
    file_auto_reason,
    hunk_auto_reason,
    path_auto_reason,
)


def settings() -> Settings:
    return Settings(auto_globs=list(DEFAULT_AUTO_GLOBS))


class TestPathGlobs:
    def test_lockfile_basename_matches_anywhere(self):
        assert path_auto_reason("frontend/package-lock.json", DEFAULT_AUTO_GLOBS)
        assert path_auto_reason("Cargo.lock", DEFAULT_AUTO_GLOBS)
        assert path_auto_reason("sub/dir/uv.lock", DEFAULT_AUTO_GLOBS)

    def test_dist_dir(self):
        assert path_auto_reason("dist/bundle.js", DEFAULT_AUTO_GLOBS)

    def test_source_file_not_matched(self):
        assert path_auto_reason("src/main.py", DEFAULT_AUTO_GLOBS) is None

    def test_custom_glob(self):
        globs = ["generated/*"]
        assert path_auto_reason("generated/api.ts", globs)
        assert path_auto_reason("src/api.ts", globs) is None


class TestFileAuto:
    def test_binary(self):
        fd = compute_file_diff("img.png", b"\x00old", b"\x00new")
        assert file_auto_reason(fd, settings()) == "binary"

    def test_non_utf8(self):
        fd = compute_file_diff("f.txt", b"ok\n", b"\xff\xfe bad")
        assert file_auto_reason(fd, settings()) == "not UTF-8"

    def test_deleted_file(self):
        fd = compute_file_diff("gone.py", b"x\n", None)
        assert file_auto_reason(fd, settings()) == "file deleted"

    def test_normal_source(self):
        fd = compute_file_diff("main.py", b"a\n", b"b\n")
        assert file_auto_reason(fd, settings()) is None


class TestHunkAuto:
    def test_deletion_only_hunk(self):
        fd = compute_file_diff("f", b"a\nGONE\nb\n", b"a\nb\n")
        assert hunk_auto_reason(fd.hunks[0]) == "deletion only"

    def test_whitespace_only(self):
        fd = compute_file_diff("f", b"x=1\n", b"x = 1\n")
        assert hunk_auto_reason(fd.hunks[0]) == "whitespace only"

    def test_real_change(self):
        fd = compute_file_diff("f", b"x = 1\n", b"x = 2\n")
        assert hunk_auto_reason(fd.hunks[0]) is None
