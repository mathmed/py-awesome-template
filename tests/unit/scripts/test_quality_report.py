import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from scripts import quality_report, suppressions
from scripts.quality_report import (
    Analysis,
    Baseline,
    Fragment,
    Metric,
    Status,
    analyze_bandit,
    analyze_deptry,
    analyze_import_linter,
    analyze_mutation,
    analyze_oasdiff,
    analyze_pip_audit,
    analyze_pytest,
    analyze_schemathesis,
    analyze_smoke,
    analyze_suppressions,
    analyze_vulture,
    analyze_xenon,
    render,
)

PYTEST_OK = """tests/unit/test_a.py ....                                    [100%]

Name                 Stmts   Miss  Cover
----------------------------------------
app/a.py                10      0   100%
----------------------------------------
TOTAL                   10      0   100%
Coverage XML written to file coverage.xml
Required test coverage of 80.0% reached. Total coverage: 100.00%
============================== 34 passed in 4.18s ==============================
"""
PYTEST_LOW_COVERAGE = """Name    Stmts   Miss  Cover
TOTAL      10      5    50%
FAIL Required test coverage of 80.0% not reached. Total coverage: 50.00%
============================== 34 passed in 4.18s ==============================
"""
PYTEST_FAILED = """FAILED tests/unit/test_a.py::test_should_x - assert 1 == 2
ERROR tests/unit/test_b.py::test_should_y
========================= 1 failed, 33 passed in 4.18s =========================
"""
IMPORT_LINTER_OK = """Application layers KEPT
Domain does not depend on outer layers KEPT

Contracts: 2 kept, 0 broken.
"""
IMPORT_LINTER_BROKEN = """Application layers KEPT
Domain does not depend on outer layers BROKEN

Contracts: 1 kept, 1 broken.

----------------
Broken contracts
----------------

Domain does not depend on outer layers
--------------------------------------

app.domain is not allowed to import app.infra:

-   app.domain.usecases.x -> app.infra.db (l.3)
"""
SMOKE_OK = """>> starting the API on http://127.0.0.1:18000 (ENV=production)
>> API healthy after 1.234s
>> GET /health -> {"status":"ok"}
>> GET /ready -> {"status":"ready"}
>> smoke OK
"""
SMOKE_FAILED = """>> starting the API on http://127.0.0.1:18000 (ENV=production)
>> smoke: the API did not become healthy within 30s
>> smoke FAILED. API logs:
Traceback: boom
"""

SCHEMATHESIS_OK = """>> API healthy after 0.545s
>> running schemathesis against http://127.0.0.1:18000/openapi.json (seed 1, max 50 examples)
     Operations:       3 selected / 3 total
=================================== SUMMARY ====================================
Test cases:
  54 generated, 54 passed

Seed: 1

=========================== No issues found in 0.46s ===========================
>> contract OK
"""
SCHEMATHESIS_FAILED = """     Operations:       3 selected / 3 total
=================================== FAILURES ===================================
_________________________________ GET /example _________________________________
1. Test Case ID: cidoQT

- Server error

    curl -X GET 'http://127.0.0.1:18000/example?field1=example'

=================================== SUMMARY ====================================

Test Phases:
  ❌ Coverage

Failures:
  ❌ Server error: 1
  ❌ Undocumented HTTP status code: 1

Test cases:
  29 generated, 1 found 2 unique failures

Seed: 1

============================= 2 failures in 0.25s ==============================
>> contract: schemathesis failed: contract violations or invalid options, see its output above
>> contract FAILED. API logs:
RuntimeError: boom
"""
SCHEMATHESIS_NOT_STARTED = """>> starting the API on http://127.0.0.1:18000 (ENV=production)
>> contract: the API process exited before becoming healthy
>> contract FAILED. API logs:
ValidationError: env
"""

PIP_AUDIT_FOUND = """Found 3 known vulnerabilities in 2 packages
Name       Version ID              Fix Versions
---------- ------- --------------- ------------
filelock   4.0.4   CVE-2026-112940 4.2.1
filelock   4.0.4   CVE-2026-112936 4.0.9
msgpack    1.2.2   CVE-2026-114613
"""

OASDIFF_NO_CHANGES = """Comparing the OpenAPI schema of HEAD with origin/main (merge base 6a0421faff05)
No changes detected
"""
OASDIFF_BREAKING = """Comparing the OpenAPI schema of HEAD with origin/main (merge base 6a0421faff05)
3 changes: 1 error, 1 warning, 1 info
error\t[request-parameter-became-required] at head.openapi.json
\tin API GET /example
\t\tthe `query` request parameter `field1` became required

warning\t[response-property-became-optional] at head.openapi.json
\tin API GET /ready
\t\tthe response property `status` became optional

info\t[endpoint-added] at head.openapi.json
\tin API GET /items
\t\tendpoint added
"""
OASDIFF_INFO_ONLY = """1 change: 0 error, 0 warning, 1 info
info\t[endpoint-added] at head.openapi.json
\tin API GET /items
\t\tendpoint added
"""


def mutation_output(score: float, survivors: list[dict[str, str]], skipped: bool = False) -> str:
    payload = {
        "skipped": skipped,
        "score": score,
        "min_score": 90.0,
        "killed": 9,
        "total": 10,
        "survivors": survivors,
    }
    return "noise\n" + quality_report.MUTATION_RESULT_PREFIX + json.dumps(payload) + "\n"


def suppressions_output(
    occurrences: tuple[suppressions.Occurrence, ...],
    baseline: Counter[tuple[str, suppressions.Kind]],
) -> str:
    return "Suppressions: ...\n" + suppressions.Comparison(occurrences, baseline).to_result_line()


