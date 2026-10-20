import pytest

from scripts import risk
from scripts.risk import RiskLabelError, RiskLevel


class TestLabels:
    @pytest.mark.parametrize(
        ("labels", "problem"),
        [
            (["risk:low"], None),
            (["risk:medium"], None),
            (["risk:high"], None),
            (["bug", "risk:critical"], None),
            ([], "expected exactly one risk label"),
            (["bug", "dependencies"], "expected exactly one risk label"),
            (["risk:low", "risk:high"], "expected exactly one risk label"),
            (["risk:urgent"], "unknown risk label risk:urgent"),
        ],
    )
    def test_should_require_exactly_one_known_label(
        self, labels: list[str], problem: str | None
    ) -> None:
        result = risk.label_problem(labels)

        if problem is None:
            assert result is None
        else:
            assert result is not None
            assert problem in result

    def test_should_list_every_level_in_the_problem(self) -> None:
        result = risk.label_problem([])

        assert result == (
            "expected exactly one risk label "
            "(risk:low, risk:medium, risk:high, risk:critical), found: none"
        )

    def test_should_build_the_label_of_a_level(self) -> None:
        assert RiskLevel.HIGH.label == "risk:high"

    def test_should_parse_the_labels_of_the_event(self) -> None:
        assert risk.parse_labels('["risk:low", "bug"]') == ["risk:low", "bug"]
        assert risk.parse_labels("") == []

    @pytest.mark.parametrize("labels_json", ['{"a": 1}', "[1]"])
    def test_should_reject_labels_that_are_not_a_list_of_strings(self, labels_json: str) -> None:
        with pytest.raises(RiskLabelError, match="JSON list of strings"):
            risk.parse_labels(labels_json)


class TestCommands:
    @pytest.mark.parametrize("level", list(RiskLevel))
    def test_should_pass_with_any_single_known_label(
        self, level: RiskLevel, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert risk.main(["check", "--labels-json", f'["dependencies", "{level.label}"]']) == 0
        assert capsys.readouterr().out == "Risk label is set.\n"

    def test_should_fail_without_a_risk_label(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert risk.main(["check", "--labels-json", '["bug"]']) == 1
        assert "expected exactly one risk label" in capsys.readouterr().err

    def test_should_fail_when_the_labels_are_not_a_list(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert risk.main(["check", "--labels-json", '{"a": 1}']) == 1
        assert "JSON list of strings" in capsys.readouterr().err
