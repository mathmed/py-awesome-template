import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

import yaml

DEFAULT_FLOORS = Path(".github/risk-floors.yaml")
LABEL_PREFIX = "risk:"
GIT_TIMEOUT_SECONDS = 60


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return list(RiskLevel).index(self)

    @property
    def label(self) -> str:
        return f"{LABEL_PREFIX}{self.value}"


class RiskFloorError(Exception):
    pass


@dataclass(frozen=True)
class Floor:
    category: str
    level: RiskLevel
    patterns: tuple[str, ...]

    def matches(self, file: str) -> bool:
        path = PurePosixPath(file)
        return any(path.full_match(pattern) for pattern in self.patterns)


@dataclass(frozen=True)
class FloorHit:
    category: str
    level: RiskLevel
    files: tuple[str, ...]


@dataclass(frozen=True)
class Assessment:
    hits: tuple[FloorHit, ...]

    @property
    def floor(self) -> RiskLevel:
        return max(
            (hit.level for hit in self.hits), key=lambda level: level.rank, default=RiskLevel.LOW
        )

    def describe(self) -> str:
        lines = [f"Risk floor: {self.floor}"]
        lines += [f"- {hit.category} ({hit.level}): {', '.join(hit.files)}" for hit in self.hits]
        if not self.hits:
            lines.append("- no file matches a floor category")
        return "\n".join(lines)


def parse_floor(entry: object) -> Floor:
    if not isinstance(entry, dict):
        raise RiskFloorError(f"each floor must be a mapping, got: {entry!r}")
    category, level, paths = entry.get("category"), entry.get("level"), entry.get("paths")
    if not isinstance(category, str) or not isinstance(paths, list) or not paths:
        raise RiskFloorError(
            f"each floor needs a category and a non-empty list of paths: {entry!r}"
        )
    if level not in set(RiskLevel):
        raise RiskFloorError(f"unknown level {level!r} in floor {category!r}")
    return Floor(category, RiskLevel(level), tuple(str(path) for path in paths))


def load_floors(path: Path) -> tuple[Floor, ...]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict) or not isinstance(data.get("floors"), list):
        raise RiskFloorError(f"{path} must have a top-level `floors` list")
    return tuple(parse_floor(entry) for entry in data["floors"])


def assess(files: list[str], floors: tuple[Floor, ...]) -> Assessment:
    hits = []
    for floor in floors:
        matched = tuple(file for file in files if floor.matches(file))
        if matched:
            hits.append(FloorHit(floor.category, floor.level, matched))
    return Assessment(tuple(hits))


def changed_files(base_ref: str) -> list[str]:
    # --no-renames lists both sides of a rename: moving a file out of a floor path counts too
    result = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", f"{base_ref}...HEAD"],
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        raise RiskFloorError(f"could not diff against {base_ref}: {result.stderr.strip()}")
    return sorted(set(result.stdout.splitlines()))


def risk_labels(labels: list[str]) -> list[str]:
    return [label for label in labels if label.startswith(LABEL_PREFIX)]


def label_problem(labels: list[str], floor: RiskLevel) -> str | None:
    found = risk_labels(labels)
    valid = [level.label for level in RiskLevel]
    if len(found) != 1:
        return f"expected exactly one risk label ({', '.join(valid)}), found: {found or 'none'}"
    if found[0] not in valid:
        return f"unknown risk label {found[0]}: use one of {', '.join(valid)}"
    level = RiskLevel(found[0].removeprefix(LABEL_PREFIX))
    if level.rank < floor.rank:
        return f"{found[0]} is below the floor of this PR ({floor.label})"
    return None


def parse_labels(labels_json: str) -> list[str]:
    labels = json.loads(labels_json or "[]")
    if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
        raise RiskFloorError(f"--labels-json must be a JSON list of strings, got: {labels_json}")
    return labels


def floor_command(base_ref: str, floors_path: Path) -> int:
    print(assess(changed_files(base_ref), load_floors(floors_path)).describe())
    return 0


def check_command(base_ref: str, floors_path: Path, labels_json: str) -> int:
    assessment = assess(changed_files(base_ref), load_floors(floors_path))
    print(assessment.describe())
    problem = label_problem(parse_labels(labels_json), assessment.floor)
    if problem:
        print(f"Risk label check failed: {problem}.", file=sys.stderr)
        return 1
    print("Risk label is at or above the floor.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--floors", type=Path, default=DEFAULT_FLOORS)
    parser.add_argument("--base", default="origin/main")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("floor", help="print the risk floor of the changes against --base")
    check = commands.add_parser("check", help="fail when the PR's risk label is below the floor")
    check.add_argument("--labels-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "floor":
            return floor_command(args.base, args.floors)
        return check_command(args.base, args.floors, args.labels_json)
    except RiskFloorError as error:
        print(f"Risk label check failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
