import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

MARKER = "<!-- quality-report -->"
DEFAULT_DIRECTORY = Path("quality-fragments")
DEFAULT_BASE_NAME = "main"
MAX_DETAILS_CHARS = 6000
MAX_SURVIVORS_LISTED = 50
MAX_VULNERABILITIES_LISTED = 50
MAX_FAILED_TESTS_LISTED = 30
MAX_FAILURE_MESSAGE_CHARS = 160
# Must match scripts/mutation.py, which prints this line followed by a JSON document
MUTATION_RESULT_PREFIX = "MUTATION_RESULT: "
# Must match scripts/suppressions.py, which prints this line followed by a JSON document
SUPPRESSIONS_RESULT_PREFIX = "SUPPRESSIONS_RESULT: "
MAX_SUPPRESSION_CHANGES_LISTED = 50
UV_NOISE = re.compile(r"^warning: `VIRTUAL_ENV=.*$", re.MULTILINE)
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M UTC"


class Analysis(StrEnum):
    RUFF_CHECK = "ruff-check"
    RUFF_FORMAT = "ruff-format"
    MYPY = "mypy"
    BANDIT = "bandit"
    PIP_AUDIT = "pip-audit"
    DEPTRY = "deptry"
    VULTURE = "vulture"
    XENON = "xenon"
    PYTEST = "pytest"
    IMPORT_LINTER = "import-linter"
    SMOKE = "smoke"
    MUTATION = "mutation"
    SUPPRESSIONS = "suppressions"
    SCHEMATHESIS = "schemathesis"
    OASDIFF = "oasdiff"


class Status(StrEnum):
    OK = "✅"
    WARNING = "⚠️"
    FAILED = "❌"
    SKIPPED = "⏭️"


class Group(StrEnum):
    CODE = "Code"
    SECURITY = "Security and dependencies"
    BEHAVIOR = "Behavior"
    ARCHITECTURE = "Architecture"


class Alert(StrEnum):
    TIP = "TIP"
    WARNING = "WARNING"
    CAUTION = "CAUTION"


SEVERITY_ORDER = [Status.OK, Status.SKIPPED, Status.WARNING, Status.FAILED]
ATTENTION_STATUSES = frozenset({Status.FAILED, Status.WARNING})


def worst(statuses: list[Status]) -> Status:
    return max(statuses, key=SEVERITY_ORDER.index, default=Status.OK)


@dataclass(frozen=True)
class Fragment:
    analysis: Analysis
    exit_code: int
    output: str
    advisory: bool = False

    @property
    def passed(self) -> bool:
        return self.exit_code == 0

    def write(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.analysis}.json"
        payload = {
            "analysis": self.analysis.value,
            "exit_code": self.exit_code,
            "output": self.output,
            "advisory": self.advisory,
        }
        path.write_text(json.dumps(payload))
        return path

    @classmethod
    def read(cls, path: Path) -> Fragment:
        data = json.loads(path.read_text())
        return cls(
            analysis=Analysis(data["analysis"]),
            exit_code=int(data["exit_code"]),
            output=str(data["output"]),
            advisory=bool(data.get("advisory", False)),
        )


@dataclass(frozen=True)
class Metric:
    label: str
    value: Decimal
    unit: str = ""

    def render(self, base: Metric | None) -> str:
        return f"{self.label} {self.value}{self.unit} ({self.delta(base)})"

    def delta(self, base: Metric | None) -> str:
        if base is None:
            return "n/a"
        difference = self.value - base.value
        if difference == 0:
            return "="
        arrow = "↑" if difference > 0 else "↓"
        return f"{arrow}{abs(difference)}"


@dataclass(frozen=True)
class Finding:
    status: Status
    summary: str
    details: str = ""
    details_title: str = "Output"
    is_markdown: bool = False
    metric: Metric | None = None


@dataclass(frozen=True)
class Section:
    group: Group
    title: str
    job: str
    analyses: tuple[Analysis, ...]
    reproduce: str


