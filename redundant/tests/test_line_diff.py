from unittest import TestCase

from redundant.lines import line_diff, score_line_diff


class LineDiffTestCase(TestCase):

    def test_identical(self):
        result = line_diff("foobar", "foobar")
        self.assertEqual(result, ["foobar"])

    def test_diff_entire(self):
        result = line_diff("abc", "123")
        self.assertEqual(result, [("abc", "123")])

    def test_diff_end(self):
        result = line_diff("foobar", "fooquu")
        self.assertEqual(result, ["foo", ("bar", "quu")])

    def test_diff_start(self):
        result = line_diff("123foo", "abcfoo")
        self.assertEqual(result, [("123", "abc"), "foo"])

    def test_score(self):
        self.assertEqual(0.0, score_line_diff(line_diff("abc", "123")))
        self.assertEqual(1.0, score_line_diff(line_diff("abc", "abc")))
        self.assertEqual(0.5, score_line_diff(line_diff("abcd", "ab34")))
        self.assertEqual(0.8, score_line_diff(line_diff(
            "some text.",
            "Some text!",
        )))
