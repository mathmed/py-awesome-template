import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

MARKER = "<!-- quality-report -->"
DEFAULT_DIRECTORY = Path("quality-fragments")
MAX_DETAILS_CHARS = 6000
MAX_SURVIVORS_LISTED = 50
MUTATION_RESULT_PREFIX = "MUTATION_RESULT: "
SUPPRESSIONS_RESULT_PREFIX = "SUPPRESSIONS_RESULT: "
MAX_SUPPRESSION_CHANGES_LISTED = 50
CONVENTIONS_RESULT_PREFIX = "CONVENTIONS_RESULT: "
MAX_CONVENTION_VIOLATIONS_LISTED = 50
UV_NOISE = re.compile(r"^warning: `VIRTUAL_ENV=.*$", re.MULTILINE)


class Analysis(StrEnum):
    RUFF_CHECK = "ruff-check"
    RUFF_FORMAT = "ruff-format"
    MYPY = "mypy"
    BANDIT = "bandit"
    PIP_AUDIT = "pip-audit"
    VULTURE = "vulture"
    XENON = "xenon"
    PYTEST = "pytest"
    IMPORT_LINTER = "import-linter"
    SMOKE = "smoke"
    MUTATION = "mutation"
    SUPPRESSIONS = "suppressions"
    CONVENTIONS = "conventions"
    SCHEMATHESIS = "schemathesis"
    OASDIFF = "oasdiff"


class Status(StrEnum):
    OK = "✅"
    WARNING = "⚠️"
    FAILED = "❌"
    SKIPPED = "⏭️"


SEVERITY_ORDER = [Status.OK, Status.SKIPPED, Status.WARNING, Status.FAILED]


def worst(statuses: list[Status]) -> Status:
    return max(statuses, key=SEVERITY_ORDER.index, default=Status.OK)


@dataclass(frozen=True)
class Fragment:
    analysis: Analysis
    exit_code: int
    output: str
    is_advisory: bool = False

    @property
    def has_passed(self) -> bool:
        return self.exit_code == 0

    def write(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.analysis}.json"
        payload = {
            "analysis": self.analysis.value,
            "exit_code": self.exit_code,
            "output": self.output,
            "advisory": self.is_advisory,
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
            is_advisory=bool(data.get("advisory", False)),
        )


@dataclass(frozen=True)
class Finding:
    status: Status
    summary: str
    details: str = ""
    details_title: str = "Output"


@dataclass(frozen=True)
class Section:
    title: str
    job: str
    analyses: tuple[Analysis, ...]


SECTIONS = [
    Section("Lint/format (ruff)", "lint", (Analysis.RUFF_CHECK, Analysis.RUFF_FORMAT)),
    Section("Types (mypy)", "types", (Analysis.MYPY,)),
    Section("Security (bandit + pip-audit)", "security", (Analysis.BANDIT, Analysis.PIP_AUDIT)),
    Section("Dead code (vulture)", "dead-code", (Analysis.VULTURE,)),
    Section("Complexity (xenon)", "complexity", (Analysis.XENON,)),
    Section("Suppressions (ratchet)", "suppressions", (Analysis.SUPPRESSIONS,)),
    Section("Code conventions", "conventions", (Analysis.CONVENTIONS,)),
    Section("Tests and coverage (pytest)", "tests", (Analysis.PYTEST,)),
    Section("Architecture (import-linter)", "lint-imports", (Analysis.IMPORT_LINTER,)),
    Section("Boot smoke (/health and /ready)", "smoke", (Analysis.SMOKE,)),
    Section("API contract (schemathesis)", "contract", (Analysis.SCHEMATHESIS,)),
    Section("Breaking API changes (oasdiff)", "openapi-diff", (Analysis.OASDIFF,)),
    Section("Mutation testing (mutmut)", "mutation", (Analysis.MUTATION,)),
]


@dataclass(frozen=True)
class SectionResult:
    title: str
    status: Status
    findings: list[tuple[Analysis, Finding]]


