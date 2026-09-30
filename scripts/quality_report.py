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
# Must match scripts/mutation.py, which prints this line followed by a JSON document
MUTATION_RESULT_PREFIX = "MUTATION_RESULT: "
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
class Finding:
    status: Status
    summary: str
    details: str = ""
    details_title: str = "Saída"


@dataclass(frozen=True)
class Section:
    title: str
    job: str
    analyses: tuple[Analysis, ...]


SECTIONS = [
    Section("Lint/format (ruff)", "lint", (Analysis.RUFF_CHECK, Analysis.RUFF_FORMAT)),
    Section("Tipos (mypy)", "types", (Analysis.MYPY,)),
    Section("Segurança (bandit + pip-audit)", "security", (Analysis.BANDIT, Analysis.PIP_AUDIT)),
    Section("Dead code (vulture)", "dead-code", (Analysis.VULTURE,)),
    Section("Complexidade (xenon)", "complexity", (Analysis.XENON,)),
    Section("Testes e cobertura (pytest)", "tests", (Analysis.PYTEST,)),
    Section("Arquitetura (import-linter)", "lint-imports", (Analysis.IMPORT_LINTER,)),
    Section("Smoke de boot (/health e /ready)", "smoke", (Analysis.SMOKE,)),
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
    if fragment.passed:
        return Finding(Status.OK, "Nenhum problema de lint")
    count = first_int(r"Found (\d+) error", output)
    summary = f"{plural(count, 'problema', 'problemas')} de lint" if count else "Lint falhou"
    return Finding(Status.FAILED, summary, tail(output))


def analyze_ruff_format(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.passed:
        return Finding(Status.OK, "Formatação conforme")
    count = len(re.findall(r"^Would reformat: ", output, re.MULTILINE))
    summary = (
        f"{plural(count, 'arquivo fora', 'arquivos fora')} do formato (`make format-code`)"
        if count
        else "Verificação de formato falhou"
    )
    return Finding(Status.FAILED, summary, tail(output))


def analyze_mypy(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.passed:
        files = first_int(r"no issues found in (\d+) source file", output)
        return Finding(Status.OK, f"Sem erros de tipo ({plural(files, 'arquivo', 'arquivos')})")
    errors = first_int(r"Found (\d+) error", output)
    summary = f"{plural(errors, 'erro', 'erros')} de tipo" if errors else "mypy falhou"
    return Finding(Status.FAILED, summary, tail(output))


def analyze_bandit(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.passed:
        return Finding(Status.OK, "Nenhum problema de segurança")
    issues = len(re.findall(r">> Issue:", output))
    summary = plural(issues, "problema", "problemas") if issues else "bandit falhou"
    return Finding(Status.FAILED, summary, tail(output))


def analyze_pip_audit(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.passed:
        return Finding(Status.OK, "Nenhuma vulnerabilidade conhecida")
    count = first_int(r"Found (\d+) known vulnerabilit", output)
    summary = (
        f"{plural(count, 'vulnerabilidade', 'vulnerabilidades')}" if count else "pip-audit falhou"
    )
    return Finding(Status.FAILED, summary, tail(output))


def analyze_vulture(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.passed and not output:
        return Finding(Status.OK, "Nenhum dead code detectado")
    lines = [line for line in output.splitlines() if line.strip()]
    status = Status.WARNING if fragment.advisory else Status.FAILED
    return Finding(status, f"{plural(len(lines), 'item', 'itens')} de dead code", tail(output))


def analyze_xenon(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    if fragment.passed:
        return Finding(Status.OK, "Complexidade dentro do limiar")
    blocks = len(re.findall(r"^ERROR:xenon:", output, re.MULTILINE))
    summary = (
        f"{plural(blocks, 'violação', 'violações')} de complexidade"
        if blocks
        else "Complexidade acima do limiar"
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
    coverage_text = f"{coverage[1]}%" if coverage else "n/d"
    if required:
        coverage_text += f" (mínimo {required[1]}%)"
    counts = f"{passed} passaram, {plural(failed, 'falhou', 'falharam')}, {total} no total"
    if failed or not summary_line:
        summary = counts if summary_line else "pytest falhou antes de concluir"
        return Finding(Status.FAILED, f"{summary} · cobertura {coverage_text}", tail(output))
    if not fragment.passed:
        summary = f"{counts} · cobertura abaixo do mínimo: {coverage_text}"
        return Finding(Status.FAILED, summary, coverage_table(output) or tail(output), "Cobertura")
    return Finding(
        Status.OK, f"{counts} · cobertura {coverage_text}", coverage_table(output), "Cobertura"
    )


CONTRACT_LINE = re.compile(r"^(?P<name>.+?)\s*(?P<state>KEPT|BROKEN)$", re.MULTILINE)


def analyze_import_linter(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    contracts = [(m["name"].strip(), m["state"]) for m in CONTRACT_LINE.finditer(output)]
    kept = first_int(r"(\d+) kept", output)
    broken = first_int(r"(\d+) broken", output)
    if fragment.passed:
        listing = "\n".join(f"{state:6} {name}" for name, state in contracts)
        return Finding(
            Status.OK,
            f"{plural(kept, 'contrato mantido', 'contratos mantidos')}",
            listing,
            "Contratos",
        )
    broken_names = [name for name, state in contracts if state == "BROKEN"]
    marker = output.find("Broken contracts")
    violation = output[marker:] if marker >= 0 else output
    if not contracts:
        return Finding(
            Status.FAILED, "import-linter falhou antes de avaliar os contratos", tail(output)
        )
    summary = f"{kept} mantidos, {plural(broken, 'quebrado', 'quebrados')}: " + "; ".join(
        f"**{name}**" for name in broken_names
    )
    return Finding(
        Status.FAILED, summary, tail(violation), "Contrato quebrado e imports que violaram"
    )


def analyze_smoke(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    health = ">> GET /health ->" in output
    ready = ">> GET /ready ->" in output
    seconds = re.search(r">> API healthy after ([\d.]+)s", output)
    endpoints = f"/health {'✅' if health else '❌'} · /ready {'✅' if ready else '❌'}"
    if fragment.passed:
        boot = f"subiu e ficou pronto em {seconds[1]}s" if seconds else "subiu"
        return Finding(Status.OK, f"API {boot} · {endpoints}")
    reason = re.findall(r"^>> smoke: (.+)$", output, re.MULTILINE)
    started = ">> starting the API" in output
    boot = "subiu mas falhou" if started else "não chegou a subir"
    cause = f": {reason[-1]}" if reason else ""
    logs = output.split(">> smoke FAILED. API logs:", 1)
    details = logs[1].strip() if len(logs) == 2 else output
    return Finding(
        Status.FAILED, f"API {boot}{cause} · {endpoints}", tail(details), "Logs da API (resumo)"
    )


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
        "| Arquivo | Função | Status |",
        "| --- | --- | --- |",
        *(
            f"| `{s.file}` | `{s.function}` | {s.status} |"
            for s in survivors[:MAX_SURVIVORS_LISTED]
        ),
    ]
    hidden = len(survivors) - MAX_SURVIVORS_LISTED
    if hidden > 0:
        rows.append(f"\n... e mais {hidden}. Rode `make mutation-results` para a lista completa.")
    return "\n".join(rows)


def analyze_mutation(fragment: Fragment) -> Finding:
    output = clean(fragment.output)
    outcome = MutationOutcome.parse(output)
    if outcome is None:
        return Finding(Status.FAILED, "mutmut falhou antes de produzir um score", tail(output))
    if outcome.skipped:
        return Finding(Status.SKIPPED, "Nenhum arquivo de domínio alterado, nada a mutar")
    survivors = len(outcome.survivors)
    summary = (
        f"score {outcome.score:.1f}% (limiar {outcome.min_score:.1f}%) · "
        f"{outcome.killed} mortos, {survivors} sobreviventes de {outcome.total}"
    )
    status = Status.OK if outcome.score >= outcome.min_score else Status.FAILED
    details = survivors_table(outcome.survivors) if outcome.survivors else ""
    return Finding(status, summary, details, "Sobreviventes")


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
}


def missing_finding(job: str, job_results: dict[str, str]) -> Finding:
    result = job_results.get(job, "desconhecido")
    if result in ("cancelled", "skipped"):
        return Finding(Status.SKIPPED, f"Job `{job}` {result}: análise não executada")
    return Finding(Status.FAILED, f"Job `{job}` terminou como `{result}` sem produzir resultado")


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
    multiple = len(result.findings) > 1
    for analysis, finding in result.findings:
        label = f"- {finding.status} **{analysis}**: " if multiple else ""
        lines.append(f"{label}{finding.summary}")
        lines += render_details(finding)
    return lines


def verdict(results: list[SectionResult]) -> str:
    failed = sum(r.status == Status.FAILED for r in results)
    warnings = sum(r.status == Status.WARNING for r in results)
    skipped = sum(r.status == Status.SKIPPED for r in results)
    extra = f" ({plural(skipped, 'análise não executada', 'análises não executadas')})"
    if failed:
        return f"❌ **Reprovado**: {plural(failed, 'análise falhou', 'análises falharam')}"
    if warnings:
        return f"⚠️ **Aprovado com avisos**: {plural(warnings, 'análise', 'análises')} com aviso"
    return "✅ **Tudo certo**" + (extra if skipped else "")


def render(
    fragments: dict[Analysis, Fragment],
    job_results: dict[str, str],
    footer: str = "",
) -> str:
    results = [evaluate(section, fragments, job_results) for section in SECTIONS]
    lines = [MARKER, "## 🔍 Quality Report", "", verdict(results), ""]
    lines += ["| Análise | Status |", "| --- | --- |"]
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
    return {job: str(data.get("result", "desconhecido")) for job, data in needs.items()}


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


def footer_from_environment() -> str:
    repository = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if not repository or not run_id:
        return ""
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    sha = os.environ.get("QUALITY_REPORT_SHA", os.environ.get("GITHUB_SHA", ""))[:7]
    commit = f"commit `{sha}` · " if sha else ""
    return f"{commit}[execução do CI]({server}/{repository}/actions/runs/{run_id})"


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
        return run_command(args.analysis, command, args.dir, args.advisory)
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