SECTIONS = [
    Section(
        Group.CODE,
        "Lint and format (ruff)",
        "lint",
        (Analysis.RUFF_CHECK, Analysis.RUFF_FORMAT),
        "make check-code",
    ),
    Section(Group.CODE, "Types (mypy)", "types", (Analysis.MYPY,), "uv run mypy app tests"),
    Section(
        Group.CODE,
        "Dead code (vulture)",
        "dead-code",
        (Analysis.VULTURE,),
        "uv run vulture app --min-confidence 80",
    ),
    Section(
        Group.CODE,
        "Complexity (xenon)",
        "complexity",
        (Analysis.XENON,),
        "uv run xenon app --max-absolute B --max-modules A --max-average A",
    ),
    Section(
        Group.CODE,
        "Suppressions (ratchet)",
        "suppressions",
        (Analysis.SUPPRESSIONS,),
        "make suppressions",
    ),
    Section(
        Group.SECURITY,
        "Code security (bandit)",
        "security",
        (Analysis.BANDIT,),
        "uv run bandit -r app -ll",
    ),
    Section(
        Group.SECURITY,
        "Vulnerable dependencies (pip-audit)",
        "security",
        (Analysis.PIP_AUDIT,),
        "uv run pip-audit",
    ),
    Section(
        Group.SECURITY,
        "Declared dependencies (deptry)",
        "dependencies",
        (Analysis.DEPTRY,),
        "make deptry",
    ),
    Section(
        Group.BEHAVIOR, "Tests and coverage (pytest)", "tests", (Analysis.PYTEST,), "make test"
    ),
    Section(
        Group.BEHAVIOR, "Boot smoke (/health, /ready)", "smoke", (Analysis.SMOKE,), "make smoke"
    ),
    Section(
        Group.BEHAVIOR,
        "API contract (schemathesis)",
        "contract",
        (Analysis.SCHEMATHESIS,),
        "make contract",
    ),
    Section(
        Group.BEHAVIOR,
        "Breaking API changes (oasdiff)",
        "openapi-diff",
        (Analysis.OASDIFF,),
        "make openapi-diff",
    ),
    Section(
        Group.BEHAVIOR,
        "Mutation testing (mutmut)",
        "mutation",
        (Analysis.MUTATION,),
        "make mutation-changed",
    ),
    Section(
        Group.ARCHITECTURE,
        "Architecture contracts (import-linter)",
        "lint-imports",
        (Analysis.IMPORT_LINTER,),
        "make lint-imports",
    ),
]


@dataclass(frozen=True)
class Baseline:
    name: str
    fragments: dict[Analysis, Fragment]
    run_url: str = ""

    @property
    def is_available(self) -> bool:
        return bool(self.fragments)


@dataclass(frozen=True)
class AnalysisResult:
    analysis: Analysis
    finding: Finding
    base: Finding | None

    @property
    def is_inherited(self) -> bool:
        return (
            self.finding.status == Status.FAILED
            and self.base is not None
            and self.base.status == Status.FAILED
        )

    @property
    def detail(self) -> str:
        if self.finding.metric is None:
            return self.finding.summary
        base_metric = self.base.metric if self.base else None
        metric = self.finding.metric.render(base_metric)
        return f"{self.finding.summary} · {metric}" if self.finding.summary else metric


@dataclass(frozen=True)
class SectionResult:
    section: Section
    status: Status
    results: tuple[AnalysisResult, ...]

    @property
    def is_inherited(self) -> bool:
        failed = [result for result in self.results if result.finding.status == Status.FAILED]
        return bool(failed) and all(result.is_inherited for result in failed)

    @property
    def detail(self) -> str:
        return " · ".join(result.detail for result in self.results if result.detail)


def clean(output: str) -> str:
    return UV_NOISE.sub("", output).strip()


def tail(text: str, limit: int = MAX_DETAILS_CHARS) -> str:
    if len(text) <= limit:
        return text
    return "[...truncated...]\n" + text[-limit:]


def shorten(text: str, limit: int = MAX_FAILURE_MESSAGE_CHARS) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def first_int(pattern: str, text: str, default: int = 0) -> int:
    match = re.search(pattern, text)
    return int(match[1]) if match else default


def plural(count: int, singular: str, plural_form: str) -> str:
    return f"{count} {singular if count == 1 else plural_form}"


def fence(text: str) -> str:
    return "```text\n" + text.replace("```", "'''") + "\n```"