def clean(output: str) -> str:
    return UV_NOISE.sub("", output).strip()


def tail(text: str, limit: int = MAX_DETAILS_CHARS) -> str:
    if len(text) <= limit:
        return text
    return "[...truncado...]\n" + text[-limit:]


def first_int(pattern: str, text: str, default: int = 0) -> int:
    match = re.search(pattern, text)
    return int(match[1]) if match else default


def plural(count: int, singular: str, plural_form: str) -> str:
    return f"{count} {singular if count == 1 else plural_form}"


def analyze_ruff_check(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.has_passed:
        return Finding(Status.OK, "No lint issues")
    count = first_int(r"Found (\d+) error", output)
    summary = f"{plural(count, 'lint issue', 'lint issues')}" if count else "Lint failed"
    return Finding(Status.FAILED, summary, tail(output))


def analyze_ruff_format(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.has_passed:
        return Finding(Status.OK, "Formatting is correct")
    count = len(re.findall(r"^Would reformat: ", output, re.MULTILINE))
    summary = (
        f"{plural(count, 'file', 'files')} need formatting (`make format-code`)"
        if count
        else "Format check failed"
    )
    return Finding(Status.FAILED, summary, tail(output))


def analyze_mypy(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.has_passed:
        files = first_int(r"no issues found in (\d+) source file", output)
        return Finding(Status.OK, f"No type errors ({plural(files, 'file', 'files')})")
    errors = first_int(r"Found (\d+) error", output)
    summary = f"{plural(errors, 'type error', 'type errors')}" if errors else "mypy failed"
    return Finding(Status.FAILED, summary, tail(output))


def analyze_bandit(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.has_passed:
        return Finding(Status.OK, "No security issues")
    issues = len(re.findall(r">> Issue:", output))
    summary = plural(issues, "issue", "issues") if issues else "bandit failed"
    return Finding(Status.FAILED, summary, tail(output))


def analyze_pip_audit(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.has_passed:
        return Finding(Status.OK, "No known vulnerabilities")
    count = first_int(r"Found (\d+) known vulnerabilit", output)
    summary = (
        f"{plural(count, 'vulnerability', 'vulnerabilities')}" if count else "pip-audit failed"
    )
    return Finding(Status.FAILED, summary, tail(output))


def analyze_vulture(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.has_passed and not output:
        return Finding(Status.OK, "No dead code detected")
    lines = [line for line in output.splitlines() if line.strip()]
    status = Status.WARNING if fragment.is_advisory else Status.FAILED
    return Finding(
        status, f"{plural(len(lines), 'dead code item', 'dead code items')}", tail(output)
    )


def analyze_xenon(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.has_passed:
        return Finding(Status.OK, "Complexity within the threshold")
    blocks = len(re.findall(r"^ERROR:xenon:", output, re.MULTILINE))
    summary = (
        f"{plural(blocks, 'complexity violation', 'complexity violations')}"
        if blocks
        else "Complexity above the threshold"
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


def analyze_pytest(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    summary_line = next(
        (
            line
            for line in reversed(output.splitlines())
            if re.search(r" in [\d.]+s", line) and re.search(r"\d+ (passed|failed|error)", line)
        ),
        "",
    )
    passed = first_int(r"(\d+) passed", summary_line)
    failed = first_int(r"(\d+) failed", summary_line) + first_int(r"(\d+) errors?", summary_line)
    total = passed + failed + first_int(r"(\d+) skipped", summary_line)
    coverage = re.search(r"Total coverage: ([\d.]+)%", output)
    required = re.search(r"Required test coverage of ([\d.]+)%", output)
    coverage_text = f"{coverage[1]}%" if coverage else "n/a"
    if required:
        coverage_text += f" (minimum {required[1]}%)"
    counts = f"{passed} passed, {failed} failed, {total} total"
    if failed or not summary_line:
        summary = counts if summary_line else "pytest failed before finishing"
        return Finding(Status.FAILED, f"{summary} · coverage {coverage_text}", tail(output))
    if not fragment.has_passed:
        summary = f"{counts} · coverage below the minimum: {coverage_text}"
        return Finding(Status.FAILED, summary, coverage_table(output) or tail(output), "Coverage")
    return Finding(
        Status.OK, f"{counts} · coverage {coverage_text}", coverage_table(output), "Coverage"
    )


CONTRACT_LINE = re.compile(r"^(?P<name>.+?)\s*(?P<state>KEPT|BROKEN)$", re.MULTILINE)


def analyze_import_linter(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    contracts = [(m["name"].strip(), m["state"]) for m in CONTRACT_LINE.finditer(output)]
    kept = first_int(r"(\d+) kept", output)
    broken = first_int(r"(\d+) broken", output)
    if fragment.has_passed:
        listing = "\n".join(f"{state:6} {name}" for name, state in contracts)
        return Finding(
            Status.OK,
            f"{plural(kept, 'contract kept', 'contracts kept')}",
            listing,
            "Contracts",
        )
    broken_names = [name for name, state in contracts if state == "BROKEN"]
    marker = output.find("Broken contracts")
    violation = output[marker:] if marker >= 0 else output
    if not contracts:
        return Finding(
            Status.FAILED, "import-linter failed before evaluating the contracts", tail(output)
        )
    summary = f"{kept} kept, {broken} broken: " + "; ".join(f"**{name}**" for name in broken_names)
    return Finding(Status.FAILED, summary, tail(violation), "Broken contract and violating imports")


def analyze_smoke(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    has_health = ">> GET /health ->" in output
    has_ready = ">> GET /ready ->" in output
    seconds = re.search(r">> API healthy after ([\d.]+)s", output)
    endpoints = f"/health {'✅' if has_health else '❌'} · /ready {'✅' if has_ready else '❌'}"
    if fragment.has_passed:
        boot = f"started and became healthy in {seconds[1]}s" if seconds else "started"
        return Finding(Status.OK, f"API {boot} · {endpoints}")
    reason = re.findall(r"^>> smoke: (.+)$", output, re.MULTILINE)
    has_started = ">> starting the API" in output
    boot = "started but failed" if has_started else "did not start"
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
    scope = (
        f"{plural(cases, 'test case', 'test cases')} on "
        f"{plural(operations, 'operation', 'operations')}"
    )
    return f"{scope} · seed {seed[1]}" if seed else scope


def schemathesis_details(output: str) -> str:
    failures = tail(between(output, " FAILURES ", " SUMMARY "))
    logs = api_logs(output, CONTRACT_LABEL)
    if not logs:
        return failures
    return f"{failures}\n\n--- API logs ---\n{tail(logs, MAX_API_LOG_CHARS)}"


def analyze_schemathesis(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.has_passed:
        return Finding(Status.OK, f"No contract violations · {schemathesis_scope(output)}")
    verdicts = SCHEMATHESIS_VERDICT.findall(output)
    if not verdicts:
        reasons = re.findall(rf"^>> {CONTRACT_LABEL}: (.+)$", output, re.MULTILINE)
        cause = f": {reasons[-1]}" if reasons else ""
        details = api_logs(output, CONTRACT_LABEL) or output
        return Finding(Status.FAILED, f"Contract test did not run{cause}", tail(details), "Output")
    checks = "; ".join(
        f"{match['check']} ({match['count']})" for match in SCHEMATHESIS_FAILURE.finditer(output)
    )
    summary = f"{verdicts[-1]}: {checks}" if checks else verdicts[-1]
    return Finding(
        Status.FAILED,
        f"{summary} · {schemathesis_scope(output)}",
        schemathesis_details(output),
        "Failures (reproduce with `make contract`)",
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
    if fragment.has_passed and "No changes detected" in output:
        return Finding(Status.OK, "No API changes")
    counts = OASDIFF_COUNTS.search(output)
    errors = int(counts["errors"]) if counts else 0
    if counts is None or (errors == 0 and not fragment.has_passed):
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
    is_skipped: bool
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
            is_skipped=bool(data["skipped"]),
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
    if outcome.is_skipped:
        return Finding(Status.SKIPPED, "No domain file changed, nothing to mutate")
    survivors = len(outcome.survivors)
    summary = (
        f"score {outcome.score:.1f}% (threshold {outcome.min_score:.1f}%) · "
        f"{outcome.killed} killed, {survivors} survived out of {outcome.total}"
    )
    status = Status.OK if outcome.score >= outcome.min_score else Status.FAILED
    details = survivors_table(outcome.survivors) if outcome.survivors else ""
    return Finding(status, summary, details, "Survivors")


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
    if outcome.increases:
        added = sum(c.current - c.baseline for c in outcome.increases)
        summary = f"{plural(added, 'new suppression', 'new suppressions')} above the baseline"
        details = suppression_changes_table(outcome.increases)
        return Finding(Status.FAILED, summary, details, "New suppressions")
    if outcome.changes:
        removed = sum(c.baseline - c.current for c in outcome.changes)
        summary = (
            f"{plural(removed, 'suppression', 'suppressions')} removed but still counted in the "
            "baseline: run `make suppressions-update`"
        )
        return Finding(
            Status.FAILED, summary, suppression_changes_table(outcome.changes), "Stale baseline"
        )
    listing = "\n".join(f"{kind}: {count}" for kind, count in outcome.totals.items())
    summary = f"{plural(outcome.total, 'suppression', 'suppressions')}, matching the baseline"
    return Finding(Status.OK, summary, listing, "By kind")


@dataclass(frozen=True)
class ConventionViolation:
    path: str
    line: int
    kind: str
    count: int


@dataclass(frozen=True)
class ConventionOutcome:
    violations: list[ConventionViolation]

    @classmethod
    def parse(cls, output: str) -> ConventionOutcome | None:
        line = next(
            (line for line in output.splitlines() if line.startswith(CONVENTIONS_RESULT_PREFIX)),
            None,
        )
        if line is None:
            return None
        data = json.loads(line.removeprefix(CONVENTIONS_RESULT_PREFIX))
        return cls(violations=[ConventionViolation(**item) for item in data["violations"]])


def convention_violations_table(violations: list[ConventionViolation]) -> str:
    rows = [
        "| File | Line | Kind |",
        "| --- | --- | --- |",
        *(
            f"| `{v.path}` | {v.line} | {v.kind} |"
            for v in violations[:MAX_CONVENTION_VIOLATIONS_LISTED]
        ),
    ]
    hidden = len(violations) - MAX_CONVENTION_VIOLATIONS_LISTED
    if hidden > 0:
        rows.append(f"\n... and {hidden} more. Run `make conventions` for the full list.")
    return "\n".join(rows)


def analyze_conventions(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    outcome = ConventionOutcome.parse(output)
    if outcome is None:
        return Finding(
            Status.FAILED, "convention check failed before producing a result", tail(output)
        )
    if outcome.violations:
        count = plural(len(outcome.violations), "convention violation", "convention violations")
        details = convention_violations_table(outcome.violations)
        return Finding(Status.FAILED, count, details, "Violations")
    return Finding(Status.OK, "No convention violations")


ANALYZERS: dict[Analysis, Callable[[Fragment], Finding]] = {
    Analysis.RUFF_CHECK: analyze_ruff_check,
    Analysis.RUFF_FORMAT: analyze_ruff_format,
    Analysis.MYPY: analyze_mypy,
    Analysis.BANDIT: analyze_bandit,
    Analysis.PIP_AUDIT: analyze_pip_audit,
    Analysis.VULTURE: analyze_vulture,
    Analysis.XENON: analyze_xenon,
    Analysis.PYTEST: analyze_pytest,
    Analysis.IMPORT_LINTER: analyze_import_linter,
    Analysis.SMOKE: analyze_smoke,
    Analysis.MUTATION: analyze_mutation,
    Analysis.SUPPRESSIONS: analyze_suppressions,
    Analysis.CONVENTIONS: analyze_conventions,
    Analysis.SCHEMATHESIS: analyze_schemathesis,
    Analysis.OASDIFF: analyze_oasdiff,
}


def missing_finding(job: str, job_results: dict[str, str]) -> Finding:
    result = job_results.get(job, "unknown")
    if result in ("cancelled", "skipped"):
        return Finding(Status.SKIPPED, f"Job `{job}` {result}: analysis not run")
    return Finding(Status.FAILED, f"Job `{job}` ended as `{result}` without producing a result")


def evaluate(
    section: Section, fragments: dict[Analysis, Fragment], job_results: dict[str, str]
) -> SectionResult:
    findings: list[tuple[Analysis, Finding]] = []
    for analysis in section.analyses:
        fragment = fragments.get(analysis)
        finding = (
            ANALYZERS[analysis](fragment) if fragment else missing_finding(section.job, job_results)
        )
        findings.append((analysis, finding))
    status = worst([finding.status for _, finding in findings])
    return SectionResult(section.title, status, findings)


def fence(text: str) -> str:
    return "```text\n" + text.replace("```", "'''") + "\n```"


def render_details(finding: Finding) -> list[str]:
    if not finding.details:
        return []
    return [
        "",
        f"<details><summary>{finding.details_title}</summary>",
        "",
        fence(finding.details),
        "",
        "</details>",
    ]


def render_section(result: SectionResult) -> list[str]:
    lines = ["", f"### {result.status} {result.title}", ""]
    has_many = len(result.findings) > 1
    for analysis, finding in result.findings:
        label = f"- {finding.status} **{analysis}**: " if has_many else ""
        lines.append(f"{label}{finding.summary}")
        lines += render_details(finding)
    return lines


def verdict(results: list[SectionResult]) -> str:
    failed = sum(r.status == Status.FAILED for r in results)
    warnings = sum(r.status == Status.WARNING for r in results)
    skipped = sum(r.status == Status.SKIPPED for r in results)
    extra = f" ({plural(skipped, 'analysis not run', 'analyses not run')})"
    if failed:
        return f"❌ **Failed**: {plural(failed, 'analysis failed', 'analyses failed')}"
    if warnings:
        return (
            f"⚠️ **Passed with warnings**: {plural(warnings, 'analysis', 'analyses')} with warnings"
        )
    return "✅ **All good**" + (extra if skipped else "")


def render(
    fragments: dict[Analysis, Fragment],
    job_results: dict[str, str],
    footer: str = "",
) -> str:
    results = [evaluate(section, fragments, job_results) for section in SECTIONS]
    lines = [MARKER, "## 🔍 Quality Report", "", verdict(results), ""]
    lines += ["| Analysis | Status |", "| --- | --- |"]
    lines += [f"| {r.title} | {r.status} |" for r in results]
    for result in results:
        lines += render_section(result)
    if footer:
        lines += ["", "---", footer]
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


def run_command(
    analysis: Analysis, command: list[str], directory: Path, *, is_advisory: bool
) -> int:
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
        Fragment(analysis, 127, message, is_advisory).write(directory)
        return 127
    assert process.stdout is not None
    for line in process.stdout:
        sys.stdout.write(line)
        lines.append(line)
    exit_code = process.wait()
    Fragment(analysis, exit_code, "".join(lines), is_advisory).write(directory)
    return 0 if is_advisory else exit_code


def footer_from_environment() -> str:
    repository = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if not repository or not run_id:
        return ""
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    sha = os.environ.get("QUALITY_REPORT_SHA", os.environ.get("GITHUB_SHA", ""))[:7]
    commit = f"commit `{sha}` · " if sha else ""
    return f"{commit}[CI run]({server}/{repository}/actions/runs/{run_id})"


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
        return run_command(args.analysis, command, args.dir, is_advisory=args.advisory)
    report = render(
        load_fragments(args.dir), parse_job_results(args.needs_json), footer_from_environment()
    )
    if args.output:
        args.output.write_text(report)
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