NOSEC_IN_HANDLER = suppressions.Occurrence("app/h.py", 7, suppressions.Kind.NOSEC)
SUPPRESSIONS_OK = suppressions_output(
    (NOSEC_IN_HANDLER,), Counter({("app/h.py", suppressions.Kind.NOSEC): 1})
)


def fragment(analysis: Analysis, output: str = "", exit_code: int = 0) -> Fragment:
    return Fragment(analysis, exit_code, output)


def all_ok_fragments() -> dict[Analysis, Fragment]:
    outputs = {
        Analysis.PYTEST: PYTEST_OK,
        Analysis.IMPORT_LINTER: IMPORT_LINTER_OK,
        Analysis.SMOKE: SMOKE_OK,
        Analysis.MUTATION: mutation_output(100.0, []),
        Analysis.SUPPRESSIONS: SUPPRESSIONS_OK,
        Analysis.SCHEMATHESIS: SCHEMATHESIS_OK,
        Analysis.OASDIFF: OASDIFF_NO_CHANGES,
    }
    return {analysis: fragment(analysis, outputs.get(analysis, "")) for analysis in Analysis}


NO_BASELINE = Baseline("main", {})
NOW = datetime(2026, 11, 13, 14, 5, tzinfo=UTC)


def failing_pip_audit() -> Fragment:
    return fragment(Analysis.PIP_AUDIT, PIP_AUDIT_FOUND, 1)


def pytest_with_coverage(coverage: str) -> str:
    return PYTEST_OK.replace("Total coverage: 100.00%", f"Total coverage: {coverage}%")


class TestPytest:
    def test_should_report_tests_and_coverage_metric(self) -> None:
        finding = analyze_pytest(fragment(Analysis.PYTEST, PYTEST_OK))

        assert finding.status == Status.OK
        assert finding.summary == "34 tests"
        assert finding.metric == Metric("coverage", Decimal("100.00"), "%")
        assert "app/a.py" in finding.details

    def test_should_count_skipped_tests(self) -> None:
        output = PYTEST_OK.replace("34 passed in", "33 passed, 1 skipped in")

        assert analyze_pytest(fragment(Analysis.PYTEST, output)).summary == "34 tests (1 skipped)"

    def test_should_fail_when_coverage_is_below_minimum(self) -> None:
        finding = analyze_pytest(fragment(Analysis.PYTEST, PYTEST_LOW_COVERAGE, 1))

        assert finding.status == Status.FAILED
        assert finding.summary == "34 tests · coverage below the 80.0% minimum"
        assert finding.metric == Metric("coverage", Decimal("50.00"), "%")

    def test_should_list_the_failed_tests_with_their_message(self) -> None:
        finding = analyze_pytest(fragment(Analysis.PYTEST, PYTEST_FAILED, 1))

        assert finding.status == Status.FAILED
        assert finding.summary == "1 of 34 tests failed"
        assert finding.is_markdown
        assert finding.details.startswith(
            "- `tests/unit/test_a.py::test_should_x`: assert 1 == 2\n"
            "- `tests/unit/test_b.py::test_should_y`\n"
        )
        assert "<details><summary>Output</summary>" in finding.details

    def test_should_truncate_long_failure_messages_and_lists(self) -> None:
        lines = [f"FAILED tests/t.py::test_{index} - {'x' * 500}" for index in range(32)]
        output = "\n".join([*lines, "==== 32 failed in 1.00s ===="])

        finding = analyze_pytest(fragment(Analysis.PYTEST, output, 1))

        listed = finding.details.split("<details>")[0]
        assert "x" * quality_report.MAX_FAILURE_MESSAGE_CHARS not in listed
        assert "- ... and 2 more" in listed
        assert "`tests/t.py::test_31`" not in listed

    def test_should_show_the_raw_output_when_no_failed_test_is_listed(self) -> None:
        output = "==== 1 failed in 1.00s ===="

        finding = analyze_pytest(fragment(Analysis.PYTEST, output, 1))

        assert finding.details == f"```text\n{output}\n```"

    def test_should_fail_when_pytest_crashes(self) -> None:
        finding = analyze_pytest(fragment(Analysis.PYTEST, "ImportError", 2))

        assert finding.status == Status.FAILED
        assert finding.summary == "pytest failed before finishing"
        assert "ImportError" in finding.details


class TestPipAudit:
    def test_should_report_no_vulnerabilities(self) -> None:
        finding = analyze_pip_audit(fragment(Analysis.PIP_AUDIT, "No known vulnerabilities found"))

        assert finding.status == Status.OK
        assert finding.summary == "no known vulnerabilities"

    def test_should_list_each_vulnerability_with_the_fixed_version(self) -> None:
        finding = analyze_pip_audit(failing_pip_audit())

        assert finding.status == Status.FAILED
        assert finding.summary == "3 vulnerabilities in 2 packages"
        assert finding.is_markdown
        assert finding.details.splitlines()[:5] == [
            "| Package | Version | CVE | Fixed in |",
            "| --- | --- | --- | --- |",
            "| filelock | 4.0.4 | CVE-2026-112940 | 4.2.1 |",
            "| filelock | 4.0.4 | CVE-2026-112936 | 4.0.9 |",
            "| msgpack | 1.2.2 | CVE-2026-114613 | no fix yet |",
        ]
        assert "`uv lock --upgrade-package filelock --upgrade-package msgpack`" in finding.details

    def test_should_truncate_a_long_list_of_vulnerabilities(self) -> None:
        rows = [
            f"pkg{index:02} 1.0 CVE-{index} 2.0"
            for index in range(quality_report.MAX_VULNERABILITIES_LISTED + 1)
        ]
        header = "Found 51 known vulnerabilities in 51 packages\nName Version ID Fix Versions\n---"
        output = "\n".join([header, *rows])

        finding = analyze_pip_audit(fragment(Analysis.PIP_AUDIT, output, 1))

        assert "... and 1 more" in finding.details
        assert "| pkg50 |" not in finding.details

    def test_should_keep_the_raw_output_when_the_table_is_not_recognized(self) -> None:
        output = "Found 1 known vulnerability in 1 package\nsomething else"

        finding = analyze_pip_audit(fragment(Analysis.PIP_AUDIT, output, 1))

        assert finding.summary == "1 vulnerability in 1 package"
        assert not finding.is_markdown
        assert finding.details == output

    def test_should_report_a_crash(self) -> None:
        finding = analyze_pip_audit(fragment(Analysis.PIP_AUDIT, "network down", 1))

        assert finding.summary == "pip-audit failed"
        assert finding.details == "network down"


