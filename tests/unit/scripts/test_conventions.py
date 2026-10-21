import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from scripts import conventions, suppressions
from scripts.conventions import Kind, scan_source
from tests.fakes.files import write

MODULE = "app/module.py"
MAX_FUNCTION = conventions.MAX_FUNCTION_LINES
MAX_CLASS = conventions.MAX_CLASS_LINES
GIT_TIMEOUT_SECONDS = 60
SCRIPT_TIMEOUT_SECONDS = 60


def kinds_in(source: str, path: str = MODULE) -> list[Kind]:
    return [occurrence.kind for occurrence in scan_source(path, source)]


def counts_in(source: str, path: str = MODULE) -> Counter[Kind]:
    counts: Counter[Kind] = Counter()
    for occurrence in scan_source(path, source):
        counts[occurrence.kind] += occurrence.count
    return counts


def lines_of(count: int) -> str:
    return "".join(f"value_{index} = {index}\n" for index in range(count))


def function_of(lines: int) -> str:
    return "def run() -> None:\n" + "    pass\n" * (lines - 1)


def indented(source: str) -> str:
    return "".join(f"    {line}\n" for line in source.splitlines())


def class_with_methods(count: int, prefix: str) -> str:
    methods = "".join(f"def {prefix}_{index}(self) -> None: ...\n" for index in range(count))
    return "class Runner:\n" + indented(methods)


class TestPrivateClass:
    @pytest.mark.parametrize("path", ["app/a.py", "tests/a.py", "scripts/a.py"])
    def test_should_count_a_class_named_with_an_underscore(self, path: str) -> None:
        source = "class _Payload:\n    def run(self) -> None:\n        class _Inner: ...\n"

        assert kinds_in(source, path) == [Kind.PRIVATE_CLASS, Kind.PRIVATE_CLASS]

    def test_should_not_count_a_public_class(self) -> None:
        assert kinds_in("class Payload: ...\n") == []


class TestComment:
    def test_should_flag_an_unmarked_block_once_at_its_first_line(self) -> None:
        source = "# first line\n# second line\n\n# another block\n"

        violations = scan_source("tests/a.py", source)

        assert [(item.line, item.kind) for item in violations] == [
            (1, Kind.UNMARKED_COMMENT),
            (4, Kind.UNMARKED_COMMENT),
        ]

    @pytest.mark.parametrize(
        "source",
        [
            "# Constraint: a block\nvalue = 1  # trailing\n",
            "value = 1  # Constraint: a trailing comment\n# then a block\n",
            "value = 1  # Constraint: a trailing comment\nother = 2  # and another\n",
        ],
    )
    def test_should_start_a_block_at_a_comment_on_a_line_of_code(self, source: str) -> None:
        assert kinds_in(source) == [Kind.UNMARKED_COMMENT]

    def test_should_split_blocks_separated_by_code(self) -> None:
        assert kinds_in("# one\nvalue = 1\n# two\n") == [
            Kind.UNMARKED_COMMENT,
            Kind.UNMARKED_COMMENT,
        ]

    @pytest.mark.parametrize("mark", conventions.COMMENT_MARKS)
    def test_should_accept_a_block_that_starts_with_a_case_mark(self, mark: str) -> None:
        source = f"# {mark} the vendor API caps a title at 20 characters,\n# so it is cut.\n"

        assert kinds_in(source) == []

    def test_should_accept_a_marked_comment_at_the_end_of_a_line(self) -> None:
        assert kinds_in("LIMIT = 20  # Constraint: the vendor API caps it\n") == []

    @pytest.mark.parametrize(
        "source",
        [
            "# Explains the loop\n# Pitfall: a mark on a later line does not count\n",
            "# constraint: the mark is case sensitive\n",
            "# Note: not one of the cases\n",
        ],
    )
    def test_should_flag_a_block_whose_first_line_has_no_case_mark(self, source: str) -> None:
        assert kinds_in(source) == [Kind.UNMARKED_COMMENT]

    @pytest.mark.parametrize(
        "comment",
        [
            "# noqa: E501",
            "# type: ignore[arg-type]",
            "# nosec B101",
            "# pragma: no cover",
            "# pragma: no mutate",
            "# pylint: disable=invalid-name",
            "# mypy: ignore-errors",
            "# pyright: ignore",
            "# fmt: off",
            "# fmt: on",
            "# isort: skip_file",
        ],
    )
    def test_should_not_count_tool_directives(self, comment: str) -> None:
        assert kinds_in(f"value = 1  {comment}\n") == []

    def test_should_not_count_the_shebang(self) -> None:
        assert kinds_in("#!/usr/bin/env python\nvalue = 1\n", "scripts/a.py") == []

    def test_should_ignore_comment_text_inside_strings(self) -> None:
        assert kinds_in('text = "# not a comment"\n') == []

    def test_should_skip_every_directive_the_suppression_ratchet_counts(self) -> None:
        counted = {(pattern.pattern, pattern.flags) for _, pattern in suppressions.COMMENT_PATTERNS}
        skipped = {(pattern.pattern, pattern.flags) for pattern in conventions.DIRECTIVE_PATTERNS}

        assert counted <= skipped


