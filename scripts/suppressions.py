import argparse
import ast
import io
import json
import re
import sys
import tokenize
import tomllib
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

DEFAULT_BASELINE = Path("suppressions-baseline.json")
DEFAULT_PYPROJECT = Path("pyproject.toml")
DEFAULT_ROOTS = (Path("app"), Path("scripts"), Path("tests"))
RESULT_PREFIX = "SUPPRESSIONS_RESULT: "
RUFF_IGNORE_TABLES = ("per-file-ignores", "extend-per-file-ignores")
# Constraint: ruff reads a ruff.toml or .ruff.toml before the pyproject.toml of its directory, and
# one in a subdirectory applies to the files under it, so the ignores there would escape the count.
RUFF_CONFIG_FILES = ("ruff.toml", ".ruff.toml")


class Kind(StrEnum):
    NOQA = "noqa"
    TYPE_IGNORE = "type-ignore"
    NOSEC = "nosec"
    NO_COVER = "no-cover"
    NO_MUTATE = "no-mutate"
    PYLINT = "pylint-disable"
    MYPY = "mypy-directive"
    PYRIGHT = "pyright-directive"
    FORMATTER = "formatter-off"
    TEST_SKIP = "test-skip"
    TEST_XFAIL = "test-xfail"
    RUFF_FILE_IGNORE = "ruff-per-file-ignore"


COMMENT_PATTERNS: tuple[tuple[Kind, re.Pattern[str]], ...] = (
    (Kind.NOQA, re.compile(r"\bnoqa\b", re.IGNORECASE)),
    (Kind.TYPE_IGNORE, re.compile(r"\btype:\s*ignore\b")),
    (Kind.NOSEC, re.compile(r"\bnosec\b", re.IGNORECASE)),
    (Kind.NO_COVER, re.compile(r"\bpragma:\s*no\s*(?:cover|branch)\b", re.IGNORECASE)),
    # Tradeoff: mutation testing is a gate here, so a mutant left out of the score is a weakened
    # check too.
    (Kind.NO_MUTATE, re.compile(r"\bpragma:\s*no\s*mutate\b", re.IGNORECASE)),
    (Kind.PYLINT, re.compile(r"\bpylint:\s*disable", re.IGNORECASE)),
    (Kind.MYPY, re.compile(r"\bmypy:")),
    (Kind.PYRIGHT, re.compile(r"\bpyright:")),
    (Kind.FORMATTER, re.compile(r"\b(?:fmt|isort|yapf):\s*(?:off|skip|skip_file|disable)\b")),
)
MARK_ATTRIBUTES = {"skip": Kind.TEST_SKIP, "skipif": Kind.TEST_SKIP, "xfail": Kind.TEST_XFAIL}
PYTEST_FUNCTIONS = {
    "skip": Kind.TEST_SKIP,
    "importorskip": Kind.TEST_SKIP,
    "xfail": Kind.TEST_XFAIL,
}
UNITTEST_DECORATORS = {
    "skip": Kind.TEST_SKIP,
    "skipIf": Kind.TEST_SKIP,
    "skipUnless": Kind.TEST_SKIP,
    "expectedFailure": Kind.TEST_XFAIL,
}
SKIP_METHODS = {"skipTest": Kind.TEST_SKIP}
OWNER_ATTRIBUTES = {
    "mark": MARK_ATTRIBUTES,
    "pytest": PYTEST_FUNCTIONS,
    "unittest": UNITTEST_DECORATORS,
}
IMPORTABLE = {"pytest": PYTEST_FUNCTIONS, "unittest": UNITTEST_DECORATORS}
COLLECT_IGNORE_NAMES = frozenset({"collect_ignore", "collect_ignore_glob"})


@dataclass(frozen=True)
class Occurrence:
    path: str
    line: int
    kind: Kind


@dataclass(frozen=True)
class Change:
    path: str
    kind: Kind
    baseline: int
    current: int
    lines: tuple[int, ...]

    @property
    def is_increase(self) -> bool:
        return self.current > self.baseline


