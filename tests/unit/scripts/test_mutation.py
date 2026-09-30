import json
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from scripts import mutation
from scripts.mutation import (
    MutantResult,
    MutantStatus,
    MutationReport,
    MutationScope,
)

CREATE = (
    "app.domain.usecases.example.create_example_usecase.xǁCreateExampleUsecaseǁexecute__mutmut_1"
)
RESULTS_OUTPUT = f"""    {CREATE}: killed
    app.domain.errors.domain_errors.xǁDomainErrorǁ__init____mutmut_1: survived
    app.domain.errors.domain_errors.xǁDomainErrorǁ__init____mutmut_2: not checked
"""


@pytest.fixture
def scope() -> MutationScope:
    return MutationScope(source_paths=["app/domain"], do_not_mutate=["app/domain/contracts/*"])


class TestMutationScope:
    @pytest.mark.parametrize(
        ("file", "expected"),
        [
            ("app/domain/usecases/example/create_example_usecase.py", True),
            ("app/domain/contracts/usecase.py", False),
            ("app/domain/usecases/__init__.py", False),
            ("app/infra/database.py", False),
            ("app/domain/README.md", False),
            ("tests/unit/domain/test_x.py", False),
        ],
    )
    def test_should_only_contain_mutable_domain_python_files(
        self, scope: MutationScope, file: str, expected: bool
    ) -> None:
        assert scope.contains(file) is expected


class TestTargets:
    def test_should_build_one_glob_per_changed_domain_module(self, scope: MutationScope) -> None:
        files = ["app/domain/errors/domain_errors.py", "app/infra/x.py", "README.md"]

        assert mutation.targets_for(files, scope) == ["app.domain.errors.domain_errors.*"]

    def test_should_return_no_targets_when_diff_misses_scope(self, scope: MutationScope) -> None:
        assert mutation.targets_for(["README.md", "app/main/main.py"], scope) == []

    def test_should_load_scope_from_pyproject(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[tool.mutmut]\nsource_paths = ["app/domain"]\n')

        assert mutation.load_scope(pyproject) == MutationScope(["app/domain"], [])


class TestResults:
    def test_should_parse_results_and_extract_file_and_function(self) -> None:
        results = mutation.parse_results(RESULTS_OUTPUT)

        assert [r.status for r in results] == [
            MutantStatus.KILLED,
            MutantStatus.SURVIVED,
            MutantStatus.NOT_CHECKED,
        ]
        assert results[1].file == "app/domain/errors/domain_errors.py"
        assert results[1].function == "DomainError.__init__"

    def test_should_filter_results_by_target_globs(self) -> None:
        results = mutation.parse_results(RESULTS_OUTPUT)

        filtered = mutation.filter_by_targets(results, ["app.domain.errors.domain_errors.*"])

        assert len(filtered) == 2
        assert mutation.filter_by_targets(results, []) == results


class TestMutationReport:
    def test_should_fail_when_score_is_below_minimum(self) -> None:
        results = mutation.parse_results(RESULTS_OUTPUT)

        sut = MutationReport(results, min_score=90)

        assert sut.score == pytest.approx(100 / 3)
        assert sut.passed is False
        markdown = sut.to_markdown()
        assert "`app/domain/errors/domain_errors.py` | `DomainError.__init__`" in markdown
        assert "❌ failed" in markdown

    def test_should_pass_when_every_mutant_is_killed(self) -> None:
        sut = MutationReport([MutantResult(CREATE, MutantStatus.KILLED)], min_score=90)

        assert sut.passed is True
        assert "Survivors" not in sut.to_markdown()

    def test_should_pass_with_empty_scope(self) -> None:
        assert MutationReport([], min_score=90).passed is True


class TestCommands:
    def test_should_succeed_fast_when_no_domain_file_changed(
        self, mocker: MockerFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        mocker.patch.object(mutation, "changed_files", return_value=["README.md"])
        mocker.patch.object(mutation, "load_scope", return_value=MutationScope(["app/domain"], []))
        run = mocker.patch("scripts.mutation.subprocess.run")

        assert mutation.changed_command("origin/main") == 0
        run.assert_not_called()
        assert "No domain files changed" in summary.read_text()

    def test_should_run_only_changed_modules_and_gate_on_score(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MUTATION_MIN_SCORE", "99")
        mocker.patch.object(
            mutation, "changed_files", return_value=["app/domain/errors/domain_errors.py"]
        )
        mocker.patch.object(mutation, "load_scope", return_value=MutationScope(["app/domain"], []))
        run = mocker.patch("scripts.mutation.subprocess.run")
        run.return_value.stdout = RESULTS_OUTPUT

        assert mutation.changed_command("origin/main") == 1
        assert run.call_args_list[0].args[0] == [
            "mutmut",
            "run",
            "app.domain.errors.domain_errors.*",
        ]

    def test_should_read_minimum_score_from_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert mutation.min_score() == mutation.DEFAULT_MIN_SCORE
        monkeypatch.setenv("MUTATION_MIN_SCORE", "80.5")
        assert mutation.min_score() == 80.5


class TestResultLine:
    def test_should_emit_machine_readable_result_with_survivors(self) -> None:
        results = [
            MutantResult(CREATE, MutantStatus.KILLED),
            MutantResult(CREATE.replace("_1", "_2"), MutantStatus.SURVIVED),
        ]
        sut = MutationReport(results, min_score=90)

        line = sut.to_result_line()

        assert line.startswith(mutation.RESULT_PREFIX)
        payload = json.loads(line.removeprefix(mutation.RESULT_PREFIX))
        assert payload["skipped"] is False
        assert payload["score"] == 50.0
        assert payload["survivors"][0]["function"] == "CreateExampleUsecase.execute"

    def test_should_emit_skipped_result_when_no_domain_file_changed(
        self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mocker.patch.object(mutation, "changed_files", return_value=["README.md"])
        mocker.patch.object(mutation, "load_scope", return_value=MutationScope(["app/domain"], []))

        mutation.changed_command("origin/main")

        line = next(
            line for line in capsys.readouterr().out.splitlines() if "MUTATION_RESULT" in line
        )
        assert json.loads(line.removeprefix(mutation.RESULT_PREFIX))["skipped"] is True
