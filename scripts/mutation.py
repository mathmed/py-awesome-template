import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

DEFAULT_MIN_SCORE = 90.0
MIN_SCORE_ENV = "MUTATION_MIN_SCORE"
# Machine-readable line read by scripts/quality_report.py (keep the prefix in sync)
RESULT_PREFIX = "MUTATION_RESULT: "
RESULT_LINE = re.compile(r"^\s*(?P<name>\S+): (?P<status>.+?)\s*$")
MUTANT_NAME = re.compile(r"^(?P<module>.+)\.x(?P<function>[^.]+)__mutmut_\d+$")


class MutantStatus(StrEnum):
    KILLED = "killed"
    SURVIVED = "survived"
    TIMEOUT = "timeout"
    SUSPICIOUS = "suspicious"
    NO_TESTS = "no tests"
    SKIPPED = "skipped"
    NOT_CHECKED = "not checked"


@dataclass(frozen=True)
class MutantResult:
    name: str
    status: MutantStatus

    @property
    def module(self) -> str:
        match = MUTANT_NAME.match(self.name)
        return match["module"] if match else self.name

    @property
    def file(self) -> str:
        return self.module.replace(".", "/") + ".py"

    @property
    def function(self) -> str:
        match = MUTANT_NAME.match(self.name)
        return match["function"].replace("ǁ", ".").strip(".") if match else self.name


@dataclass(frozen=True)
class MutationScope:
    source_paths: list[str]
    do_not_mutate: list[str]

    def contains(self, file: str) -> bool:
        if not file.endswith(".py") or file.endswith("__init__.py"):
            return False
        if not any(file.startswith(path.rstrip("/") + "/") for path in self.source_paths):
            return False
        return not any(fnmatch.fnmatch(file, pattern) for pattern in self.do_not_mutate)


@dataclass(frozen=True)
class MutationReport:
    results: list[MutantResult]
    min_score: float

    @property
    def killed(self) -> int:
        return sum(result.status == MutantStatus.KILLED for result in self.results)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def survivors(self) -> list[MutantResult]:
        return [result for result in self.results if result.status != MutantStatus.KILLED]

    @property
    def score(self) -> float:
        return 100.0 if self.total == 0 else self.killed / self.total * 100

    @property
    def passed(self) -> bool:
        return self.score >= self.min_score

    def to_result_line(self) -> str:
        return RESULT_PREFIX + json.dumps(
            {
                "skipped": False,
                "score": self.score,
                "min_score": self.min_score,
                "killed": self.killed,
                "total": self.total,
                "survivors": [
                    {
                        "file": item.file,
                        "function": item.function,
                        "status": item.status.value,
                        "name": item.name,
                    }
                    for item in self.survivors
                ],
            }
        )

    def to_markdown(self) -> str:
        verdict = "✅ passed" if self.passed else "❌ failed"
        lines = [
            "## Mutation testing",
            "",
            f"**Score: {self.score:.1f}%** (minimum {self.min_score:.1f}%, {verdict})",
            "",
            "| Killed 🎉 | Survived / not killed 🙁 | Total |",
            "| --- | --- | --- |",
            f"| {self.killed} | {len(self.survivors)} | {self.total} |",
        ]
        if not self.survivors:
            return "\n".join(lines) + "\n"
        lines += [
            "",
            "### Survivors",
            "",
            "| File | Function | Status | Mutant |",
            "| --- | --- | --- | --- |",
        ]
        lines += [
            f"| `{item.file}` | `{item.function}` | {item.status} | `{item.name}` |"
            for item in self.survivors
        ]
        lines += ["", "Inspect one with `uv run mutmut show <Mutant>`."]
        return "\n".join(lines) + "\n"


def load_scope(pyproject: Path = Path("pyproject.toml")) -> MutationScope:
    config = tomllib.loads(pyproject.read_text())["tool"]["mutmut"]
    return MutationScope(
        source_paths=config["source_paths"], do_not_mutate=config.get("do_not_mutate", [])
    )


def changed_files(base_ref: str) -> list[str]:
    output = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return output.splitlines()


def targets_for(files: list[str], scope: MutationScope) -> list[str]:
    modules = sorted(
        {file.removesuffix(".py").replace("/", ".") for file in files if scope.contains(file)}
    )
    return [f"{module}.*" for module in modules]


def parse_results(output: str) -> list[MutantResult]:
    statuses = {status.value: status for status in MutantStatus}
    results = []
    for line in output.splitlines():
        match = RESULT_LINE.match(line)
        if match and match["status"] in statuses:
            results.append(MutantResult(match["name"], statuses[match["status"]]))
    return results


def filter_by_targets(results: list[MutantResult], targets: list[str]) -> list[MutantResult]:
    if not targets:
        return results
    return [r for r in results if any(fnmatch.fnmatchcase(r.name, target) for target in targets)]


def read_results(targets: list[str]) -> list[MutantResult]:
    output = subprocess.run(
        ["mutmut", "results", "--all", "true"], check=True, capture_output=True, text=True
    ).stdout
    return filter_by_targets(parse_results(output), targets)


def publish(markdown: str) -> None:
    print(markdown)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as handle:
            handle.write(markdown)


def skipped_result_line(min_score: float) -> str:
    return RESULT_PREFIX + json.dumps(
        {
            "skipped": True,
            "score": 100.0,
            "min_score": min_score,
            "killed": 0,
            "total": 0,
            "survivors": [],
        }
    )


def min_score() -> float:
    return float(os.environ.get(MIN_SCORE_ENV, DEFAULT_MIN_SCORE))


def report_command(targets: list[str]) -> int:
    report = MutationReport(read_results(targets), min_score())
    publish(report.to_markdown())
    print(report.to_result_line())
    return 0 if report.passed else 1


def changed_command(base_ref: str) -> int:
    targets = targets_for(changed_files(base_ref), load_scope())
    if not targets:
        message = "## Mutation testing\n\nNo domain files changed, nothing to mutate.\n"
        publish(message)
        print(skipped_result_line(min_score()))
        return 0
    print("Mutating:", *targets, sep="\n  ", flush=True)
    subprocess.run(["mutmut", "run", *targets], check=True)
    return report_command(targets)


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    changed = commands.add_parser("changed")
    changed.add_argument("--base", default="origin/main")
    commands.add_parser("report")
    args = parser.parse_args()
    if args.command == "changed":
        return changed_command(args.base)
    return report_command([])


if __name__ == "__main__":
    sys.exit(main())
