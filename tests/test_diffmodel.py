from typethru.diffmodel import (
    compute_file_diff,
    is_binary,
    is_utf8,
    split_lines,
)


class TestSplitLines:
    def test_empty(self):
        assert split_lines(b"") == []

    def test_trailing_newline(self):
        assert split_lines(b"a\nb\n") == [b"a\n", b"b\n"]

    def test_no_trailing_newline(self):
        assert split_lines(b"a\nb") == [b"a\n", b"b"]

    def test_crlf_preserved(self):
        assert split_lines(b"a\r\nb\r\n") == [b"a\r\n", b"b\r\n"]

    def test_roundtrip(self):
        for data in (b"", b"x", b"x\n", b"a\r\nb\n\nc", b"\n\n\n"):
            assert b"".join(split_lines(data)) == data


class TestComputeFileDiff:
    def test_no_change(self):
        fd = compute_file_diff("f", b"a\nb\n", b"a\nb\n")
        assert fd.hunks == []

    def test_single_modification(self):
        fd = compute_file_diff("f", b"a\nb\nc\n", b"a\nB\nc\n")
        assert len(fd.hunks) == 1
        hunk = fd.hunks[0]
        assert [ln.kind for ln in hunk.display] == ["ctx", "del", "add", "ctx"]
        assert hunk.add_lines[0].text == "B"
        assert hunk.add_lines[0].target_lineno == 2

    def test_new_file(self):
        fd = compute_file_diff("f", None, b"x\ny\n")
        assert len(fd.hunks) == 1
        assert [ln.kind for ln in fd.hunks[0].display] == ["add", "add"]

    def test_deleted_file(self):
        fd = compute_file_diff("f", b"x\n", None)
        assert len(fd.hunks) == 1
        assert fd.hunks[0].add_lines == []

    def test_distant_changes_make_separate_hunks(self):
        base = b"".join(b"line%d\n" % i for i in range(30))
        target = base.replace(b"line2\n", b"LINE2\n").replace(b"line25\n", b"LINE25\n")
        fd = compute_file_diff("f", base, target)
        assert len(fd.hunks) == 2

    def test_close_changes_merge_into_one_hunk(self):
        base = b"a\nb\nc\nd\ne\n"
        target = b"A\nb\nc\nd\nE\n"
        fd = compute_file_diff("f", base, target)
        assert len(fd.hunks) == 1

    def test_whitespace_only_hunk(self):
        fd = compute_file_diff("f", b"x = 1\ny\n", b"x  =  1\ny\n")
        assert fd.hunks[0].is_whitespace_only()

    def test_substantive_hunk_not_whitespace_only(self):
        fd = compute_file_diff("f", b"x = 1\n", b"x = 2\n")
        assert not fd.hunks[0].is_whitespace_only()


class TestReconstruct:
    def test_all_applied_is_byte_identical(self):
        base = b"def f():\r\n    return 1\r\n\r\nprint(f())\r\n"
        target = b"def f(x):\r\n    return x + 1\r\n\r\nprint(f(2))\r\n"
        fd = compute_file_diff("f", base, target)
        applied = {h.index for h in fd.hunks}
        assert fd.reconstruct(applied) == target

    def test_none_applied_is_base(self):
        base = b"a\nb\nc\n"
        target = b"A\nb\nC\n"
        fd = compute_file_diff("f", base, target)
        assert fd.reconstruct(set()) == base

    def test_subset_applied(self):
        base = b"".join(b"line%d\n" % i for i in range(30))
        target = base.replace(b"line2\n", b"LINE2\n").replace(b"line25\n", b"LINE25\n")
        fd = compute_file_diff("f", base, target)
        first_only = fd.reconstruct({0})
        assert b"LINE2\n" in first_only
        assert b"line25\n" in first_only

    def test_new_file_applied(self):
        fd = compute_file_diff("f", None, b"x\n")
        assert fd.reconstruct({0}) == b"x\n"

    def test_deleted_file(self):
        fd = compute_file_diff("f", b"x\n", None)
        assert fd.reconstruct({0}) is None
        assert fd.reconstruct(set()) == b"x\n"

    def test_missing_trailing_newline_preserved(self):
        base = b"a\nend"
        target = b"a\nEND"
        fd = compute_file_diff("f", base, target)
        assert fd.reconstruct({0}) == target


class TestContentChecks:
    def test_binary(self):
        assert is_binary(b"\x00\x01\x02")
        assert not is_binary(b"plain text\n")
        assert not is_binary(None)

    def test_utf8(self):
        assert is_utf8("héllo".encode("utf-8"))
        assert not is_utf8(b"\xff\xfe\x00bad")
        assert is_utf8(None)
