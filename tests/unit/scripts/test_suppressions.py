import json
from collections import Counter
from pathlib import Path

import pytest

from scripts import suppressions
from scripts.suppressions import Change, Comparison, Kind, Occurrence, scan_source

HANDLER = "app/handler.py"


def kinds_in(source: str) -> list[Kind]:
    return [occurrence.kind for occurrence in scan_source("x.py", source)]


def write(root: Path, relative: str, source: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    return path


class TestCommentSuppressions:
    @pytest.mark.parametrize(
        ("comment", "kind"),
        [
            ("# noqa", Kind.NOQA),
            ("# noqa: E501", Kind.NOQA),
            ("# ruff: noqa", Kind.NOQA),
            ("# type: ignore", Kind.TYPE_IGNORE),
            ("# type: ignore[arg-type]", Kind.TYPE_IGNORE),
            ("# nosec B101", Kind.NOSEC),
            ("# pragma: no cover", Kind.NO_COVER),
            ("# pragma: no branch", Kind.NO_COVER),
            ("# pylint: disable=invalid-name", Kind.PYLINT),
            ("# mypy: ignore-errors", Kind.MYPY),
            ("# pyright: ignore[reportGeneralTypeIssues]", Kind.PYRIGHT),
            ("# fmt: off", Kind.FORMATTER),
            ("# fmt: skip", Kind.FORMATTER),
            ("# isort: skip_file", Kind.FORMATTER),
        ],
    )
    def test_should_detect_each_comment_suppression(self, comment: str, kind: Kind) -> None:
        assert kinds_in(f"value = 1  {comment}\n") == [kind]

    def test_should_count_every_suppression_in_the_same_comment(self) -> None:
        assert kinds_in("value = 1  # type: ignore[misc]  # noqa: E501\n") == [
            Kind.NOQA,
            Kind.TYPE_IGNORE,
        ]

    def test_should_report_the_line_of_the_comment(self) -> None:
        occurrences = scan_source(HANDLER, "a = 1\n\nb = 2  # nosec\n")

        assert occurrences == [Occurrence(HANDLER, 3, Kind.NOSEC)]

    @pytest.mark.parametrize(
        "source",
        [
            'text = "# noqa"\n',
            'text = """\n# type: ignore\n"""\n',
            "# a regular comment about types\n",
            "skip = True\nif skip:\n    pass\n",
        ],
    )
    def test_should_ignore_text_that_is_not_a_suppression(self, source: str) -> None:
        assert kinds_in(source) == []


class TestTestSkips:
    @pytest.mark.parametrize(
        ("source", "kind"),
        [
            ("import pytest\n@pytest.mark.skip\ndef f(): ...\n", Kind.TEST_SKIP),
            (
                "import pytest\n@pytest.mark.skipif(True, reason='x')\ndef f(): ...\n",
                Kind.TEST_SKIP,
            ),
            ("import pytest\n@pytest.mark.xfail\ndef f(): ...\n", Kind.TEST_XFAIL),
            ("from pytest import mark\n@mark.skip\ndef f(): ...\n", Kind.TEST_SKIP),
            ("import pytest\npytestmark = pytest.mark.skip\n", Kind.TEST_SKIP),
            ("import pytest\ndef f():\n    pytest.skip('x')\n", Kind.TEST_SKIP),
            ("import pytest\nyaml = pytest.importorskip('yaml')\n", Kind.TEST_SKIP),
            ("import pytest\ndef f():\n    pytest.xfail('x')\n", Kind.TEST_XFAIL),
            ("import pytest\np = pytest.param(1, marks=pytest.mark.xfail)\n", Kind.TEST_XFAIL),
            ("from pytest import skip as s\ndef f():\n    s('x')\n", Kind.TEST_SKIP),
            ("import unittest\n@unittest.skipIf(True, 'x')\ndef f(): ...\n", Kind.TEST_SKIP),
            ("import unittest\n@unittest.expectedFailure\ndef f(): ...\n", Kind.TEST_XFAIL),
            ("def test(self):\n    self.skipTest('x')\n", Kind.TEST_SKIP),
        ],
    )
    def test_should_detect_skipped_and_expected_failure_tests(
        self, source: str, kind: Kind
    ) -> None:
        assert kinds_in(source) == [kind]

    def test_should_not_count_other_pytest_marks(self) -> None:
        source = "import pytest\n@pytest.mark.parametrize('a', [1])\ndef f(a): ...\n"

        assert kinds_in(source) == []

    def test_should_fail_loudly_on_invalid_python(self) -> None:
        with pytest.raises(SyntaxError):
            scan_source("x.py", "def broken(:\n")


class TestScan:
    def test_should_scan_python_files_under_every_root(self, tmp_path: Path) -> None:
        write(tmp_path, "app/a.py", "a = 1  # noqa\n")
        write(tmp_path, "tests/b.py", "b = 1  # type: ignore\n")
        write(tmp_path, "app/notes.md", "# noqa\n")

        occurrences = suppressions.scan([tmp_path / "app", tmp_path / "tests"])

        assert [(Path(item.path).name, item.kind) for item in occurrences] == [
            ("a.py", Kind.NOQA),
            ("b.py", Kind.TYPE_IGNORE),
        ]

    def test_should_fail_when_a_root_does_not_exist(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="root not found"):
            suppressions.scan([tmp_path / "missing"])


class TestComparison:
    @pytest.fixture
    def sut(self) -> Comparison:
        occurrences = (
            Occurrence(HANDLER, 3, Kind.NOSEC),
            Occurrence(HANDLER, 9, Kind.NOSEC),
            Occurrence("tests/t.py", 1, Kind.TEST_SKIP),
        )
        baseline = Counter({(HANDLER, Kind.NOSEC): 1, ("app/gone.py", Kind.NOQA): 2})
        return Comparison(occurrences, baseline)

    def test_should_list_increases_with_every_line_of_that_kind_in_the_file(
        self, sut: Comparison
    ) -> None:
        assert sut.increases == (
            Change(HANDLER, Kind.NOSEC, 1, 2, (3, 9)),
            Change("tests/t.py", Kind.TEST_SKIP, 0, 1, (1,)),
        )

    def test_should_list_decreases_including_files_that_no_longer_exist(
        self, sut: Comparison
    ) -> None:
        assert sut.decreases == (Change("app/gone.py", Kind.NOQA, 2, 0, ()),)

    def test_should_have_no_changes_when_counts_match(self) -> None:
        occurrences = (Occurrence(HANDLER, 3, Kind.NOSEC),)

        comparison = Comparison(occurrences, Counter({(HANDLER, Kind.NOSEC): 1}))

        assert comparison.changes == ()

    def test_should_count_a_moved_suppression_as_an_increase(self) -> None:
        occurrences = (Occurrence("app/other.py", 1, Kind.NOSEC),)

        comparison = Comparison(occurrences, Counter({(HANDLER, Kind.NOSEC): 1}))

        assert [change.path for change in comparison.increases] == ["app/other.py"]
        assert [change.path for change in comparison.decreases] == [HANDLER]

    def test_should_serialize_the_result_line(self, sut: Comparison) -> None:
        line = sut.to_result_line()

        payload = json.loads(line.removeprefix(suppressions.RESULT_PREFIX))
        assert line.startswith(suppressions.RESULT_PREFIX)
        assert payload["total"] == 3
        assert payload["baseline_total"] == 3
        assert payload["totals"] == {"nosec": 2, "test-skip": 1}
        assert payload["changes"][0] == {
            "path": "app/gone.py",
            "kind": "noqa",
            "baseline": 2,
            "current": 0,
            "lines": [],
        }


class TestBaseline:
    def test_should_treat_a_missing_baseline_as_empty(self, tmp_path: Path) -> None:
        assert suppressions.load_baseline(tmp_path / "missing.json") == Counter()

    def test_should_round_trip_the_baseline(self, tmp_path: Path) -> None:
        path = tmp_path / "baseline.json"
        counts = Counter({(HANDLER, Kind.NOSEC): 1, (HANDLER, Kind.NOQA): 2})

        suppressions.write_baseline(path, counts)

        assert suppressions.load_baseline(path) == counts
        assert json.loads(path.read_text()) == {HANDLER: {"noqa": 2, "nosec": 1}}

    def test_should_reject_an_unknown_kind(self, tmp_path: Path) -> None:
        path = tmp_path / "baseline.json"
        path.write_text(json.dumps({HANDLER: {"unknown": 1}}))

        with pytest.raises(ValueError, match="unknown"):
            suppressions.load_baseline(path)


class TestCommands:
    @pytest.fixture
    def root(self, tmp_path: Path) -> Path:
        write(tmp_path, "app/a.py", "a = 1  # noqa\nb = 2  # noqa\n")
        return tmp_path / "app"

    @pytest.fixture
    def baseline(self, tmp_path: Path) -> Path:
        return tmp_path / "baseline.json"

    def run(self, baseline: Path, root: Path, *command: str) -> int:
        return suppressions.main(["--baseline", str(baseline), "--root", str(root), *command])

    def lock(self, baseline: Path, root: Path, count: int) -> None:
        file = (root / "a.py").as_posix()
        suppressions.write_baseline(baseline, Counter({(file, Kind.NOQA): count}))

    def test_should_pass_when_suppressions_match_the_baseline(
        self, baseline: Path, root: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self.lock(baseline, root, 2)

        assert self.run(baseline, root, "check") == 0
        assert "Suppressions match the baseline." in capsys.readouterr().out

    def test_should_fail_when_a_suppression_is_added(
        self, baseline: Path, root: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self.lock(baseline, root, 1)

        assert self.run(baseline, root, "check") == 1
        output = capsys.readouterr().out
        assert "New suppressions" in output
        assert "noqa 1 -> 2 (lines: 1, 2)" in output

    def test_should_fail_when_the_baseline_is_stale(
        self, baseline: Path, root: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self.lock(baseline, root, 3)

        assert self.run(baseline, root, "check") == 1
        assert "make suppressions-update" in capsys.readouterr().out

    def test_should_lower_the_baseline_on_update(self, baseline: Path, root: Path) -> None:
        self.lock(baseline, root, 3)

        assert self.run(baseline, root, "update") == 0
        assert self.run(baseline, root, "check") == 0

    def test_should_refuse_to_raise_the_baseline_without_the_flag(
        self, baseline: Path, root: Path
    ) -> None:
        self.lock(baseline, root, 1)

        assert self.run(baseline, root, "update") == 1
        assert self.run(baseline, root, "check") == 1

    def test_should_raise_the_baseline_with_the_flag(self, baseline: Path, root: Path) -> None:
        self.lock(baseline, root, 1)

        assert self.run(baseline, root, "update", "--allow-increase") == 0
        assert self.run(baseline, root, "check") == 0