@dataclass(frozen=True)
class Comparison:
    occurrences: tuple[Occurrence, ...]
    baseline: Counter[tuple[str, Kind]]

    @property
    def current(self) -> Counter[tuple[str, Kind]]:
        return Counter((item.path, item.kind) for item in self.occurrences)

    @property
    def changes(self) -> tuple[Change, ...]:
        current = self.current
        keys = sorted(set(current) | set(self.baseline))
        return tuple(
            self.change_for(path, kind, current[(path, kind)])
            for path, kind in keys
            if current[(path, kind)] != self.baseline[(path, kind)]
        )

    @property
    def increases(self) -> tuple[Change, ...]:
        return tuple(change for change in self.changes if change.is_increase)

    @property
    def decreases(self) -> tuple[Change, ...]:
        return tuple(change for change in self.changes if not change.is_increase)

    def change_for(self, path: str, kind: Kind, current: int) -> Change:
        lines = tuple(
            item.line for item in self.occurrences if item.path == path and item.kind == kind
        )
        return Change(path, kind, self.baseline[(path, kind)], current, lines)

    def to_result_line(self) -> str:
        return RESULT_PREFIX + json.dumps(
            {
                "total": len(self.occurrences),
                "baseline_total": self.baseline.total(),
                "totals": totals_by_kind(self.current),
                "changes": [
                    {
                        "path": change.path,
                        "kind": change.kind.value,
                        "baseline": change.baseline,
                        "current": change.current,
                        "lines": list(change.lines),
                    }
                    for change in self.changes
                ],
            }
        )


def totals_by_kind(counts: Counter[tuple[str, Kind]]) -> dict[str, int]:
    totals: Counter[str] = Counter()
    for (_, kind), count in counts.items():
        totals[kind.value] += count
    return {kind.value: totals[kind.value] for kind in Kind if totals[kind.value]}


def comment_kinds(source: str) -> Iterator[tuple[int, Kind]]:
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            continue
        for kind, pattern in COMMENT_PATTERNS:
            for _ in pattern.finditer(token.string):
                yield token.start[0], kind


def owner_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def attribute_kind(node: ast.Attribute) -> Kind | None:
    if node.attr in SKIP_METHODS:
        return SKIP_METHODS[node.attr]
    return OWNER_ATTRIBUTES.get(owner_name(node.value), {}).get(node.attr)


def imported_names(tree: ast.Module) -> dict[str, Kind]:
    names: dict[str, Kind] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module not in IMPORTABLE:
            continue
        functions = IMPORTABLE[node.module]
        for alias in node.names:
            if alias.name in functions:
                names[alias.asname or alias.name] = functions[alias.name]
    return names


def node_kind(node: ast.AST, names: dict[str, Kind]) -> Kind | None:
    if isinstance(node, ast.Attribute):
        return attribute_kind(node)
    if not isinstance(node, ast.Name):
        return None
    if isinstance(node.ctx, ast.Store):
        return Kind.TEST_SKIP if node.id in COLLECT_IGNORE_NAMES else None
    return names.get(node.id)


def skip_marker_kinds(tree: ast.Module) -> Iterator[tuple[int, Kind]]:
    names = imported_names(tree)
    for node in ast.walk(tree):
        kind = node_kind(node, names)
        if kind is not None and isinstance(node, ast.expr):
            yield node.lineno, kind


def scan_source(path: str, source: str) -> list[Occurrence]:
    tree = ast.parse(source, filename=path)
    found = [*comment_kinds(source), *skip_marker_kinds(tree)]
    return [Occurrence(path, line, kind) for line, kind in sorted(found)]


