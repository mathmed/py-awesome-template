import json
import re
from collections import Counter
from pathlib import Path

import pytest

from scripts import mutation, quality_report, suppressions
from scripts.quality_report import (
    Analysis,
    Fragment,
    Status,
    analyze_bandit,
    analyze_import_linter,
    analyze_mutation,
    analyze_oasdiff,
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


def mutation_output(score: float, survivors: list[dict[str, str]], *, skipped: bool = False) -> str:
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


class TestPytest:
    def test_should_report_counts_and_coverage(self) -> None:
        finding = analyze_pytest(fragment(Analysis.PYTEST, PYTEST_OK))

        assert finding.status == Status.OK
        assert "34 passed, 0 failed, 34 total" in finding.summary
        assert "100.00% (minimum 80.0%)" in finding.summary
        assert "app/a.py" in finding.details

    def test_should_fail_when_coverage_is_below_minimum(self) -> None:
        finding = analyze_pytest(fragment(Analysis.PYTEST, PYTEST_LOW_COVERAGE, 1))

        assert finding.status == Status.FAILED
        assert "below the minimum" in finding.summary

    def test_should_fail_when_a_test_fails(self) -> None:
        finding = analyze_pytest(fragment(Analysis.PYTEST, PYTEST_FAILED, 1))

        assert finding.status == Status.FAILED
        assert "1 failed" in finding.summary
        assert "test_should_x" in finding.details

    def test_should_fail_when_pytest_crashes(self) -> None:
        finding = analyze_pytest(fragment(Analysis.PYTEST, "ImportError", 2))

        assert finding.status == Status.FAILED
        assert "before finishing" in finding.summary


class TestImportLinter:
    def test_should_list_kept_contracts(self) -> None:
        finding = analyze_import_linter(fragment(Analysis.IMPORT_LINTER, IMPORT_LINTER_OK))

        assert finding.status == Status.OK
        assert "2 contracts kept" in finding.summary
        assert "Domain does not depend on outer layers" in finding.details

    def test_should_show_broken_contract_and_violating_import(self) -> None:
        finding = analyze_import_linter(fragment(Analysis.IMPORT_LINTER, IMPORT_LINTER_BROKEN, 1))

        assert finding.status == Status.FAILED
        assert "**Domain does not depend on outer layers**" in finding.summary
        assert "app.domain.usecases.x -> app.infra.db" in finding.details


class TestSmoke:
    def test_should_report_boot_time_and_endpoints(self) -> None:
        finding = analyze_smoke(fragment(Analysis.SMOKE, SMOKE_OK))

        assert finding.status == Status.OK
        assert "1.234s" in finding.summary
        assert "/health ✅ · /ready ✅" in finding.summary
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
        assert finding.summary == (
            "No contract violations · 54 test cases on 3 operations · seed 1"
        )
        assert finding.details == ""

    def test_should_list_failed_checks_with_the_failures_and_api_logs(self) -> None:
        finding = analyze_schemathesis(fragment(Analysis.SCHEMATHESIS, SCHEMATHESIS_FAILED, 1))

        assert finding.status == Status.FAILED
        assert finding.summary == (
            "2 failures: Server error (1); Undocumented HTTP status code (1)"
            " · 29 test cases on 3 operations · seed 1"
        )
        assert finding.details.startswith("_" * 33 + " GET /example")
        assert "curl -X GET" in finding.details
        assert "SUMMARY" not in finding.details
        assert finding.details.endswith("--- API logs ---\nRuntimeError: boom")

    def test_should_report_why_the_contract_test_did_not_run(self) -> None:
        finding = analyze_schemathesis(fragment(Analysis.SCHEMATHESIS, SCHEMATHESIS_NOT_STARTED, 1))

        assert finding.status == Status.FAILED
        assert finding.summary == (
            "Contract test did not run: the API process exited before becoming healthy"
        )
        assert finding.details == "ValidationError: env"

    def test_should_fail_with_the_raw_output_when_nothing_is_recognized(self) -> None:
        finding = analyze_schemathesis(fragment(Analysis.SCHEMATHESIS, "uv: not found", 127))

        assert finding.summary == "Contract test did not run"
        assert finding.details == "uv: not found"


class TestOasdiff:
    def test_should_report_no_api_changes(self) -> None:
        finding = analyze_oasdiff(fragment(Analysis.OASDIFF, OASDIFF_NO_CHANGES))

        assert finding.status == Status.OK
        assert finding.summary == "No API changes"

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
    def test_should_share_the_result_prefix_with_the_producer(self) -> None:
        assert quality_report.MUTATION_RESULT_PREFIX == mutation.RESULT_PREFIX

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
        assert "score 90.0% (threshold 90.0%)" in finding.summary
        assert "| `app/domain/x.py` | `X.run` | survived |" in finding.details

    def test_should_fail_below_threshold(self) -> None:
        finding = analyze_mutation(fragment(Analysis.MUTATION, mutation_output(50.0, []), 1))

        assert finding.status == Status.FAILED

    def test_should_report_no_domain_change_as_skipped(self) -> None:
        output = mutation_output(100.0, [], skipped=True)

        finding = analyze_mutation(fragment(Analysis.MUTATION, output))

        assert finding.status == Status.SKIPPED
        assert "No domain file changed" in finding.summary

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
        assert finding.summary == "1 suppression, matching the baseline"
        assert finding.details == "nosec: 1"

    def test_should_list_new_suppressions_with_file_and_lines(self) -> None:
        second = suppressions.Occurrence("app/h.py", 9, suppressions.Kind.NOSEC)
        output = suppressions_output(
            (NOSEC_IN_HANDLER, second), Counter({("app/h.py", suppressions.Kind.NOSEC): 1})
        )

        finding = analyze_suppressions(fragment(Analysis.SUPPRESSIONS, output, 1))

        assert finding.status == Status.FAILED
        assert finding.summary == "1 new suppression above the baseline"
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


class TestAdvisoryTools:
    def test_should_warn_on_dead_code_when_advisory(self) -> None:
        advisory = Fragment(
            Analysis.VULTURE, 3, "app/a.py:1: unused function 'f'", is_advisory=True
        )

        finding = analyze_vulture(advisory)

        assert finding.status == Status.WARNING
        assert "1 dead code item" in finding.summary

    def test_should_be_ok_without_dead_code(self) -> None:
        assert analyze_vulture(fragment(Analysis.VULTURE)).status == Status.OK

    def test_should_ignore_uv_environment_warning(self) -> None:
        noisy = "warning: `VIRTUAL_ENV=/x` does not match the project environment path"

        assert analyze_vulture(fragment(Analysis.VULTURE, noisy)).status == Status.OK

    def test_should_fail_complexity_above_threshold(self) -> None:
        output = 'ERROR:xenon:block "app.py:1 f" has a rank of C'

        finding = analyze_xenon(fragment(Analysis.XENON, output, 1))

        assert finding.status == Status.FAILED
        assert "1 complexity violation" in finding.summary

    def test_should_count_bandit_issues(self) -> None:
        finding = analyze_bandit(fragment(Analysis.BANDIT, ">> Issue: [B101]\n>> Issue: [B102]", 1))

        assert "2 issues" in finding.summary


class TestRender:
    def test_should_render_all_ok(self) -> None:
        report = render(all_ok_fragments(), {})

        assert report.startswith(quality_report.MARKER)
        assert "✅ **All good**" in report
        for section in quality_report.SECTIONS:
            assert f"| {section.title} | ✅ |" in report

    def test_should_keep_sections_in_the_requested_order(self) -> None:
        report = render(all_ok_fragments(), {})

        positions = [report.index(f"### ✅ {s.title}") for s in quality_report.SECTIONS]
        assert positions == sorted(positions)

    def test_should_mark_missing_fragment_of_failed_job_as_failed(self) -> None:
        fragments = all_ok_fragments()
        del fragments[Analysis.MYPY]

        report = render(fragments, {"types": "failure"})

        assert "❌ **Failed**: 1 analysis failed" in report
        assert "Job `types` ended as `failure` without producing a result" in report

    @pytest.mark.parametrize("result", ["cancelled", "skipped"])
    def test_should_mark_missing_fragment_of_cancelled_job_as_skipped(self, result: str) -> None:
        fragments = all_ok_fragments()
        del fragments[Analysis.SMOKE]

        report = render(fragments, {"smoke": result})

        assert "| Boot smoke (/health and /ready) | ⏭️ |" in report
        assert "✅ **All good** (1 analysis not run)" in report

    def test_should_take_the_worst_status_in_multi_analysis_sections(self) -> None:
        fragments = all_ok_fragments()
        fragments[Analysis.PIP_AUDIT] = fragment(
            Analysis.PIP_AUDIT, "Found 2 known vulnerabilities", 1
        )

        report = render(fragments, {})

        assert "### ❌ Security (bandit + pip-audit)" in report
        assert "- ✅ **bandit**: No security issues" in report
        assert "- ❌ **pip-audit**: 2 vulnerabilities" in report

    def test_should_wrap_long_output_in_collapsible_details(self) -> None:
        fragments = all_ok_fragments()
        fragments[Analysis.MYPY] = fragment(Analysis.MYPY, "x" * 20000, 1)

        report = render(fragments, {})

        assert "<details><summary>Output</summary>" in report
        assert "[...truncado...]" in report
        assert len(report) < 30000

    def test_should_not_let_output_break_the_code_fence(self) -> None:
        fragments = all_ok_fragments()
        fragments[Analysis.MYPY] = fragment(Analysis.MYPY, "```\nevil", 1)

        assert "```\nevil" not in render(fragments, {})

    def test_should_add_footer(self) -> None:
        assert render(all_ok_fragments(), {}, "commit `abc`").endswith("---\ncommit `abc`\n")


class TestRunCommand:
    def test_should_store_fragment_and_keep_exit_code(self, tmp_path: Path) -> None:
        code = quality_report.run_command(
            Analysis.XENON, ["bash", "-c", "echo out; exit 3"], tmp_path, is_advisory=False
        )

        stored = Fragment.read(tmp_path / "xenon.json")
        assert code == 3
        assert stored.exit_code == 3
        assert stored.output == "out\n"

    def test_should_keep_real_exit_code_in_fragment_but_not_block_when_advisory(
        self, tmp_path: Path
    ) -> None:
        code = quality_report.run_command(
            Analysis.VULTURE, ["bash", "-c", "exit 3"], tmp_path, is_advisory=True
        )

        assert code == 0
        assert Fragment.read(tmp_path / "vulture.json").exit_code == 3

    def test_should_fail_with_127_when_command_does_not_exist(self, tmp_path: Path) -> None:
        code = quality_report.run_command(
            Analysis.MYPY, ["no-such-binary-xyz"], tmp_path, is_advisory=False
        )

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

    def test_should_build_footer_from_github_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for variable in ("GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITHUB_SHA", "QUALITY_REPORT_SHA"):
            monkeypatch.delenv(variable, raising=False)
        assert quality_report.footer_from_environment() == ""
        monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
        monkeypatch.setenv("GITHUB_RUN_ID", "42")
        monkeypatch.setenv("GITHUB_SHA", "abcdef0123")

        footer = quality_report.footer_from_environment()

        assert footer == "commit `abcdef0` · [CI run](https://github.com/o/r/actions/runs/42)"


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
        assert "No type errors (3 files)" in output.read_text()

    def test_should_propagate_command_exit_code(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "sys.argv",
            ["quality_report", "run", "mypy", "--dir", str(tmp_path), "--", "bash", "-c", "exit 5"],
        )

        assert quality_report.main() == 5


class TestWiring:
    def test_should_have_every_section_job_in_the_needs_of_the_report(self) -> None:
        ci = Path(".github/workflows/ci.yml").read_text()
        needs = re.search(r"^    needs: \[(?P<jobs>[^\]]+)\]$", ci, re.MULTILINE)

        assert needs is not None
        jobs = {job.strip() for job in needs["jobs"].split(",")}
        assert {section.job for section in quality_report.SECTIONS} <= jobs

    def test_should_upload_a_fragment_from_every_section_job(self) -> None:
        workflows = "".join(path.read_text() for path in Path(".github/workflows").glob("*.yml"))

        for section in quality_report.SECTIONS:
            assert f"name: quality-fragment-{section.job}" in workflows

    @pytest.mark.parametrize(
        ("script", "label"),
        [("scripts/smoke.sh", "smoke"), ("scripts/contract.sh", quality_report.CONTRACT_LABEL)],
    )
    def test_should_share_the_label_of_the_messages_with_the_boot_scripts(
        self, script: str, label: str
    ) -> None:
        assert f"\nAPI_LABEL={label}\n" in Path(script).read_text()