class TestImportLinter:
    def test_should_list_kept_contracts(self) -> None:
        finding = analyze_import_linter(fragment(Analysis.IMPORT_LINTER, IMPORT_LINTER_OK))

        assert finding.status == Status.OK
        assert finding.summary == "2 contracts kept"
        assert "Domain does not depend on outer layers" in finding.details

    def test_should_show_the_broken_contract_and_violating_import(self) -> None:
        finding = analyze_import_linter(fragment(Analysis.IMPORT_LINTER, IMPORT_LINTER_BROKEN, 1))

        assert finding.status == Status.FAILED
        assert finding.summary == "1 of 2 contracts broken"
        assert "- **Domain does not depend on outer layers**" in finding.details
        assert "```text\nDomain does not depend on outer layers\n---" in finding.details
        assert finding.details.count("Broken contracts") == 1
        assert "app.domain.usecases.x -> app.infra.db" in finding.details

    def test_should_fail_when_no_contract_was_evaluated(self) -> None:
        finding = analyze_import_linter(fragment(Analysis.IMPORT_LINTER, "config error", 1))

        assert finding.summary == "import-linter failed before evaluating the contracts"


class TestSmoke:
    def test_should_report_boot_time(self) -> None:
        finding = analyze_smoke(fragment(Analysis.SMOKE, SMOKE_OK))

        assert finding.status == Status.OK
        assert finding.summary == "healthy in 1.234s · /health and /ready answered"
        assert finding.details == ""

    def test_should_include_logs_only_when_failed(self) -> None:
        finding = analyze_smoke(fragment(Analysis.SMOKE, SMOKE_FAILED, 1))

        assert finding.status == Status.FAILED
        assert "did not become healthy" in finding.summary
        assert "/health ❌ · /ready ❌" in finding.summary
        assert finding.details == "Traceback: boom"


class TestSchemathesis:
    def test_should_report_cases_operations_and_seed(self) -> None:
        finding = analyze_schemathesis(fragment(Analysis.SCHEMATHESIS, SCHEMATHESIS_OK))

        assert finding.status == Status.OK
        assert finding.summary == "54 cases on 3 operations · seed 1"
        assert finding.details == ""

    def test_should_list_failed_checks_with_the_failures_and_api_logs(self) -> None:
        finding = analyze_schemathesis(fragment(Analysis.SCHEMATHESIS, SCHEMATHESIS_FAILED, 1))

        assert finding.status == Status.FAILED
        assert finding.summary == (
            "2 failures: Server error (1); Undocumented HTTP status code (1)"
            " · 29 cases on 3 operations · seed 1"
        )
        assert finding.details.startswith("_" * 33 + " GET /example")
        assert "curl -X GET" in finding.details
        assert "SUMMARY" not in finding.details
        assert finding.details.endswith("--- API logs ---\nRuntimeError: boom")

    def test_should_report_why_the_contract_test_did_not_run(self) -> None:
        finding = analyze_schemathesis(fragment(Analysis.SCHEMATHESIS, SCHEMATHESIS_NOT_STARTED, 1))

        assert finding.status == Status.FAILED
        assert finding.summary == (
            "contract test did not run: the API process exited before becoming healthy"
        )
        assert finding.details == "ValidationError: env"

    def test_should_fail_with_the_raw_output_when_nothing_is_recognized(self) -> None:
        finding = analyze_schemathesis(fragment(Analysis.SCHEMATHESIS, "uv: not found", 127))

        assert finding.summary == "contract test did not run"
        assert finding.details == "uv: not found"


class TestOasdiff:
    def test_should_report_no_api_changes(self) -> None:
        finding = analyze_oasdiff(fragment(Analysis.OASDIFF, OASDIFF_NO_CHANGES))

        assert finding.status == Status.OK
        assert finding.summary == "no API changes"

    def test_should_list_additive_changes_as_ok(self) -> None:
        finding = analyze_oasdiff(fragment(Analysis.OASDIFF, OASDIFF_INFO_ONLY))

        assert finding.status == Status.OK
        assert finding.summary == "1 API change, none breaking"
        assert finding.details == "info    API GET /items: endpoint added [endpoint-added]"

    def test_should_fail_on_breaking_changes_and_list_every_change(self) -> None:
        finding = analyze_oasdiff(fragment(Analysis.OASDIFF, OASDIFF_BREAKING, 1))

        assert finding.status == Status.FAILED
        assert finding.summary == "1 breaking change out of 3"
        assert finding.details.splitlines() == [
            "error   API GET /example: the `query` request parameter `field1` became required"
            " [request-parameter-became-required]",
            "warning API GET /ready: the response property `status` became optional"
            " [response-property-became-optional]",
            "info    API GET /items: endpoint added [endpoint-added]",
        ]

    def test_should_warn_on_possible_breaking_changes(self) -> None:
        output = OASDIFF_BREAKING.replace("3 changes: 1 error", "3 changes: 0 error")

        finding = analyze_oasdiff(fragment(Analysis.OASDIFF, output))

        assert finding.status == Status.WARNING
        assert finding.summary == "1 possible breaking change (warning) out of 3"

    @pytest.mark.parametrize(
        ("output", "exit_code"),
        [
            ("oasdiff not found (oasdiff): install it, see the README", 127),
            ("`git merge-base origin/x HEAD` failed", 1),
            ("1 change: 0 error, 0 warning, 1 info\npanic: boom", 2),
            ("something unexpected", 0),
        ],
    )
    def test_should_fail_when_the_diff_did_not_complete(self, output: str, exit_code: int) -> None:
        finding = analyze_oasdiff(fragment(Analysis.OASDIFF, output, exit_code))

        assert finding.status == Status.FAILED
        assert finding.summary == "OpenAPI diff failed before comparing"
        assert output in finding.details