def python_files(roots: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.is_dir():
            raise FileNotFoundError(f"suppression scan root not found: {root}")
        files += root.rglob("*.py")
    return sorted(files)


def scan(roots: Iterable[Path]) -> tuple[Occurrence, ...]:
    occurrences: list[Occurrence] = []
    for file in python_files(roots):
        occurrences += scan_source(file.as_posix(), file.read_text(encoding="utf-8"))
    return tuple(occurrences)


def scan_pyproject(path: Path) -> tuple[Occurrence, ...]:
    text = path.read_text(encoding="utf-8")
    ruff = tomllib.loads(text).get("tool", {}).get("ruff", {})
    occurrences: list[Occurrence] = []
    for section in (ruff, ruff.get("lint", {})):
        for table in RUFF_IGNORE_TABLES:
            for pattern, codes in section.get(table, {}).items():
                line = key_line(text, pattern)
                occurrences += [Occurrence(pattern, line, Kind.RUFF_FILE_IGNORE) for _ in codes]
    return tuple(occurrences)


def key_line(text: str, key: str) -> int:
    quoted = (f'"{key}"', f"'{key}'")
    lines = enumerate(text.splitlines(), start=1)
    return next((number for number, line in lines if line.lstrip().startswith(quoted)), 0)


def ruff_config_files(roots: Iterable[Path], pyproject: Path) -> list[Path]:
    top = [pyproject.parent / name for name in RUFF_CONFIG_FILES]
    nested = [file for root in roots for name in RUFF_CONFIG_FILES for file in root.rglob(name)]
    return sorted({file for file in (*top, *nested) if file.exists()})


def scan_repository(roots: list[Path], pyproject: Path) -> tuple[Occurrence, ...]:
    return (*scan(roots), *scan_pyproject(pyproject))


def load_baseline(path: Path) -> Counter[tuple[str, Kind]]:
    if not path.exists():
        return Counter()
    data = json.loads(path.read_text())
    return Counter(
        {
            (file, Kind(kind)): int(count)
            for file, kinds in data.items()
            for kind, count in kinds.items()
        }
    )


def write_baseline(path: Path, counts: Counter[tuple[str, Kind]]) -> None:
    data: dict[str, dict[str, int]] = {}
    for (file, kind), count in sorted(counts.items()):
        data.setdefault(file, {})[kind.value] = count
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def describe(change: Change) -> str:
    lines = ", ".join(str(line) for line in change.lines) or "-"
    return f"  {change.path}: {change.kind} {change.baseline} -> {change.current} (lines: {lines})"


def print_report(comparison: Comparison) -> None:
    print(f"Suppressions: {len(comparison.occurrences)} (baseline {comparison.baseline.total()})")
    for kind, count in totals_by_kind(comparison.current).items():
        print(f"  {kind}: {count}")
    if comparison.increases:
        print("New suppressions (remove them, or get the owner's approval to raise the baseline):")
        print(*(describe(change) for change in comparison.increases), sep="\n")
    if comparison.decreases:
        print("Suppressions removed (lock the improvement in with `make suppressions-update`):")
        print(*(describe(change) for change in comparison.decreases), sep="\n")


def has_ruff_config_files(roots: list[Path], pyproject: Path) -> bool:
    found = ruff_config_files(roots, pyproject)
    if not found:
        return False
    print(
        "Ruff configuration outside pyproject.toml (move it there, where the ignores are counted):"
    )
    print(*(f"  {file.as_posix()}" for file in found), sep="\n")
    return True


def check_command(baseline_path: Path, roots: list[Path], pyproject: Path) -> int:
    if has_ruff_config_files(roots, pyproject):
        return 1
    comparison = Comparison(scan_repository(roots, pyproject), load_baseline(baseline_path))
    print_report(comparison)
    print(comparison.to_result_line())
    if comparison.changes:
        return 1
    print("Suppressions match the baseline.")
    return 0


def update_command(
    baseline_path: Path, roots: list[Path], pyproject: Path, *, can_increase: bool
) -> int:
    if has_ruff_config_files(roots, pyproject):
        return 1
    comparison = Comparison(scan_repository(roots, pyproject), load_baseline(baseline_path))
    print_report(comparison)
    if comparison.increases and not can_increase:
        print(
            "Refusing to raise the baseline: pass --allow-increase only with the owner's approval."
        )
        return 1
    write_baseline(baseline_path, comparison.current)
    print(f"Baseline written to {baseline_path}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--root", type=Path, action="append", dest="roots")
    parser.add_argument("--pyproject", type=Path, default=DEFAULT_PYPROJECT)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="fail when the suppressions differ from the baseline")
    update = commands.add_parser("update", help="rewrite the baseline with the current counts")
    update.add_argument("--allow-increase", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    roots = args.roots or list(DEFAULT_ROOTS)
    if args.command == "check":
        return check_command(args.baseline, roots, args.pyproject)
    return update_command(args.baseline, roots, args.pyproject, can_increase=args.allow_increase)


if __name__ == "__main__":
    sys.exit(main())