class TestDocstring:
    @pytest.mark.parametrize(
        "source",
        [
            '"""Module."""\n',
            'class Payload:\n    """Payload."""\n',
            'def run() -> None:\n    """Run."""\n',
            'async def run() -> None:\n    """Run."""\n',
        ],
    )
    def test_should_count_a_docstring(self, source: str) -> None:
        assert kinds_in(source, "tests/a.py") == [Kind.DOCSTRING]

    def test_should_not_count_a_string_that_is_not_the_first_statement(self) -> None:
        assert kinds_in('def run() -> None:\n    value = 1\n    "not a docstring"\n') == []


class TestLongModule:
    def test_should_count_the_lines_above_the_limit(self) -> None:
        source = lines_of(conventions.MAX_MODULE_LINES + 3)

        occurrences = scan_source(MODULE, source)

        assert [(item.kind, item.line, item.count) for item in occurrences] == [
            (Kind.LONG_MODULE, conventions.MAX_MODULE_LINES + 1, 3)
        ]

    def test_should_not_count_a_module_at_the_limit(self) -> None:
        assert kinds_in(lines_of(conventions.MAX_MODULE_LINES)) == []

    def test_should_only_count_modules_of_the_application(self) -> None:
        assert kinds_in(lines_of(conventions.MAX_MODULE_LINES + 1), "tests/a.py") == []


class TestLongFunction:
    def test_should_add_up_the_lines_above_the_limit_of_each_function(self) -> None:
        source = (
            "class Runner:\n"
            + indented(function_of(MAX_FUNCTION + 1))
            + function_of(MAX_FUNCTION + 2)
        )

        assert counts_in(source) == Counter({Kind.LONG_FUNCTION: 3})

    def test_should_count_a_nested_function_only_through_the_function_around_it(self) -> None:
        source = "def outer() -> None:\n" + indented(function_of(MAX_FUNCTION + 5))

        assert counts_in(source) == Counter({Kind.LONG_FUNCTION: 6})

    def test_should_not_count_a_function_at_the_limit(self) -> None:
        assert kinds_in(function_of(MAX_FUNCTION)) == []

    def test_should_only_count_functions_of_the_application(self) -> None:
        assert kinds_in(function_of(MAX_FUNCTION + 1), "scripts/a.py") == []


class TestLongClass:
    def test_should_count_only_the_outermost_class(self) -> None:
        inner = "class Inner:\n" + indented(lines_of(MAX_CLASS))
        source = "class Runner:\n" + indented(inner)

        assert counts_in(source) == Counter({Kind.LONG_CLASS: 2})

    def test_should_not_count_a_class_at_the_limit(self) -> None:
        assert kinds_in("class Runner:\n" + indented(lines_of(MAX_CLASS - 1))) == []


class TestPublicMethods:
    def test_should_count_the_public_methods_above_the_limit(self) -> None:
        source = class_with_methods(conventions.MAX_PUBLIC_METHODS + 2, "run")

        assert counts_in(source) == Counter({Kind.PUBLIC_METHODS: 2})

    def test_should_not_count_a_class_at_the_limit(self) -> None:
        assert kinds_in(class_with_methods(conventions.MAX_PUBLIC_METHODS, "run")) == []

    def test_should_not_count_private_or_dunder_methods(self) -> None:
        source = class_with_methods(conventions.MAX_PUBLIC_METHODS, "run") + indented(
            "def _helper(self) -> None: ...\ndef __len__(self) -> int: ...\n"
        )

        assert kinds_in(source) == []

    def test_should_check_scripts_but_not_tests(self) -> None:
        source = class_with_methods(conventions.MAX_PUBLIC_METHODS + 1, "run")

        assert kinds_in(source, "scripts/a.py") == [Kind.PUBLIC_METHODS]
        assert kinds_in(source, "tests/a.py") == []