class TestMutation:
    def test_should_list_survivors_with_file_and_function(self) -> None:
        survivor = {
            "file": "app/domain/x.py",
            "function": "X.run",
            "status": "survived",
            "name": "n",
        }
        output = mutation_output(90.0, [survivor])

        finding = analyze_mutation(fragment(Analysis.MUTATION, output))

        assert finding.status == Status.OK
        assert finding.summary == "9 of 10 mutants killed (threshold 90.0%)"
        assert finding.metric == Metric("score", Decimal("90.0"), "%")
        assert finding.is_markdown
        assert "| `app/domain/x.py` | `X.run` | survived |" in finding.details

    def test_should_fail_below_threshold(self) -> None:
        finding = analyze_mutation(fragment(Analysis.MUTATION, mutation_output(50.0, []), 1))

        assert finding.status == Status.FAILED

    def test_should_report_no_domain_change_as_skipped_with_the_reason(self) -> None:
        output = mutation_output(100.0, [], skipped=True)

        finding = analyze_mutation(fragment(Analysis.MUTATION, output))

        assert finding.status == Status.SKIPPED
        assert finding.summary == "no domain file changed"

    def test_should_fail_when_mutmut_crashes_without_result(self) -> None:
        finding = analyze_mutation(fragment(Analysis.MUTATION, "CalledProcessError", 1))

        assert finding.status == Status.FAILED
        assert "CalledProcessError" in finding.details


class TestSuppressions:
    def test_should_share_the_result_prefix_with_the_producer(self) -> None:
        assert quality_report.SUPPRESSIONS_RESULT_PREFIX == suppressions.RESULT_PREFIX

    def test_should_report_totals_when_matching_the_baseline(self) -> None:
        finding = analyze_suppressions(fragment(Analysis.SUPPRESSIONS, SUPPRESSIONS_OK))

        assert finding.status == Status.OK
        assert finding.summary == "baseline matched"
        assert finding.metric == Metric("suppressions", Decimal(1))
        assert finding.details == "nosec: 1"

    def test_should_list_new_suppressions_with_file_and_lines(self) -> None:
        second = suppressions.Occurrence("app/h.py", 9, suppressions.Kind.NOSEC)
        output = suppressions_output(
            (NOSEC_IN_HANDLER, second), Counter({("app/h.py", suppressions.Kind.NOSEC): 1})
        )

        finding = analyze_suppressions(fragment(Analysis.SUPPRESSIONS, output, 1))

        assert finding.status == Status.FAILED
        assert finding.summary == "1 new suppression above the baseline"
        assert finding.metric == Metric("suppressions", Decimal(2))
        assert finding.is_markdown
        assert "| `app/h.py` | nosec | 1 → 2 | 7, 9 |" in finding.details

    def test_should_ask_to_update_a_stale_baseline(self) -> None:
        output = suppressions_output((), Counter({("app/h.py", suppressions.Kind.NOQA): 2}))

        finding = analyze_suppressions(fragment(Analysis.SUPPRESSIONS, output, 1))

        assert finding.status == Status.FAILED
        assert "2 suppressions removed" in finding.summary
        assert "make suppressions-update" in finding.summary
        assert "| `app/h.py` | noqa | 2 → 0 | - |" in finding.details

    def test_should_truncate_a_long_list_of_changes(self) -> None:
        occurrences = tuple(
            suppressions.Occurrence(f"app/m{index:02}.py", 1, suppressions.Kind.NOQA)
            for index in range(quality_report.MAX_SUPPRESSION_CHANGES_LISTED + 2)
        )
        output = suppressions_output(occurrences, Counter())

        finding = analyze_suppressions(fragment(Analysis.SUPPRESSIONS, output, 1))

        assert "52 new suppressions" in finding.summary
        assert "... and 2 more" in finding.details
        assert "app/m51.py" not in finding.details

    def test_should_fail_when_the_check_crashes(self) -> None:
        finding = analyze_suppressions(fragment(Analysis.SUPPRESSIONS, "SyntaxError: boom", 1))

        assert finding.status == Status.FAILED
        assert "SyntaxError: boom" in finding.details


