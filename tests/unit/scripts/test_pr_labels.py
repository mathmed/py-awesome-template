import pytest

from scripts import pr_labels
from scripts.pr_labels import (
    DEPLOY_LABELS,
    RISK_LABELS,
    DeployKind,
    LabelGroup,
    PrLabelError,
    RiskLevel,
)


class TestLabelGroup:
    @pytest.fixture
    def sut(self) -> LabelGroup:
        return LabelGroup("deploy", tuple(DeployKind))

    def test_should_build_the_labels_of_every_value(self, sut: LabelGroup) -> None:
        assert sut.prefix == "deploy:"
        assert sut.labels == (
            "deploy:none",
            "deploy:simple",
            "deploy:migration",
            "deploy:coordinated",
        )

    @pytest.mark.parametrize(
        ("labels", "problem"),
        [
            (["deploy:none"], None),
            (["deploy:simple"], None),
            (["deploy:migration"], None),
            (["bug", "risk:high", "deploy:coordinated"], None),
            ([], "expected exactly one deploy label"),
            (["bug", "risk:low"], "expected exactly one deploy label"),
            (["deploy:none", "deploy:migration"], "expected exactly one deploy label"),
            (["deploy:later"], "unknown deploy label deploy:later"),
            (["deployed"], "expected exactly one deploy label"),
        ],
    )
    def test_should_require_exactly_one_known_label(
        self, sut: LabelGroup, labels: list[str], problem: str | None
    ) -> None:
        result = sut.problem(labels)

        if problem is None:
            assert result is None
        else:
            assert result is not None
            assert problem in result

    def test_should_list_every_value_when_none_is_found(self, sut: LabelGroup) -> None:
        assert sut.problem([]) == (
            "expected exactly one deploy label "
            "(deploy:none, deploy:simple, deploy:migration, deploy:coordinated), found: none"
        )

    def test_should_list_the_labels_found_when_there_are_many(self, sut: LabelGroup) -> None:
        assert sut.problem(["deploy:none", "deploy:simple"]) == (
            "expected exactly one deploy label "
            "(deploy:none, deploy:simple, deploy:migration, deploy:coordinated), "
            "found: deploy:none, deploy:simple"
        )

    def test_should_list_every_value_for_an_unknown_label(self, sut: LabelGroup) -> None:
        assert sut.problem(["deploy:later"]) == (
            "unknown deploy label deploy:later: use one of "
            "deploy:none, deploy:simple, deploy:migration, deploy:coordinated"
        )


class TestLabels:
    def test_should_check_the_risk_and_deploy_groups(self) -> None:
        assert pr_labels.LABEL_GROUPS == (RISK_LABELS, DEPLOY_LABELS)
        assert RISK_LABELS.labels == ("risk:low", "risk:medium", "risk:high", "risk:critical")
        assert DEPLOY_LABELS.prefix == "deploy:"

    def test_should_report_no_problem_with_one_label_of_each_group(self) -> None:
        assert pr_labels.label_problems(["bug", "risk:medium", "deploy:simple"]) == []

    def test_should_report_one_problem_per_group(self) -> None:
        problems = pr_labels.label_problems(["risk:urgent"])

        assert len(problems) == 2
        assert problems[0].startswith("unknown risk label risk:urgent")
        assert problems[1].startswith("expected exactly one deploy label")

    def test_should_parse_the_labels_of_the_event(self) -> None:
        assert pr_labels.parse_labels('["risk:low", "bug"]') == ["risk:low", "bug"]
        assert pr_labels.parse_labels("") == []

    @pytest.mark.parametrize("labels_json", ['{"a": 1}', "[1]"])
    def test_should_reject_labels_that_are_not_a_list_of_strings(self, labels_json: str) -> None:
        with pytest.raises(PrLabelError, match="JSON list of strings"):
            pr_labels.parse_labels(labels_json)


class TestCommands:
    @pytest.mark.parametrize("level", list(RiskLevel))
    @pytest.mark.parametrize("kind", list(DeployKind))
    def test_should_pass_with_one_known_label_of_each_group(
        self, level: RiskLevel, kind: DeployKind, capsys: pytest.CaptureFixture[str]
    ) -> None:
        labels_json = f'["dependencies", "risk:{level}", "deploy:{kind}"]'

        assert pr_labels.main(["check", "--labels-json", labels_json]) == 0
        assert capsys.readouterr().out == (
            "PR labels are set: one risk label and one deploy label.\n"
        )

    def test_should_fail_without_a_deploy_label(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert pr_labels.main(["check", "--labels-json", '["risk:low"]']) == 1

        output = capsys.readouterr()
        assert output.out == ""
        assert output.err == (
            "PR label check failed: expected exactly one deploy label "
            "(deploy:none, deploy:simple, deploy:migration, deploy:coordinated), found: none.\n"
        )

    def test_should_report_both_groups_when_both_are_missing(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert pr_labels.main(["check", "--labels-json", '["bug"]']) == 1

        error = capsys.readouterr().err
        assert "expected exactly one risk label" in error
        assert "expected exactly one deploy label" in error

    def test_should_fail_when_the_labels_are_not_a_list(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert pr_labels.main(["check", "--labels-json", '{"a": 1}']) == 1
        assert "JSON list of strings" in capsys.readouterr().err