def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def analyze_ruff_check(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.passed:
        return Finding(Status.OK, "no lint issues")
    count = first_int(r"Found (\d+) error", output)
    summary = plural(count, "lint issue", "lint issues") if count else "lint failed"
    return Finding(Status.FAILED, summary, tail(output))


def analyze_ruff_format(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.passed:
        files = first_int(r"(\d+) files? already formatted", output)
        return Finding(Status.OK, f"{plural(files, 'file', 'files')} formatted" if files else "")
    count = len(re.findall(r"^Would reformat: ", output, re.MULTILINE))
    summary = (
        f"{plural(count, 'file', 'files')} to format (`make format-code`)"
        if count
        else "format check failed"
    )
    return Finding(Status.FAILED, summary, tail(output))


def analyze_mypy(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.passed:
        files = first_int(r"no issues found in (\d+) source file", output)
        return Finding(Status.OK, plural(files, "file", "files"))
    errors = first_int(r"Found (\d+) error", output)
    summary = plural(errors, "type error", "type errors") if errors else "mypy failed"
    return Finding(Status.FAILED, summary, tail(output))


def analyze_bandit(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.passed:
        lines = first_int(r"Total lines of code: (\d+)", output)
        scanned = f" · {plural(lines, 'line', 'lines')} scanned" if lines else ""
        return Finding(Status.OK, f"no issues{scanned}")
    issues = len(re.findall(r">> Issue:", output))
    summary = plural(issues, "issue", "issues") if issues else "bandit failed"
    return Finding(Status.FAILED, summary, tail(output))


@dataclass(frozen=True)
class Vulnerability:
    package: str
    version: str
    identifier: str
    fixed_in: str


PIP_AUDIT_HEADER = re.compile(r"^Name\s+Version\s+ID\s+Fix Versions", re.MULTILINE)


def parse_vulnerabilities(output: str) -> list[Vulnerability]:
    header = PIP_AUDIT_HEADER.search(output)
    if header is None:
        return []
    vulnerabilities: list[Vulnerability] = []
    for line in output[header.end() :].splitlines()[2:]:
        parts = line.split()
        if len(parts) < 3:
            break
        fixed_in = " ".join(parts[3:]) or "no fix yet"
        vulnerabilities.append(Vulnerability(parts[0], parts[1], parts[2], fixed_in))
    return vulnerabilities


def vulnerabilities_table(vulnerabilities: list[Vulnerability]) -> str:
    rows = [
        "| Package | Version | CVE | Fixed in |",
        "| --- | --- | --- | --- |",
        *(
            f"| {v.package} | {v.version} | {v.identifier} | {v.fixed_in} |"
            for v in vulnerabilities[:MAX_VULNERABILITIES_LISTED]
        ),
    ]
    hidden = len(vulnerabilities) - MAX_VULNERABILITIES_LISTED
    if hidden > 0:
        rows.append(f"\n... and {hidden} more. Run `uv run pip-audit` for the full list.")
    packages = sorted({v.package for v in vulnerabilities})
    upgrade = " ".join(f"--upgrade-package {package}" for package in packages)
    rows.append(f"\n**Fix**: `uv lock {upgrade}`, then `uv sync`.")
    return "\n".join(rows)


def analyze_pip_audit(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.passed:
        return Finding(Status.OK, "no known vulnerabilities")
    count = first_int(r"Found (\d+) known vulnerabilit", output)
    packages = first_int(r"known vulnerabilit(?:y|ies) in (\d+) package", output)
    vulnerabilities = parse_vulnerabilities(output)
    if not count:
        return Finding(Status.FAILED, "pip-audit failed", tail(output))
    summary = plural(count, "vulnerability", "vulnerabilities")
    if packages:
        summary += f" in {plural(packages, 'package', 'packages')}"
    if not vulnerabilities:
        return Finding(Status.FAILED, summary, tail(output))
    return Finding(Status.FAILED, summary, vulnerabilities_table(vulnerabilities), is_markdown=True)


def analyze_deptry(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.passed:
        files = first_int(r"Scanning (\d+) files?", output)
        scanned = f"{plural(files, 'file', 'files')} · " if files else ""
        return Finding(Status.OK, f"{scanned}no dependency issues")
    count = first_int(r"Found (\d+) dependency issue", output)
    summary = plural(count, "dependency issue", "dependency issues") if count else "deptry failed"
    return Finding(Status.FAILED, summary, tail(output))


def analyze_vulture(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.passed and not output:
        return Finding(Status.OK, "no dead code")
    lines = [line for line in output.splitlines() if line.strip()]
    status = Status.WARNING if fragment.advisory else Status.FAILED
    summary = plural(len(lines), "dead code item", "dead code items")
    if fragment.advisory:
        summary += " (advisory, does not block)"
    return Finding(status, summary, tail(output))


def analyze_xenon(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.passed:
        return Finding(Status.OK, "within the threshold")
    blocks = len(re.findall(r"^ERROR:xenon:", output, re.MULTILINE))
    summary = (
        f"{plural(blocks, 'block', 'blocks')} above the threshold"
        if blocks
        else "complexity above the threshold"
    )
    return Finding(Status.FAILED, summary, tail(output))


def coverage_table(output: str) -> str:
    lines = output.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("Name ")), None)
    if start is None:
        return ""
    end = next((i for i, line in enumerate(lines) if line.startswith("TOTAL")), None)
    if end is None:
        return ""
    return "\n".join(lines[start : end + 1])


FAILED_TEST = re.compile(r"^(?:FAILED|ERROR) (?P<test>\S+)(?: - (?P<message>.+))?$", re.MULTILINE)


def failed_tests_list(output: str) -> str:
    failures = list(FAILED_TEST.finditer(output))
    if not failures:
        return ""
    items = [
        f"- `{match['test']}`" + (f": {shorten(match['message'])}" if match["message"] else "")
        for match in failures[:MAX_FAILED_TESTS_LISTED]
    ]
    hidden = len(failures) - MAX_FAILED_TESTS_LISTED
    if hidden > 0:
        items.append(f"- ... and {hidden} more")
    return "\n".join(items)


def pytest_summary_line(output: str) -> str:
    return next(
        (
            line
            for line in reversed(output.splitlines())
            if re.search(r" in [\d.]+s", line) and re.search(r"\d+ (passed|failed|error)", line)
        ),
        "",
    )


def pytest_failure_details(output: str) -> str:
    failed = failed_tests_list(output)
    raw = fence(tail(output))
    if not failed:
        return raw
    return f"{failed}\n\n<details><summary>Output</summary>\n\n{raw}\n\n</details>"


def analyze_pytest(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    summary_line = pytest_summary_line(output)
    passed = first_int(r"(\d+) passed", summary_line)
    failed = first_int(r"(\d+) failed", summary_line) + first_int(r"(\d+) errors?", summary_line)
    skipped = first_int(r"(\d+) skipped", summary_line)
    total = passed + failed + skipped
    coverage = re.search(r"Total coverage: ([\d.]+)%", output)
    required = re.search(r"Required test coverage of ([\d.]+)%", output)
    metric = Metric("coverage", Decimal(coverage[1]), "%") if coverage else None
    tests = plural(total, "test", "tests") + (f" ({skipped} skipped)" if skipped else "")
    if not summary_line:
        return Finding(Status.FAILED, "pytest failed before finishing", tail(output))
    if failed:
        summary = f"{failed} of {plural(total, 'test', 'tests')} failed"
        details = pytest_failure_details(output)
        return Finding(Status.FAILED, summary, details, is_markdown=True, metric=metric)
    if not fragment.passed:
        minimum = f" {required[1]}%" if required else ""
        summary = f"{tests} · coverage below the{minimum} minimum"
        details = coverage_table(output) or tail(output)
        return Finding(Status.FAILED, summary, details, "Coverage", metric=metric)
    return Finding(Status.OK, tests, coverage_table(output), "Coverage", metric=metric)


CONTRACT_LINE = re.compile(r"^(?P<name>.+?)\s*(?P<state>KEPT|BROKEN)$", re.MULTILINE)


def analyze_import_linter(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    contracts = [(m["name"].strip(), m["state"]) for m in CONTRACT_LINE.finditer(output)]
    kept = first_int(r"(\d+) kept", output)
    broken = first_int(r"(\d+) broken", output)
    if fragment.passed:
        listing = "\n".join(f"{state:6} {name}" for name, state in contracts)
        return Finding(
            Status.OK, plural(kept, "contract kept", "contracts kept"), listing, "Contracts"
        )
    if not contracts:
        return Finding(
            Status.FAILED, "import-linter failed before evaluating the contracts", tail(output)
        )
    broken_names = [name for name, state in contracts if state == "BROKEN"]
    marker = output.find("Broken contracts")
    violation = (
        output[marker:].removeprefix("Broken contracts").lstrip("-\n") if marker >= 0 else output
    )
    broken_list = "\n".join(f"- **{name}**" for name in broken_names)
    details = f"Broken contracts:\n\n{broken_list}\n\n{fence(tail(violation))}"
    summary = f"{broken} of {plural(kept + broken, 'contract', 'contracts')} broken"
    return Finding(Status.FAILED, summary, details, is_markdown=True)


def analyze_smoke(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    seconds = re.search(r">> API healthy after ([\d.]+)s", output)
    if fragment.passed:
        boot = f"healthy in {seconds[1]}s · " if seconds else ""
        return Finding(Status.OK, f"{boot}/health and /ready answered")
    health = ">> GET /health ->" in output
    ready = ">> GET /ready ->" in output
    endpoints = f"/health {'✅' if health else '❌'} · /ready {'✅' if ready else '❌'}"
    reason = re.findall(r"^>> smoke: (.+)$", output, re.MULTILINE)
    started = ">> starting the API" in output
    boot = "started but failed" if started else "did not start"
    cause = f": {reason[-1]}" if reason else ""
    logs = output.split(">> smoke FAILED. API logs:", 1)
    details = logs[1].strip() if len(logs) == 2 else output
    return Finding(
        Status.FAILED, f"API {boot}{cause} · {endpoints}", tail(details), "API logs (excerpt)"
    )


SCHEMATHESIS_VERDICT = re.compile(r"^=+ (?P<verdict>.+?) in [\d.]+s =+$", re.MULTILINE)
SCHEMATHESIS_FAILURE = re.compile(r"^\s*❌ (?P<check>[^:\n]+): (?P<count>\d+)$", re.MULTILINE)
SCHEMATHESIS_OPERATIONS = r"Operations:\s+\d+ selected / (\d+) total"
MAX_API_LOG_CHARS = 2000
# Must match API_LABEL in scripts/contract.sh
CONTRACT_LABEL = "contract"


def between(text: str, start: str, end: str) -> str:
    begin = text.find(start)
    if begin < 0:
        return ""
    finish = text.find(end, begin)
    return text[begin + len(start) : finish if finish >= 0 else None].strip("= \n")


def api_logs(output: str, label: str) -> str:
    parts = output.split(f">> {label} FAILED. API logs:", 1)
    return parts[1].strip() if len(parts) == 2 else ""


def schemathesis_scope(output: str) -> str:
    cases = first_int(r"(\d+) generated", output)
    operations = first_int(SCHEMATHESIS_OPERATIONS, output)
    seed = re.search(r"^Seed: (.+)$", output, re.MULTILINE)
    scope = f"{plural(cases, 'case', 'cases')} on {plural(operations, 'operation', 'operations')}"
    return f"{scope} · seed {seed[1]}" if seed else scope


def schemathesis_details(output: str) -> str:
    failures = tail(between(output, " FAILURES ", " SUMMARY "))
    logs = api_logs(output, CONTRACT_LABEL)
    if not logs:
        return failures
    return f"{failures}\n\n--- API logs ---\n{tail(logs, MAX_API_LOG_CHARS)}"


def analyze_schemathesis(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.passed:
        return Finding(Status.OK, schemathesis_scope(output))
    verdicts = SCHEMATHESIS_VERDICT.findall(output)
    if not verdicts:
        reasons = re.findall(rf"^>> {CONTRACT_LABEL}: (.+)$", output, re.MULTILINE)
        cause = f": {reasons[-1]}" if reasons else ""
        details = api_logs(output, CONTRACT_LABEL) or output
        return Finding(Status.FAILED, f"contract test did not run{cause}", tail(details))
    checks = "; ".join(
        f"{match['check']} ({match['count']})" for match in SCHEMATHESIS_FAILURE.finditer(output)
    )
    summary = f"{verdicts[-1]}: {checks}" if checks else verdicts[-1]
    return Finding(
        Status.FAILED,
        f"{summary} · {schemathesis_scope(output)}",
        schemathesis_details(output),
        "Failures, with a curl per failure",
    )


OASDIFF_COUNTS = re.compile(
    r"^(?P<total>\d+) changes?: (?P<errors>\d+) error, (?P<warnings>\d+) warning, \d+ info$",
    re.MULTILINE,
)
OASDIFF_ENTRY = re.compile(
    r"^(?P<level>error|warning|info)\t\[(?P<rule>[^\]]+)\][^\n]*\n\tin (?P<where>[^\n]+)\n"
    r"\t\t(?P<text>[^\n]+)",
    re.MULTILINE,
)


def oasdiff_listing(output: str) -> str:
    return "\n".join(
        f"{m['level']:7} {m['where']}: {m['text']} [{m['rule']}]"
        for m in OASDIFF_ENTRY.finditer(output)
    )


def analyze_oasdiff(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.passed and "No changes detected" in output:
        return Finding(Status.OK, "no API changes")
    counts = OASDIFF_COUNTS.search(output)
    errors = int(counts["errors"]) if counts else 0
    if counts is None or (errors == 0 and not fragment.passed):
        return Finding(Status.FAILED, "OpenAPI diff failed before comparing", tail(output))
    total, warnings = int(counts["total"]), int(counts["warnings"])
    listing = tail(oasdiff_listing(output))
    if errors:
        summary = f"{plural(errors, 'breaking change', 'breaking changes')} out of {total}"
        return Finding(Status.FAILED, summary, listing, "API changes")
    if warnings:
        summary = (
            f"{plural(warnings, 'possible breaking change', 'possible breaking changes')} "
            f"(warning) out of {total}"
        )
        return Finding(Status.WARNING, summary, listing, "API changes")
    summary = f"{plural(total, 'API change', 'API changes')}, none breaking"
    return Finding(Status.OK, summary, listing, "API changes")


@dataclass(frozen=True)
class Survivor:
    file: str
    function: str
    status: str
    name: str


@dataclass(frozen=True)
class MutationOutcome:
    skipped: bool
    score: float
    min_score: float
    killed: int
    total: int
    survivors: list[Survivor]

    @classmethod
    def parse(cls, output: str) -> MutationOutcome | None:
        line = next(
            (line for line in output.splitlines() if line.startswith(MUTATION_RESULT_PREFIX)), None
        )
        if line is None:
            return None
        data = json.loads(line.removeprefix(MUTATION_RESULT_PREFIX))
        return cls(
            skipped=bool(data["skipped"]),
            score=float(data["score"]),
            min_score=float(data["min_score"]),
            killed=int(data["killed"]),
            total=int(data["total"]),
            survivors=[Survivor(**item) for item in data["survivors"]],
        )


def survivors_table(survivors: list[Survivor]) -> str:
    rows = [
        "| File | Function | Status |",
        "| --- | --- | --- |",
        *(
            f"| `{s.file}` | `{s.function}` | {s.status} |"
            for s in survivors[:MAX_SURVIVORS_LISTED]
        ),
    ]
    hidden = len(survivors) - MAX_SURVIVORS_LISTED
    if hidden > 0:
        rows.append(f"\n... and {hidden} more. Run `make mutation-results` for the full list.")
    return "\n".join(rows)


def analyze_mutation(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    outcome = MutationOutcome.parse(output)
    if outcome is None:
        return Finding(Status.FAILED, "mutmut failed before producing a score", tail(output))
    if outcome.skipped:
        return Finding(Status.SKIPPED, "no domain file changed")
    summary = (
        f"{outcome.killed} of {plural(outcome.total, 'mutant', 'mutants')} killed "
        f"(threshold {outcome.min_score:.1f}%)"
    )
    metric = Metric("score", Decimal(f"{outcome.score:.1f}"), "%")
    status = Status.OK if outcome.score >= outcome.min_score else Status.FAILED
    details = survivors_table(outcome.survivors) if outcome.survivors else ""
    return Finding(status, summary, details, "Survivors", True, metric)


@dataclass(frozen=True)
class SuppressionChange:
    path: str
    kind: str
    baseline: int
    current: int
    lines: list[int]

    @property
    def is_increase(self) -> bool:
        return self.current > self.baseline


@dataclass(frozen=True)
class SuppressionOutcome:
    total: int
    totals: dict[str, int]
    changes: list[SuppressionChange]

    @property
    def increases(self) -> list[SuppressionChange]:
        return [change for change in self.changes if change.is_increase]

    @classmethod
    def parse(cls, output: str) -> SuppressionOutcome | None:
        line = next(
            (line for line in output.splitlines() if line.startswith(SUPPRESSIONS_RESULT_PREFIX)),
            None,
        )
        if line is None:
            return None
        data = json.loads(line.removeprefix(SUPPRESSIONS_RESULT_PREFIX))
        return cls(
            total=int(data["total"]),
            totals={str(kind): int(count) for kind, count in data["totals"].items()},
            changes=[SuppressionChange(**item) for item in data["changes"]],
        )


def suppression_changes_table(changes: list[SuppressionChange]) -> str:
    rows = [
        "| File | Kind | Baseline → current | Lines |",
        "| --- | --- | --- | --- |",
        *(
            f"| `{c.path}` | {c.kind} | {c.baseline} → {c.current} | "
            f"{', '.join(map(str, c.lines)) or '-'} |"
            for c in changes[:MAX_SUPPRESSION_CHANGES_LISTED]
        ),
    ]
    hidden = len(changes) - MAX_SUPPRESSION_CHANGES_LISTED
    if hidden > 0:
        rows.append(f"\n... and {hidden} more. Run `make suppressions` for the full list.")
    return "\n".join(rows)


def analyze_suppressions(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    outcome = SuppressionOutcome.parse(output)
    if outcome is None:
        return Finding(
            Status.FAILED, "suppression check failed before producing a result", tail(output)
        )
    metric = Metric("suppressions", Decimal(outcome.total))
    if outcome.increases:
        added = sum(c.current - c.baseline for c in outcome.increases)
        summary = f"{plural(added, 'new suppression', 'new suppressions')} above the baseline"
        details = suppression_changes_table(outcome.increases)
        return Finding(Status.FAILED, summary, details, "New suppressions", True, metric)
    if outcome.changes:
        removed = sum(c.baseline - c.current for c in outcome.changes)
        summary = (
            f"{plural(removed, 'suppression', 'suppressions')} removed but still counted in the "
            "baseline: run `make suppressions-update`"
        )
        details = suppression_changes_table(outcome.changes)
        return Finding(Status.FAILED, summary, details, "Stale baseline", True, metric)
    listing = "\n".join(f"{kind}: {count}" for kind, count in outcome.totals.items())
    return Finding(Status.OK, "baseline matched", listing, "By kind", metric=metric)


ANALYZERS: dict[Analysis, Callable[[Fragment], Finding]] = {
    Analysis.RUFF_CHECK: analyze_ruff_check,
    Analysis.RUFF_FORMAT: analyze_ruff_format,
    Analysis.MYPY: analyze_mypy,
    Analysis.BANDIT: analyze_bandit,
    Analysis.PIP_AUDIT: analyze_pip_audit,
    Analysis.DEPTRY: analyze_deptry,
    Analysis.VULTURE: analyze_vulture,
    Analysis.XENON: analyze_xenon,
    Analysis.PYTEST: analyze_pytest,
    Analysis.IMPORT_LINTER: analyze_import_linter,
    Analysis.SMOKE: analyze_smoke,
    Analysis.MUTATION: analyze_mutation,
    Analysis.SUPPRESSIONS: analyze_suppressions,
    Analysis.SCHEMATHESIS: analyze_schemathesis,
    Analysis.OASDIFF: analyze_oasdiff,
}


def missing_finding(job: str, job_results: dict[str, str]) -> Finding:
    result = job_results.get(job, "unknown")
    if result in ("cancelled", "skipped"):
        return Finding(Status.SKIPPED, f"job `{job}` {result}")
    return Finding(Status.FAILED, f"job `{job}` ended as `{result}` without producing a result")


def base_finding(analysis: Analysis, baseline: Baseline) -> Finding | None:
    fragment = baseline.fragments.get(analysis)
    if fragment is None:
        return None
    try:
        return ANALYZERS[analysis](fragment)
    except (ValueError, KeyError, TypeError) as error:
        print(f"ignoring the {baseline.name} fragment of {analysis}: {error}", file=sys.stderr)
        return None


def evaluate(
    section: Section,
    fragments: dict[Analysis, Fragment],
    job_results: dict[str, str],
    baseline: Baseline,
) -> SectionResult:
    results: list[AnalysisResult] = []
    for analysis in section.analyses:
        fragment = fragments.get(analysis)
        finding = (
            ANALYZERS[analysis](fragment) if fragment else missing_finding(section.job, job_results)
        )
        results.append(AnalysisResult(analysis, finding, base_finding(analysis, baseline)))
    status = worst([result.finding.status for result in results])
    return SectionResult(section, status, tuple(results))


def count(results: list[SectionResult], status: Status) -> int:
    return sum(result.status == status for result in results)


def failed_text(results: list[SectionResult], base_name: str) -> str:
    failed = [result for result in results if result.status == Status.FAILED]
    inherited = sum(result.is_inherited for result in failed)
    text = f"{Status.FAILED} {len(failed)} failed"
    if inherited == 0:
        return text
    if inherited < len(failed):
        return f"{text} ({inherited} inherited from `{base_name}`)"
    every = "all " if len(failed) > 1 else ""
    return f"{text}, {every}inherited from `{base_name}`"


def verdict(results: list[SectionResult], base_name: str) -> list[str]:
    failed, warnings = count(results, Status.FAILED), count(results, Status.WARNING)
    passed, skipped = count(results, Status.OK), count(results, Status.SKIPPED)
    parts = [failed_text(results, base_name)] if failed else []
    if warnings:
        parts.append(f"{Status.WARNING} {plural(warnings, 'warning', 'warnings')}")
    parts.append(f"{Status.OK} {passed} passed")
    if skipped:
        parts.append(f"{Status.SKIPPED} {skipped} skipped")
    alert = Alert.CAUTION if failed else Alert.WARNING if warnings else Alert.TIP
    return [f"> [!{alert}]", "> " + " · ".join(parts)]


def render_finding_details(finding: Finding) -> list[str]:
    if not finding.details:
        return []
    return ["", finding.details if finding.is_markdown else fence(finding.details)]


def render_problem(result: SectionResult, base_name: str) -> list[str]:
    lines = ["", f"### {result.status} {result.section.title}"]
    is_single = len(result.results) == 1
    for item in result.results:
        if item.finding.status not in ATTENTION_STATUSES:
            continue
        label = "" if is_single else f"**{item.analysis}**: "
        inherited = f" · inherited from `{base_name}`" if item.is_inherited else ""
        lines += ["", f"{label}{item.detail}{inherited}"]
        lines += render_finding_details(item.finding)
    lines += ["", f"**Reproduce**: `{result.section.reproduce}`"]
    return lines


def render_problems(results: list[SectionResult], base_name: str) -> list[str]:
    lines: list[str] = []
    for status in (Status.FAILED, Status.WARNING):
        for result in results:
            if result.status == status:
                lines += render_problem(result, base_name)
    return lines


def render_table(results: list[SectionResult], base_name: str) -> list[str]:
    lines = ["", "| Area | Check | Status | Detail |", "| --- | --- | :---: | --- |"]
    for group in Group:
        rows = [result for result in results if result.section.group == group]
        for index, result in enumerate(rows):
            area = f"**{group}**" if index == 0 else ""
            inherited = f" · inherited from `{base_name}`" if result.is_inherited else ""
            detail = cell(result.detail + inherited)
            lines.append(f"| {area} | {result.section.title} | {result.status} | {detail} |")
    return lines


def render_passed(results: list[SectionResult]) -> list[str]:
    passed = [result for result in results if result.status == Status.OK]
    blocks: list[str] = []
    for result in passed:
        for item in result.results:
            if not item.finding.details:
                continue
            title = item.finding.details_title
            blocks += ["", f"**{result.section.title}** · {title}"]
            blocks += render_finding_details(item.finding)
    if not blocks:
        return []
    summary = f"{len(passed)} passed"
    return ["", f"<details><summary>{summary}</summary>", *blocks, "", "</details>"]


def baseline_note(baseline: Baseline) -> str:
    if not baseline.is_available:
        return f"no `{baseline.name}` baseline: deltas are n/a"
    run = f"last `{baseline.name}` run"
    return (
        f"compared with the [{run}]({baseline.run_url})"
        if baseline.run_url
        else (f"compared with the {run}")
    )


def render(
    fragments: dict[Analysis, Fragment],
    job_results: dict[str, str],
    *,
    baseline: Baseline,
    footer: str = "",
) -> str:
    results = [evaluate(section, fragments, job_results, baseline) for section in SECTIONS]
    lines = [MARKER, "## Quality Report", "", *verdict(results, baseline.name)]
    lines += render_problems(results, baseline.name)
    lines += render_table(results, baseline.name)
    lines += render_passed(results)
    notes = " · ".join(part for part in (footer, baseline_note(baseline)) if part)
    lines += ["", "---", f"<sub>{notes}</sub>"]
    return "\n".join(lines) + "\n"


def load_fragments(directory: Path) -> dict[Analysis, Fragment]:
    fragments: dict[Analysis, Fragment] = {}
    for path in sorted(directory.glob("*.json")):
        try:
            fragment = Fragment.read(path)
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as error:
            print(f"ignoring invalid fragment {path}: {error}", file=sys.stderr)
            continue
        fragments[fragment.analysis] = fragment
    return fragments


def parse_job_results(needs_json: str) -> dict[str, str]:
    if not needs_json:
        return {}
    needs = json.loads(needs_json)
    return {job: str(data.get("result", "unknown")) for job, data in needs.items()}


def run_command(analysis: Analysis, command: list[str], directory: Path, advisory: bool) -> int:
    lines: list[str] = []
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
        )
    except OSError as error:
        message = f"could not run {command[0]}: {error}"
        print(message, file=sys.stderr)
        Fragment(analysis, 127, message, advisory).write(directory)
        return 127
    assert process.stdout is not None
    for line in process.stdout:
        sys.stdout.write(line)
        lines.append(line)
    exit_code = process.wait()
    Fragment(analysis, exit_code, "".join(lines), advisory).write(directory)
    return 0 if advisory else exit_code


def run_url(run_id: str) -> str:
    repository = os.environ.get("GITHUB_REPOSITORY")
    if not repository or not run_id:
        return ""
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    return f"{server}/{repository}/actions/runs/{run_id}"


def footer_from_environment(now: datetime) -> str:
    sha = os.environ.get("QUALITY_REPORT_SHA", os.environ.get("GITHUB_SHA", ""))[:7]
    url = run_url(os.environ.get("GITHUB_RUN_ID", ""))
    parts = [
        f"commit `{sha}`" if sha else "",
        now.astimezone(UTC).strftime(TIMESTAMP_FORMAT),
        f"[workflow run]({url})" if url else "",
    ]
    return " · ".join(part for part in parts if part)


def load_baseline(directory: Path | None, name: str) -> Baseline:
    fragments = load_fragments(directory) if directory else {}
    return Baseline(name, fragments, run_url(os.environ.get("QUALITY_REPORT_BASE_RUN_ID", "")))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run a command and store its fragment")
    run.add_argument("analysis", type=Analysis)
    run.add_argument("--dir", type=Path, default=DEFAULT_DIRECTORY)
    run.add_argument("--advisory", action="store_true")
    render_parser = commands.add_parser("render", help="build the Markdown report")
    render_parser.add_argument("--dir", type=Path, default=DEFAULT_DIRECTORY)
    render_parser.add_argument("--needs-json", default="")
    render_parser.add_argument("--output", type=Path)
    render_parser.add_argument(
        "--base-dir", type=Path, help="fragments of the last run on the base branch, if any"
    )
    render_parser.add_argument("--base-name", default=DEFAULT_BASE_NAME)
    return parser


def main() -> int:
    argv = sys.argv[1:]
    command: list[str] = []
    if "--" in argv:
        separator = argv.index("--")
        argv, command = argv[:separator], argv[separator + 1 :]
    args = build_parser().parse_args(argv)
    if args.command == "run":
        if not command:
            print("missing command after --", file=sys.stderr)
            return 2
        return run_command(args.analysis, command, args.dir, args.advisory)
    report = render(
        load_fragments(args.dir),
        parse_job_results(args.needs_json),
        baseline=load_baseline(args.base_dir, args.base_name or DEFAULT_BASE_NAME),
        footer=footer_from_environment(datetime.now(UTC)),
    )
    if args.output:
        args.output.write_text(report)
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
