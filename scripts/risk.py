import argparse
import json
import sys
from enum import StrEnum

LABEL_PREFIX = "risk:"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def label(self) -> str:
        return f"{LABEL_PREFIX}{self.value}"


class RiskLabelError(Exception):
    pass


def risk_labels(labels: list[str]) -> list[str]:
    return [label for label in labels if label.startswith(LABEL_PREFIX)]


def label_problem(labels: list[str]) -> str | None:
    found = risk_labels(labels)
    valid = [level.label for level in RiskLevel]
    if len(found) != 1:
        return f"expected exactly one risk label ({', '.join(valid)}), found: {found or 'none'}"
    if found[0] not in valid:
        return f"unknown risk label {found[0]}: use one of {', '.join(valid)}"
    return None


def parse_labels(labels_json: str) -> list[str]:
    labels = json.loads(labels_json or "[]")
    if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
        raise RiskLabelError(f"--labels-json must be a JSON list of strings, got: {labels_json}")
    return labels


def check_command(labels_json: str) -> int:
    problem = label_problem(parse_labels(labels_json))
    if problem:
        print(f"Risk label check failed: {problem}.", file=sys.stderr)
        return 1
    print("Risk label is set.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="fail unless the PR has exactly one known risk label")
    check.add_argument("--labels-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return check_command(args.labels_json)
    except RiskLabelError as error:
        print(f"Risk label check failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