class TestOneLineDetails:
    @pytest.mark.parametrize(
        ("analysis", "output", "summary"),
        [
            (Analysis.RUFF_CHECK, "All checks passed!", "no lint issues"),
            (Analysis.RUFF_FORMAT, "47 files already formatted", "47 files formatted"),
            (Analysis.RUFF_FORMAT, "1 file already formatted", "1 file formatted"),
            (Analysis.RUFF_FORMAT, "", ""),
            (Analysis.MYPY, "Success: no issues found in 35 source files", "35 files"),
            (Analysis.BANDIT, "Total lines of code: 244", "no issues · 244 lines scanned"),
            (Analysis.BANDIT, "No issues identified.", "no issues"),
            (Analysis.DEPTRY, "Scanning 27 files...\nSuccess!", "27 files · no dependency issues"),
            (Analysis.DEPTRY, "Success!", "no dependency issues"),
            (Analysis.VULTURE, "", "no dead code"),
            (Analysis.XENON, "", "within the threshold"),
        ],
    )
    def test_should_summarize_a_passing_analysis_in_one_line(
        self, analysis: Analysis, output: str, summary: str
    ) -> None:
        finding = quality_report.ANALYZERS[analysis](fragment(analysis, output))

        assert finding.status == Status.OK
        assert finding.summary == summary

    @pytest.mark.parametrize(
        ("analysis", "output", "summary"),
        [
            (Analysis.RUFF_CHECK, "Found 3 errors.", "3 lint issues"),
            (Analysis.RUFF_CHECK, "boom", "lint failed"),
            (Analysis.RUFF_FORMAT, "Would reformat: a.py", "1 file to format (`make format-code`)"),
            (Analysis.RUFF_FORMAT, "boom", "format check failed"),
            (Analysis.MYPY, "Found 2 errors in 1 file", "2 type errors"),
            (Analysis.MYPY, "boom", "mypy failed"),
            (Analysis.BANDIT, ">> Issue: [B101]\n>> Issue: [B102]", "2 issues"),
            (Analysis.BANDIT, "boom", "bandit failed"),
            (
                Analysis.XENON,
                'ERROR:xenon:block "app.py:1 f" has a rank of C',
                "1 block above the threshold",
            ),
            (Analysis.XENON, "boom", "complexity above the threshold"),
        ],
    )
    def test_should_summarize_a_failing_analysis_in_one_line(
        self, analysis: Analysis, output: str, summary: str
    ) -> None:
        finding = quality_report.ANALYZERS[analysis](fragment(analysis, output, 1))

        assert finding.status == Status.FAILED
        assert finding.summary == summary
        assert finding.details == output


class TestAdvisoryTools:
    def test_should_warn_on_dead_code_when_advisory(self) -> None:
        advisory = Fragment(Analysis.VULTURE, 3, "app/a.py:1: unused function 'f'", advisory=True)

        finding = analyze_vulture(advisory)

        assert finding.status == Status.WARNING
        assert finding.summary == "1 dead code item (advisory, does not block)"

    def test_should_fail_on_dead_code_when_not_advisory(self) -> None:
        finding = analyze_vulture(fragment(Analysis.VULTURE, "app/a.py:1: unused 'f'", 3))

        assert finding.status == Status.FAILED
        assert finding.summary == "1 dead code item"

    def test_should_fail_with_dependency_issue_count(self) -> None:
        output = "pyproject.toml: DEP002 'x' defined as a dependency but not used\nFound 2 dependency issues."

        finding = analyze_deptry(fragment(Analysis.DEPTRY, output, 1))

        assert finding.status == Status.FAILED
        assert finding.summary == "2 dependency issues"
        assert "DEP002" in finding.details

    def test_should_fail_with_single_dependency_issue(self) -> None:
        finding = analyze_deptry(fragment(Analysis.DEPTRY, "Found 1 dependency issue.", 1))

        assert finding.summary == "1 dependency issue"

    def test_should_report_deptry_failure_without_count(self) -> None:
        finding = analyze_deptry(fragment(Analysis.DEPTRY, "boom", 2))

        assert finding.status == Status.FAILED
        assert finding.summary == "deptry failed"

    def test_should_ignore_uv_environment_warning(self) -> None:
        noisy = "warning: `VIRTUAL_ENV=/x` does not match the project environment path"

        assert analyze_vulture(fragment(Analysis.VULTURE, noisy)).status == Status.OK

    def test_should_count_bandit_issues(self) -> None:
        finding = analyze_bandit(fragment(Analysis.BANDIT, ">> Issue: [B101]\n>> Issue: [B102]", 1))

        assert finding.summary == "2 issues"

    def test_should_count_xenon_blocks(self) -> None:
        output = 'ERROR:xenon:block "app.py:1 f" has a rank of C'

        assert analyze_xenon(fragment(Analysis.XENON, output, 1)).summary == (
            "1 block above the threshold"
        )


class TestMetric:
    @pytest.mark.parametrize(
        ("current", "base", "expected"),
        [
            ("100.00", "100.00", "coverage 100.00% (=)"),
            ("91.2", "93.3", "coverage 91.2% (↓2.1)"),
            ("95.50", "94.00", "coverage 95.50% (↑1.50)"),
        ],
    )
    def test_should_render_the_variation_against_the_base(
        self, current: str, base: str, expected: str
    ) -> None:
        metric = Metric("coverage", Decimal(current), "%")

        assert metric.render(Metric("coverage", Decimal(base), "%")) == expected

    def test_should_render_na_without_a_base(self) -> None:
        assert Metric("suppressions", Decimal(3)).render(None) == "suppressions 3 (n/a)"