class TestBoolName:
    @pytest.mark.parametrize(
        "source",
        [
            "def valid() -> bool: ...\n",
            "async def valid() -> bool: ...\n",
            "def check() -> 'bool': ...\n",
            "def run(enabled: bool) -> None: ...\n",
            "def run(*, enabled: bool = False) -> None: ...\n",
            "def run(enabled: bool, /) -> None: ...\n",
            "class Payload:\n    def valid(self) -> bool: ...\n",
            "class Payload:\n    enabled: bool\n",
            "class Payload:\n    enabled: bool = False\n",
        ],
    )
    def test_should_count_a_boolean_without_prefix(self, source: str) -> None:
        assert kinds_in(source) == [Kind.BOOL_NAME]

    @pytest.mark.parametrize(
        "source",
        [
            "def is_valid() -> bool: ...\n",
            "def _has_units() -> bool: ...\n",
            "def run(*, should_retry: bool, can_send: bool) -> None: ...\n",
            "def run(_is_private: bool) -> None: ...\n",
            "class Payload:\n    def __eq__(self, other: object) -> bool: ...\n",
            "class Payload:\n    is_enabled: bool\n",
            "class Payload:\n    count: int\n",
            "def run(enabled: bool | None) -> None: ...\n",
            "enabled: bool = False\n",
        ],
    )
    def test_should_not_count_a_prefixed_or_non_boolean_name(self, source: str) -> None:
        assert kinds_in(source) == []

    def test_should_check_scripts_but_not_tests(self) -> None:
        source = "def valid() -> bool: ...\n"

        assert kinds_in(source, "scripts/a.py") == [Kind.BOOL_NAME]
        assert kinds_in(source, "tests/a.py") == []


class TestFileOrder:
    @pytest.mark.parametrize(
        "source",
        [
            "def run() -> None: ...\nLIMIT = 1\n",
            "def run() -> None: ...\n_LIMIT: int = 1\n",
            "def _helper() -> None: ...\ndef run() -> None: ...\n",
            "def _helper() -> None: ...\nclass Payload: ...\n",
            "def run() -> None: ...\nclass Payload: ...\n",
            "def run() -> None: ...\nclass Payload:\n    HANDLERS = (run,)\n",
        ],
    )
    def test_should_count_a_definition_out_of_order(self, source: str) -> None:
        assert kinds_in(source) == [Kind.FILE_ORDER]

    @pytest.mark.parametrize(
        "source",
        [
            "LIMIT = 1\nclass Payload: ...\ndef run() -> None: ...\ndef _helper() -> None: ...\n",
            "class Payload: ...\nPAYLOADS = (Payload(),)\n",
            "def run() -> None: ...\nlogger = run()\n",
            "def run() -> None: ...\nif __name__ == '__main__':\n    run()\n",
            "def run() -> None: ...\nHANDLERS = MappingProxyType({'run': run})\n",
            "def _parse() -> None: ...\nPARSERS = (_parse,)\n",
        ],
    )
    def test_should_not_count_definitions_in_order(self, source: str) -> None:
        assert kinds_in(source) == []

    def test_should_count_a_constant_that_names_no_function_of_the_module(self) -> None:
        assert kinds_in("def run() -> None: ...\nHANDLERS = (print, LIMIT)\n") == [Kind.FILE_ORDER]

    def test_should_only_check_the_application(self) -> None:
        assert kinds_in("def run() -> None: ...\nLIMIT = 1\n", "scripts/a.py") == []


class TestMutableConstant:
    @pytest.mark.parametrize(
        "source",
        [
            "LIMITS = [1, 2]\n",
            "_LIMITS = {'a': 1}\n",
            "NAMES = {'a', 'b'}\n",
            "SQUARES = [n * n for n in range(3)]\n",
            "INDEX = {n: n for n in range(3)}\n",
            "UNIQUE = {n for n in range(3)}\n",
            "LIMITS: dict[str, int] = {}\n",
        ],
    )
    def test_should_count_a_constant_bound_to_a_mutable_literal(self, source: str) -> None:
        assert kinds_in(source) == [Kind.MUTABLE_CONSTANT]

    @pytest.mark.parametrize(
        "source",
        [
            "LIMITS = (1, 2)\n",
            "NAMES = frozenset({'a', 'b'})\n",
            "INDEX = MappingProxyType({'a': 1})\n",
            "limits = [1, 2]\n",
            "class Payload:\n    LIMITS = [1, 2]\n",
        ],
    )
    def test_should_not_count_an_immutable_or_non_constant_value(self, source: str) -> None:
        assert kinds_in(source) == []


