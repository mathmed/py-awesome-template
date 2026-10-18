import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from scripts import risk
from scripts.risk import Assessment, Floor, FloorHit, RiskFloorError, RiskLevel

FLOORS_FILE = Path(".github/risk-floors.yaml")


def completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="fatal: bad ref")


@pytest.fixture
def floors() -> tuple[Floor, ...]:
    return risk.load_floors(FLOORS_FILE)


class TestCommittedFloors:
    @pytest.mark.parametrize(
        ("file", "category"),
        [
            ("pyproject.toml", "pipeline config"),
            (".pre-commit-config.yaml", "pipeline config"),
            ("Makefile", "pipeline config"),
            ("suppressions-baseline.json", "pipeline config"),
            ("scripts/quality_report.py", "pipeline config"),
            (".github/workflows/ci.yml", "pipeline config"),
            (".github/risk-floors.yaml", "pipeline config"),
            (".claude/agents/coder.md", "pipeline config"),
            ("CLAUDE.md", "pipeline config"),
            ("app/infra/database/migrations/0001_init.py", "migrations"),
            ("alembic/versions/0001_init.py", "migrations"),
            ("alembic.ini", "migrations"),
            ("app/presentation/fastapi/middlewares/auth_middleware.py", "auth"),
            ("app/domain/usecases/authentication/login_usecase.py", "auth"),
            ("app/domain/services/permissions.py", "auth"),
        ],
    )
    def test_should_put_sensitive_files_at_high(
        self, floors: tuple[Floor, ...], file: str, category: str
    ) -> None:
        assessment = risk.assess([file], floors)

        assert assessment.floor == RiskLevel.HIGH
        assert [hit.category for hit in assessment.hits] == [category]

    @pytest.mark.parametrize(
        "file",
        [
            "app/domain/usecases/example/create_example_usecase.py",
            "tests/unit/domain/test_x.py",
            "README.md",
            "docker/Dockerfile",
            "uv.lock",
            "app/scripts/helper.py",
        ],
    )
    def test_should_leave_ordinary_files_at_low(self, floors: tuple[Floor, ...], file: str) -> None:
        assert risk.assess([file], floors).floor == RiskLevel.LOW


class TestAssessment:
    @pytest.fixture
    def sut(self) -> Assessment:
        floors = (
            Floor("docs", RiskLevel.MEDIUM, ("docs/**",)),
            Floor("pipeline", RiskLevel.HIGH, ("Makefile",)),
            Floor("unused", RiskLevel.CRITICAL, ("never/**",)),
        )
        return risk.assess(["docs/a.md", "Makefile", "docs/b.md", "app/x.py"], floors)

    def test_should_group_matching_files_by_category(self, sut: Assessment) -> None:
        assert sut.hits == (
            FloorHit("docs", RiskLevel.MEDIUM, ("docs/a.md", "docs/b.md")),
            FloorHit("pipeline", RiskLevel.HIGH, ("Makefile",)),
        )

    def test_should_take_the_highest_level_as_the_floor(self, sut: Assessment) -> None:
        assert sut.floor == RiskLevel.HIGH

    def test_should_describe_the_floor_and_the_files(self, sut: Assessment) -> None:
        assert sut.describe() == (
            "Risk floor: high\n- docs (medium): docs/a.md, docs/b.md\n- pipeline (high): Makefile"
        )

    def test_should_be_low_without_hits(self) -> None:
        assessment = Assessment(())

        assert assessment.floor == RiskLevel.LOW
        assert assessment.describe().endswith("no file matches a floor category")


class TestLoadFloors:
    def write(self, tmp_path: Path, content: str) -> Path:
        path = tmp_path / "floors.yaml"
        path.write_text(content)
        return path

    def test_should_load_floors(self, tmp_path: Path) -> None:
        path = self.write(tmp_path, "floors:\n  - {category: x, level: medium, paths: [a/**]}\n")

        assert risk.load_floors(path) == (Floor("x", RiskLevel.MEDIUM, ("a/**",)),)

    @pytest.mark.parametrize(
        ("content", "message"),
        [
            ("[]", "top-level `floors` list"),
            ("floors: [x]", "must be a mapping"),
            ("floors:\n  - {category: x, level: high, paths: []}", "non-empty list of paths"),
            ("floors:\n  - {level: high, paths: [a]}", "needs a category"),
            ("floors:\n  - {category: x, level: urgent, paths: [a]}", "unknown level 'urgent'"),
        ],
    )
    def test_should_reject_invalid_files(self, tmp_path: Path, content: str, message: str) -> None:
        with pytest.raises(RiskFloorError, match=message):
            risk.load_floors(self.write(tmp_path, content))


class TestLabels:
    @pytest.mark.parametrize(
        ("labels", "floor", "problem"),
        [
            (["risk:high"], RiskLevel.HIGH, None),
            (["bug", "risk:critical"], RiskLevel.HIGH, None),
            (["risk:low"], RiskLevel.LOW, None),
            (
                ["risk:medium"],
                RiskLevel.HIGH,
                "risk:medium is below the floor of this PR (risk:high)",
            ),
            ([], RiskLevel.LOW, "expected exactly one risk label"),
            (["risk:low", "risk:high"], RiskLevel.LOW, "expected exactly one risk label"),
            (["risk:urgent"], RiskLevel.LOW, "unknown risk label risk:urgent"),
        ],
    )
    def test_should_require_one_known_label_at_or_above_the_floor(
        self, labels: list[str], floor: RiskLevel, problem: str | None
    ) -> None:
        result = risk.label_problem(labels, floor)

        if problem is None:
            assert result is None
        else:
            assert result is not None
            assert problem in result

    def test_should_parse_the_labels_of_the_event(self) -> None:
        assert risk.parse_labels('["risk:low", "bug"]') == ["risk:low", "bug"]
        assert risk.parse_labels("") == []

    @pytest.mark.parametrize("labels_json", ['{"a": 1}', "[1]"])
    def test_should_reject_labels_that_are_not_a_list_of_strings(self, labels_json: str) -> None:
        with pytest.raises(RiskFloorError, match="JSON list of strings"):
            risk.parse_labels(labels_json)


class TestCommands:
    @pytest.fixture
    def git(self, mocker: MockerFixture) -> MagicMock:
        return mocker.patch(
            "scripts.risk.subprocess.run", return_value=completed("Makefile\nREADME.md\nMakefile\n")
        )

    def test_should_list_both_sides_of_renames_against_the_merge_base(self, git: MagicMock) -> None:
        assert risk.changed_files("origin/main") == ["Makefile", "README.md"]
        assert git.call_args.args[0] == [
            "git",
            "diff",
            "--name-only",
            "--no-renames",
            "origin/main...HEAD",
        ]

    def test_should_fail_when_the_base_cannot_be_diffed(self, mocker: MockerFixture) -> None:
        mocker.patch("scripts.risk.subprocess.run", return_value=completed(returncode=128))

        assert risk.main(["--base", "origin/nope", "floor"]) == 1

    def test_should_print_the_floor(
        self, git: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert risk.main(["floor"]) == 0
        assert capsys.readouterr().out.startswith("Risk floor: high\n- pipeline config (high)")

    def test_should_pass_with_a_label_at_the_floor(
        self, git: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert risk.main(["check", "--labels-json", '["risk:high"]']) == 0
        assert "at or above the floor" in capsys.readouterr().out

    def test_should_fail_with_a_label_below_the_floor(
        self, git: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert risk.main(["check", "--labels-json", '["risk:low"]']) == 1
        assert "risk:low is below the floor" in capsys.readouterr().err