class TestVerdict:
    def test_should_use_a_tip_alert_when_everything_passed(self) -> None:
        report = render(all_ok_fragments(), {}, baseline=NO_BASELINE)

        assert report.startswith(f"{quality_report.MARKER}\n## Quality Report\n\n")
        assert "> [!TIP]\n> ✅ 14 passed\n" in report

    def test_should_use_a_caution_alert_with_the_counts_when_something_failed(self) -> None:
        fragments = all_ok_fragments()
        fragments[Analysis.PIP_AUDIT] = failing_pip_audit()
        fragments[Analysis.MUTATION] = fragment(
            Analysis.MUTATION, mutation_output(100.0, [], skipped=True)
        )

        report = render(fragments, {}, baseline=NO_BASELINE)

        assert "> [!CAUTION]\n> ❌ 1 failed · ✅ 12 passed · ⏭️ 1 skipped\n" in report

    def test_should_use_a_warning_alert_when_only_warnings(self) -> None:
        fragments = all_ok_fragments()
        fragments[Analysis.VULTURE] = Fragment(Analysis.VULTURE, 3, "app/a.py:1: x", True)

        report = render(fragments, {}, baseline=NO_BASELINE)

        assert "> [!WARNING]\n> ⚠️ 1 warning · ✅ 13 passed\n" in report

    def test_should_say_when_every_failure_is_inherited_from_the_base(self) -> None:
        fragments = all_ok_fragments()
        fragments[Analysis.PIP_AUDIT] = failing_pip_audit()
        fragments[Analysis.MYPY] = fragment(Analysis.MYPY, "Found 1 error", 1)
        baseline = Baseline("main", dict(fragments))

        report = render(fragments, {}, baseline=baseline)

        assert "> ❌ 2 failed, all inherited from `main` · ✅ 12 passed\n" in report

    def test_should_count_inherited_failures_when_only_some_are(self) -> None:
        fragments = all_ok_fragments()
        baseline = Baseline("main", {**fragments, Analysis.PIP_AUDIT: failing_pip_audit()})
        fragments[Analysis.PIP_AUDIT] = failing_pip_audit()
        fragments[Analysis.MYPY] = fragment(Analysis.MYPY, "Found 1 error", 1)

        report = render(fragments, {}, baseline=baseline)

        assert "> ❌ 2 failed (1 inherited from `main`) · ✅ 12 passed\n" in report

    def test_should_say_inherited_without_all_for_a_single_failure(self) -> None:
        fragments = all_ok_fragments()
        fragments[Analysis.PIP_AUDIT] = failing_pip_audit()

        report = render(fragments, {}, baseline=Baseline("develop", dict(fragments)))

        assert "> ❌ 1 failed, inherited from `develop` · ✅ 13 passed\n" in report


class TestProblems:
    def test_should_show_failures_open_before_the_table(self) -> None:
        fragments = all_ok_fragments()
        fragments[Analysis.PIP_AUDIT] = failing_pip_audit()

        report = render(fragments, {}, baseline=NO_BASELINE)

        failure = report.index("### ❌ Vulnerable dependencies (pip-audit)")
        assert failure < report.index("| Area | Check | Status | Detail |")
        section = report[failure : report.index("| Area |")]
        assert "3 vulnerabilities in 2 packages\n" in section
        assert "| filelock | 4.0.4 | CVE-2026-112940 | 4.2.1 |" in section
        assert "**Reproduce**: `uv run pip-audit`" in section
        assert "<details" not in section

    def test_should_not_open_a_section_for_passing_analyses(self) -> None:
        report = render(all_ok_fragments(), {}, baseline=NO_BASELINE)

        assert "### " not in report

    def test_should_fence_raw_output_and_keep_the_fence_closed(self) -> None:
        fragments = all_ok_fragments()
        fragments[Analysis.MYPY] = fragment(Analysis.MYPY, "```\nevil", 1)

        report = render(fragments, {}, baseline=NO_BASELINE)

        assert "```text\n'''\nevil\n```" in report
        assert "**Reproduce**: `uv run mypy app tests`" in report

    def test_should_truncate_long_output(self) -> None:
        fragments = all_ok_fragments()
        fragments[Analysis.MYPY] = fragment(Analysis.MYPY, "x" * 20000, 1)

        report = render(fragments, {}, baseline=NO_BASELINE)

        assert "[...truncated...]" in report
        assert len(report) < 30000

    def test_should_name_the_failing_analysis_inside_a_multi_analysis_check(self) -> None:
        fragments = all_ok_fragments()
        fragments[Analysis.RUFF_FORMAT] = fragment(Analysis.RUFF_FORMAT, "Would reformat: a.py", 1)

        report = render(fragments, {}, baseline=NO_BASELINE)

        assert "### ❌ Lint and format (ruff)" in report
        assert "**ruff-format**: 1 file to format (`make format-code`)" in report
        assert "**ruff-check**" not in report
        assert "**Reproduce**: `make check-code`" in report

    def test_should_label_an_inherited_failure(self) -> None:
        fragments = all_ok_fragments()
        fragments[Analysis.PIP_AUDIT] = failing_pip_audit()

        report = render(fragments, {}, baseline=Baseline("main", dict(fragments)))

        assert "3 vulnerabilities in 2 packages · inherited from `main`\n" in report

    def test_should_list_failures_before_warnings(self) -> None:
        fragments = all_ok_fragments()
        fragments[Analysis.VULTURE] = Fragment(Analysis.VULTURE, 3, "app/a.py:1: x", True)
        fragments[Analysis.IMPORT_LINTER] = fragment(
            Analysis.IMPORT_LINTER, IMPORT_LINTER_BROKEN, 1
        )

        report = render(fragments, {}, baseline=NO_BASELINE)

        assert report.index("### ❌ Architecture contracts") < report.index("### ⚠️ Dead code")

    def test_should_report_a_job_that_produced_no_result(self) -> None:
        fragments = all_ok_fragments()
        del fragments[Analysis.MYPY]

        report = render(fragments, {"types": "failure"}, baseline=NO_BASELINE)

        assert "### ❌ Types (mypy)" in report
        assert "job `types` ended as `failure` without producing a result" in report