class TestTestName:
    @pytest.mark.parametrize(
        "source",
        [
            "def test_sends() -> None: ...\n",
            "async def test_sends() -> None: ...\n",
            "class TestChannel:\n    def test_sends(self) -> None: ...\n",
        ],
    )
    def test_should_count_a_test_not_named_test_should(self, source: str) -> None:
        assert kinds_in(source, "tests/a.py") == [Kind.TEST_NAME]

    @pytest.mark.parametrize(
        "source",
        [
            "def test_should_send() -> None: ...\n",
            "def helper() -> None: ...\n",
            "@fixture\ndef test_settings() -> None: ...\n",
            "@pytest.fixture(scope='session')\ndef test_settings() -> None: ...\n",
        ],
    )
    def test_should_not_count_a_test_should_or_a_fixture(self, source: str) -> None:
        assert kinds_in(source, "tests/a.py") == []

    def test_should_only_check_the_tests(self) -> None:
        assert kinds_in("def test_sends() -> None: ...\n") == []


class TestScanSource:
    def test_should_fail_loudly_on_invalid_python(self) -> None:
        with pytest.raises(SyntaxError):
            scan_source(MODULE, "def broken(:\n")

    def test_should_fail_on_a_file_outside_the_known_scopes(self) -> None:
        with pytest.raises(ValueError, match="docs"):
            scan_source("docs/env.py", "value = 1\n")


class TestScan:
    def test_should_scan_every_root_relative_to_its_name(self, tmp_path: Path) -> None:
        write(tmp_path, "app/domain/a.py", "class _Payload: ...\n")
        write(tmp_path, "tests/b.py", "def test_sends() -> None: ...\n")
        write(tmp_path, "app/notes.md", "# a note\n")

        violations = conventions.scan([tmp_path / "app", tmp_path / "tests"])

        assert [(item.path, item.kind) for item in violations] == [
            ("app/domain/a.py", Kind.PRIVATE_CLASS),
            ("tests/b.py", Kind.TEST_NAME),
        ]

    def test_should_fail_when_a_root_does_not_exist(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="root not found"):
            conventions.scan([tmp_path / "app"])

    def test_should_have_no_violation_in_the_repository(self) -> None:
        assert conventions.scan(conventions.DEFAULT_ROOTS) == ()

    def test_should_cover_every_directory_with_python_in_the_repository(self) -> None:
        tracked = subprocess.run(
            ["git", "ls-files", "*.py"],
            capture_output=True,
            text=True,
            check=True,
            timeout=GIT_TIMEOUT_SECONDS,
        ).stdout.split()

        directories = {Path(name).parts[0] for name in tracked}

        assert directories == {root.name for root in conventions.DEFAULT_ROOTS}

    def test_should_serialize_the_result_line(self) -> None:
        violation = conventions.Violation(MODULE, 401, Kind.LONG_MODULE, 7)

        line = conventions.result_line((violation,))

        payload = json.loads(line.removeprefix(conventions.RESULT_PREFIX))
        assert payload == {
            "total": 1,
            "totals": {"long-module": 1},
            "violations": [{"path": MODULE, "line": 401, "kind": "long-module", "count": 7}],
        }


class TestCommands:
    @pytest.fixture
    def root(self, tmp_path: Path) -> Path:
        write(tmp_path, "app/a.py", "class _One: ...\nclass _Two: ...\n")
        return tmp_path / "app"

    @pytest.fixture
    def clean_root(self, tmp_path: Path) -> Path:
        write(tmp_path, "clean/app/a.py", "class Payload: ...\n")
        return tmp_path / "clean" / "app"

    def run(self, root: Path) -> int:
        return conventions.main(["--root", str(root)])

    def test_should_fail_listing_every_violation_with_file_line_and_kind(
        self, root: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert self.run(root) == 1
        output = capsys.readouterr().out
        assert output.startswith("Convention violations: 2\n")
        assert "  app/a.py:1: private-class\n  app/a.py:2: private-class\n" in output
        assert output.splitlines()[-1].startswith(conventions.RESULT_PREFIX)

    def test_should_pass_without_violations(
        self, clean_root: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert self.run(clean_root) == 0
        assert capsys.readouterr().out.endswith("No convention violations.\n")

    def test_should_run_as_a_file_like_the_other_scripts(self, clean_root: Path) -> None:
        command = ["--root", str(clean_root)]

        result = subprocess.run(
            [sys.executable, "scripts/conventions.py", *command],
            capture_output=True,
            text=True,
            check=False,
            timeout=SCRIPT_TIMEOUT_SECONDS,
        )

        assert result.returncode == 0
        assert result.stdout.endswith("No convention violations.\n")
