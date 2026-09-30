import json
from pathlib import Path

import pytest

from scripts import quality_report
from scripts.quality_report import (
    Analysis,
    Fragment,
    Status,
    analyze_bandit,
    analyze_import_linter,
    analyze_mutation,
    analyze_pytest,
    analyze_smoke,
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


def fragment(analysis: Analysis, output: str = "", exit_code: int = 0) -> Fragment:
    return Fragment(analysis, exit_code, output)


def all_ok_fragments() -> dict[Analysis, Fragment]:
    outputs = {
        Analysis.PYTEST: PYTEST_OK,
        Analysis.IMPORT_LINTER: IMPORT_LINTER_OK,
        Analysis.SMOKE: SMOKE_OK,
        Analysis.MUTATION: mutation_output(100.0, []),
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


class TestAdvisoryTools:
    def test_should_warn_on_dead_code_when_advisory(self) -> None:
        advisory = Fragment(Analysis.VULTURE, 3, "app/a.py:1: unused function 'f'", advisory=True)

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