class TestTable:
    def test_should_group_the_checks_by_area_in_order(self) -> None:
        report = render(all_ok_fragments(), {}, baseline=NO_BASELINE)

        rows = [line for line in report.splitlines() if line.startswith("| ")][2:]
        areas = [row.split(" | ")[0].removeprefix("| ") for row in rows]
        assert [area for area in areas if area.strip()] == [
            "**Code**",
            "**Security and dependencies**",
            "**Behavior**",
            "**Architecture**",
        ]
        assert len(rows) == len(quality_report.SECTIONS)

    def test_should_keep_every_check_of_an_area_together(self) -> None:
        groups = [section.group for section in quality_report.SECTIONS]

        assert groups == sorted(groups, key=list(quality_report.Group).index)

    def test_should_show_a_one_line_detail_per_check(self) -> None:
        report = render(all_ok_fragments(), {}, baseline=NO_BASELINE)

        assert "|  | Types (mypy) | ✅ | 0 files |" in report
        assert (
            "| **Behavior** | Tests and coverage (pytest) | ✅ | 34 tests · coverage 100.00% (n/a) |"
            in report
        )
        assert (
            "| **Architecture** | Architecture contracts (import-linter) | ✅ | 2 contracts kept |"
            in report
        )
        assert (
            "|  | API contract (schemathesis) | ✅ | 54 cases on 3 operations · seed 1 |" in report
        )

    def test_should_show_the_reason_next_to_a_skipped_check(self) -> None:
        fragments = all_ok_fragments()
        fragments[Analysis.MUTATION] = fragment(
            Analysis.MUTATION, mutation_output(100.0, [], skipped=True)
        )
        del fragments[Analysis.SMOKE]

        report = render(fragments, {"smoke": "cancelled"}, baseline=NO_BASELINE)

        assert "| Mutation testing (mutmut) | ⏭️ | no domain file changed |" in report
        assert "| Boot smoke (/health, /ready) | ⏭️ | job `smoke` cancelled |" in report

    def test_should_show_the_variation_against_the_base(self) -> None:
        base = all_ok_fragments()
        base[Analysis.PYTEST] = fragment(Analysis.PYTEST, pytest_with_coverage("97.30"))
        current = all_ok_fragments()
        current[Analysis.PYTEST] = fragment(Analysis.PYTEST, pytest_with_coverage("95.20"))

        report = render(current, {}, baseline=Baseline("main", base))

        assert "34 tests · coverage 95.20% (↓2.10) |" in report
        assert "baseline matched · suppressions 1 (=) |" in report
        assert "9 of 10 mutants killed (threshold 90.0%) · score 100.0% (=) |" in report

    def test_should_label_an_inherited_failure_in_the_table(self) -> None:
        fragments = all_ok_fragments()
        fragments[Analysis.PIP_AUDIT] = failing_pip_audit()

        report = render(fragments, {}, baseline=Baseline("main", dict(fragments)))

        assert "| ❌ | 3 vulnerabilities in 2 packages · inherited from `main` |" in report

    def test_should_escape_pipes_in_the_detail(self) -> None:
        fragments = all_ok_fragments()
        fragments[Analysis.SMOKE] = fragment(Analysis.SMOKE, ">> smoke: a | b", 1)

        report = render(fragments, {}, baseline=NO_BASELINE)

        assert "API did not start: a \\| b" in report


class TestMissingBaseline:
    def test_should_render_without_a_base(self) -> None:
        report = render(all_ok_fragments(), {}, baseline=NO_BASELINE)

        assert "coverage 100.00% (n/a)" in report
        assert "inherited" not in report
        assert report.endswith("<sub>no `main` baseline: deltas are n/a</sub>\n")

    def test_should_not_mark_a_failure_as_inherited_when_the_base_passed(self) -> None:
        fragments = all_ok_fragments()
        baseline = Baseline("main", dict(fragments))
        fragments[Analysis.PIP_AUDIT] = failing_pip_audit()

        report = render(fragments, {}, baseline=baseline)

        assert "inherited" not in report

    def test_should_not_mark_a_failure_as_inherited_when_the_base_lacks_the_analysis(
        self,
    ) -> None:
        fragments = all_ok_fragments()
        fragments[Analysis.PIP_AUDIT] = failing_pip_audit()
        baseline = Baseline("main", {Analysis.MYPY: fragments[Analysis.MYPY]})

        report = render(fragments, {}, baseline=baseline)

        assert "inherited" not in report
        assert "coverage 100.00% (n/a)" in report

    def test_should_ignore_a_base_fragment_it_cannot_parse(self) -> None:
        broken = fragment(Analysis.MUTATION, quality_report.MUTATION_RESULT_PREFIX + "{bad", 0)
        baseline = Baseline("main", {Analysis.MUTATION: broken})

        report = render(all_ok_fragments(), {}, baseline=baseline)

        assert "score 100.0% (n/a)" in report

    def test_should_load_the_baseline_from_a_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
        monkeypatch.setenv("QUALITY_REPORT_BASE_RUN_ID", "7")
        fragment(Analysis.MYPY, "ok").write(tmp_path)

        baseline = quality_report.load_baseline(tmp_path, "main")

        assert list(baseline.fragments) == [Analysis.MYPY]
        assert baseline.run_url == "https://github.com/o/r/actions/runs/7"

    def test_should_treat_a_missing_directory_as_no_baseline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("QUALITY_REPORT_BASE_RUN_ID", raising=False)

        assert not quality_report.load_baseline(tmp_path / "missing", "main").is_available
        assert not quality_report.load_baseline(None, "main").is_available


