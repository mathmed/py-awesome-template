import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from scripts import openapi
from scripts.openapi import OpenApiDiffError

REPOSITORY = Path("/repo")
COMMIT = "0123456789abcdef"


@pytest.fixture
def isolated_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "path", list(sys.path))


@pytest.mark.usefixtures("isolated_path")
class TestExport:
    def test_should_write_the_schema_of_the_app_in_the_directory(self, tmp_path: Path) -> None:
        output = tmp_path / "schema.json"

        openapi.export_schema(Path.cwd(), output)

        schema = json.loads(output.read_text())
        assert {"/health", "/ready", "/example"} <= set(schema["paths"])
        assert list(schema) == sorted(schema)

    def test_should_export_through_the_command_line(self, tmp_path: Path) -> None:
        output = tmp_path / "schema.json"

        assert openapi.main(["export", "--output", str(output)]) == 0
        assert "/health" in json.loads(output.read_text())["paths"]


class TestRun:
    def test_should_return_the_output_of_a_successful_command(self, tmp_path: Path) -> None:
        assert openapi.run(["bash", "-c", "echo out"], cwd=tmp_path, timeout=10) == "out\n"

    def test_should_raise_with_the_output_when_the_command_fails(self, tmp_path: Path) -> None:
        with pytest.raises(OpenApiDiffError, match="failed:\nout\nerr"):
            openapi.run(["bash", "-c", "echo out; echo err >&2; exit 3"], cwd=tmp_path, timeout=10)

    def test_should_hint_at_the_history_when_the_merge_base_is_missing(
        self, mocker: MockerFixture
    ) -> None:
        mocker.patch.object(openapi, "run", side_effect=OpenApiDiffError("fatal: bad object"))

        with pytest.raises(OpenApiDiffError, match=r"fetch-depth: 0"):
            openapi.merge_base("origin/main", REPOSITORY)

    def test_should_not_leak_the_current_virtual_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("VIRTUAL_ENV", "/somewhere/.venv")
        monkeypatch.setenv("PATH", "/bin")

        environment = openapi.project_environment()

        assert "VIRTUAL_ENV" not in environment
        assert environment["PATH"] == "/bin"


class TestDiff:
    @pytest.fixture
    def run(self, mocker: MockerFixture) -> MagicMock:
        mocker.patch("scripts.openapi.shutil.which", return_value="/usr/bin/oasdiff")
        return mocker.patch.object(openapi, "run", return_value=f"{COMMIT}\n")

    @pytest.fixture
    def oasdiff(self, mocker: MockerFixture) -> MagicMock:
        completed: subprocess.CompletedProcess[str] = subprocess.CompletedProcess([], 1)
        return mocker.patch("scripts.openapi.subprocess.run", return_value=completed)

    def commands(self, run: MagicMock) -> list[list[str]]:
        return [call.args[0] for call in run.call_args_list]

    def test_should_compare_head_with_the_merge_base_and_keep_the_oasdiff_exit_code(
        self, run: MagicMock, oasdiff: MagicMock
    ) -> None:
        code = openapi.diff_command("origin/main", "oasdiff", REPOSITORY)

        commands = self.commands(run)
        assert code == 1
        assert commands[0] == ["git", "merge-base", "origin/main", "HEAD"]
        assert commands[1][-3:] == ["export", "--output", commands[1][-1]]
        assert commands[1][-1].endswith(openapi.HEAD_SCHEMA)
        assert run.call_args_list[1].kwargs["cwd"] == REPOSITORY
        assert commands[2][:4] == ["git", "worktree", "add", "--detach"]
        assert commands[2][-1] == COMMIT
        tree = Path(commands[2][-2])
        assert run.call_args_list[3].kwargs["cwd"] == tree
        assert commands[3][-1].endswith(openapi.BASE_SCHEMA)
        assert commands[4] == ["git", "worktree", "remove", "--force", str(tree)]
        changelog = oasdiff.call_args.args[0]
        assert changelog[:4] == ["oasdiff", "changelog", openapi.BASE_SCHEMA, openapi.HEAD_SCHEMA]
        assert "--fail-on" in changelog
        assert changelog[changelog.index("--fail-on") + 1] == "ERR"
        assert "--allow-external-refs=false" in changelog

    def test_should_remove_the_worktree_when_the_base_export_fails(
        self, run: MagicMock, oasdiff: MagicMock
    ) -> None:
        run.side_effect = [f"{COMMIT}\n", "", "", OpenApiDiffError("base broke"), ""]

        with pytest.raises(OpenApiDiffError, match="base broke"):
            openapi.diff_command("origin/main", "oasdiff", REPOSITORY)

        assert self.commands(run)[-1][:3] == ["git", "worktree", "remove"]
        oasdiff.assert_not_called()

    def test_should_fail_fast_when_oasdiff_is_not_installed(
        self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mocker.patch("scripts.openapi.shutil.which", return_value=None)
        run = mocker.patch.object(openapi, "run")

        assert openapi.diff_command("origin/main", "oasdiff", REPOSITORY) == 127
        assert "oasdiff not found" in capsys.readouterr().err
        run.assert_not_called()

    def test_should_report_diff_errors_and_exit_with_one(
        self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mocker.patch.object(openapi, "diff_command", side_effect=OpenApiDiffError("no base"))

        assert openapi.main(["diff", "--base", "origin/x"]) == 1
        assert "no base" in capsys.readouterr().err
