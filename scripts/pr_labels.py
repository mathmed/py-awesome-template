import argparse
import json
import sys
from dataclasses import dataclass
from enum import StrEnum


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DeployKind(StrEnum):
    NONE = "none"
    SIMPLE = "simple"
    MIGRATION = "migration"
    COORDINATED = "coordinated"


class PrLabelError(Exception):
    pass


@dataclass(frozen=True)
class LabelGroup:
    name: str
    values: tuple[str, ...]

    @property
    def prefix(self) -> str:
        return f"{self.name}:"

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(f"{self.prefix}{value}" for value in self.values)

    def problem(self, labels: list[str]) -> str | None:
        found = [label for label in labels if label.startswith(self.prefix)]
        valid = ", ".join(self.labels)
        if len(found) != 1:
            return f"expected exactly one {self.name} label ({valid}), found: {', '.join(found) or 'none'}"
        if found[0] not in self.labels:
            return f"unknown {self.name} label {found[0]}: use one of {valid}"
        return None


RISK_LABELS = LabelGroup("risk", tuple(RiskLevel))
DEPLOY_LABELS = LabelGroup("deploy", tuple(DeployKind))
LABEL_GROUPS = (RISK_LABELS, DEPLOY_LABELS)


def label_problems(labels: list[str]) -> list[str]:
    return [problem for group in LABEL_GROUPS if (problem := group.problem(labels)) is not None]


def parse_labels(labels_json: str) -> list[str]:
    labels = json.loads(labels_json or "[]")
    if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
        raise PrLabelError(f"--labels-json must be a JSON list of strings, got: {labels_json}")
    return labels


def check_command(labels_json: str) -> int:
    problems = label_problems(parse_labels(labels_json))
    for problem in problems:
        print(f"PR label check failed: {problem}.", file=sys.stderr)
    if problems:
        return 1
    print("PR labels are set: one risk label and one deploy label.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser(
        "check",
        help="fail unless the PR has exactly one known risk label and one known deploy label",
    )
    check.add_argument("--labels-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return check_command(args.labels_json)
    except PrLabelError as error:
        print(f"PR label check failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