class TestPassedDetails:
    def test_should_group_passing_details_in_a_single_closed_block(self) -> None:
        report = render(all_ok_fragments(), {}, baseline=NO_BASELINE)

        assert report.count("<details>") == 1
        assert "<details><summary>14 passed</summary>" in report
        assert "**Tests and coverage (pytest)** · Coverage" in report
        assert "**Architecture contracts (import-linter)** · Contracts" in report
        assert "**Suppressions (ratchet)** · By kind" in report

    def test_should_leave_failed_details_out_of_the_passed_block(self) -> None:
        fragments = all_ok_fragments()
        fragments[Analysis.IMPORT_LINTER] = fragment(
            Analysis.IMPORT_LINTER, IMPORT_LINTER_BROKEN, 1
        )

        report = render(fragments, {}, baseline=NO_BASELINE)

        passed = report[report.index("<details><summary>13 passed") :]
        assert "Architecture contracts" not in passed

    def test_should_omit_the_block_when_no_passing_check_has_details(self) -> None:
        fragments = {analysis: fragment(analysis) for analysis in Analysis}
        fragments[Analysis.MUTATION] = fragment(
            Analysis.MUTATION, mutation_output(100.0, [], skipped=True)
        )
        fragments[Analysis.SUPPRESSIONS] = fragment(Analysis.SUPPRESSIONS, "x", 1)

        report = render(fragments, {}, baseline=NO_BASELINE)

        assert "passed</summary>" not in report


class TestFooter:
    def test_should_build_the_footer_from_the_github_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
        monkeypatch.setenv("GITHUB_RUN_ID", "42")
        monkeypatch.setenv("GITHUB_SHA", "abcdef0123")
        monkeypatch.delenv("QUALITY_REPORT_SHA", raising=False)

        footer = quality_report.footer_from_environment(NOW)

        assert footer == (
            "commit `abcdef0` · 2026-11-13 14:05 UTC · "
            "[workflow run](https://github.com/o/r/actions/runs/42)"
        )

    def test_should_prefer_the_pull_request_head_sha(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_SHA", "merge000000")
        monkeypatch.setenv("QUALITY_REPORT_SHA", "head1234567")

        assert quality_report.footer_from_environment(NOW).startswith("commit `head123`")

    def test_should_keep_only_the_time_outside_github(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for variable in ("GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITHUB_SHA", "QUALITY_REPORT_SHA"):
            monkeypatch.delenv(variable, raising=False)

        assert quality_report.footer_from_environment(NOW) == "2026-11-13 14:05 UTC"

    def test_should_end_the_report_with_the_footer_and_the_baseline_run(self) -> None:
        baseline = Baseline("main", all_ok_fragments(), "https://ci/runs/7")

        report = render(all_ok_fragments(), {}, baseline=baseline, footer="commit `abc`")

        assert report.endswith(
            "---\n<sub>commit `abc` · compared with the [last `main` run](https://ci/runs/7)</sub>\n"
        )

    def test_should_mention_the_baseline_run_without_a_link(self) -> None:
        report = render(all_ok_fragments(), {}, baseline=Baseline("main", all_ok_fragments()))

        assert report.endswith("<sub>compared with the last `main` run</sub>\n")


class TestRunCommand:
    def test_should_store_fragment_and_keep_exit_code(self, tmp_path: Path) -> None:
        code = quality_report.run_command(
            Analysis.XENON, ["bash", "-c", "echo out; exit 3"], tmp_path, advisory=False
        )

        stored = Fragment.read(tmp_path / "xenon.json")
        assert code == 3
        assert stored.exit_code == 3
        assert stored.output == "out\n"

    def test_should_keep_real_exit_code_in_fragment_but_not_block_when_advisory(
        self, tmp_path: Path
    ) -> None:
        code = quality_report.run_command(
            Analysis.VULTURE, ["bash", "-c", "exit 3"], tmp_path, advisory=True
        )

        assert code == 0
        assert Fragment.read(tmp_path / "vulture.json").exit_code == 3

    def test_should_fail_with_127_when_command_does_not_exist(self, tmp_path: Path) -> None:
        code = quality_report.run_command(Analysis.MYPY, ["no-such-binary-xyz"], tmp_path, False)

        assert code == 127
        assert Fragment.read(tmp_path / "mypy.json").exit_code == 127


class TestLoading:
    def test_should_load_fragments_and_ignore_invalid_files(self, tmp_path: Path) -> None:
        fragment(Analysis.MYPY, "ok").write(tmp_path)
        (tmp_path / "broken.json").write_text("{not json")
        (tmp_path / "unknown.json").write_text(
            json.dumps({"analysis": "nope", "exit_code": 0, "output": ""})
        )

        loaded = quality_report.load_fragments(tmp_path)

        assert list(loaded) == [Analysis.MYPY]

    def test_should_parse_needs_json(self) -> None:
        needs = json.dumps({"lint": {"result": "success", "outputs": {}}, "smoke": {}})

        assert quality_report.parse_job_results(needs) == {
            "lint": "success",
            "smoke": "unknown",
        }
        assert quality_report.parse_job_results("") == {}


class TestMain:
    def test_should_render_report_to_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fragment(Analysis.MYPY, "Success: no issues found in 3 source files").write(tmp_path)
        output = tmp_path / "report.md"
        monkeypatch.setattr(
            "sys.argv",
            ["quality_report", "render", "--dir", str(tmp_path), "--output", str(output)],
        )

        assert quality_report.main() == 0
        report = output.read_text()
        assert "|  | Types (mypy) | ✅ | 3 files |" in report
        assert "no `main` baseline: deltas are n/a" in report

    def test_should_compare_with_the_base_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        current, base = tmp_path / "current", tmp_path / "base"
        failing_pip_audit().write(current)
        failing_pip_audit().write(base)
        monkeypatch.setattr(
            "sys.argv",
            [
                "quality_report",
                "render",
                "--dir",
                str(current),
                "--base-dir",
                str(base),
                "--base-name",
                "develop",
            ],
        )

        assert quality_report.main() == 0
        assert "inherited from `develop`" in capsys.readouterr().out

    def test_should_propagate_command_exit_code(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "sys.argv",
            ["quality_report", "run", "mypy", "--dir", str(tmp_path), "--", "bash", "-c", "exit 5"],
        )

        assert quality_report.main() == 5
