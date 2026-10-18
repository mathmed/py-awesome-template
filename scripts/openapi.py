import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

APP_MODULE = "app.main.main"
SCRIPT = Path(__file__).resolve()
BASE_SCHEMA = "base.openapi.json"
HEAD_SCHEMA = "head.openapi.json"
BASE_TREE = "base-tree"
GIT_TIMEOUT_SECONDS = 120
# The base export may install the base branch's dependencies into a fresh environment first
EXPORT_TIMEOUT_SECONDS = 600
OASDIFF_TIMEOUT_SECONDS = 120
OASDIFF_NOT_FOUND = 127


class OpenApiDiffError(Exception):
    pass


def export_schema(app_dir: Path, output: Path) -> None:
    sys.path.insert(0, str(app_dir))
    module = importlib.import_module(APP_MODULE)
    schema: dict[str, object] = module.app.openapi()
    output.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")


def run(command: list[str], *, cwd: Path, timeout: int, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        command, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, check=False
    )
    if result.returncode != 0:
        raise OpenApiDiffError(f"`{' '.join(command)}` failed:\n{result.stdout}{result.stderr}")
    return result.stdout


def merge_base(base_ref: str, repository: Path) -> str:
    command = ["git", "merge-base", base_ref, "HEAD"]
    try:
        return run(command, cwd=repository, timeout=GIT_TIMEOUT_SECONDS).strip()
    except OpenApiDiffError as error:
        message = f"{error}\nIs {base_ref} fetched with the full history (fetch-depth: 0)?"
        raise OpenApiDiffError(message) from error


def project_environment() -> dict[str, str]:
    # Each checkout must use its own project environment, not the one this script runs in
    return {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}


def export_in(checkout: Path, output: Path) -> None:
    command = ["uv", "run", "--locked", "--no-dev", "python", str(SCRIPT), "export"]
    command += ["--output", str(output)]
    run(command, cwd=checkout, timeout=EXPORT_TIMEOUT_SECONDS, env=project_environment())


def export_base(commit: str, repository: Path, output: Path) -> None:
    tree = output.parent / BASE_TREE
    worktree = ["git", "worktree"]
    run(
        [*worktree, "add", "--detach", str(tree), commit],
        cwd=repository,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    try:
        export_in(tree, output)
    finally:
        run(
            [*worktree, "remove", "--force", str(tree)], cwd=repository, timeout=GIT_TIMEOUT_SECONDS
        )


def changelog(oasdiff: str, directory: Path) -> int:
    command = [oasdiff, "changelog", BASE_SCHEMA, HEAD_SCHEMA, "--fail-on", "ERR"]
    command += ["--color", "never", "--allow-external-refs=false"]
    result = subprocess.run(command, cwd=directory, timeout=OASDIFF_TIMEOUT_SECONDS, check=False)
    return result.returncode


def diff_command(base_ref: str, oasdiff: str, repository: Path) -> int:
    if shutil.which(oasdiff) is None:
        print(f"oasdiff not found ({oasdiff}): install it, see the README", file=sys.stderr)
        return OASDIFF_NOT_FOUND
    commit = merge_base(base_ref, repository)
    print(
        f"Comparing the OpenAPI schema of HEAD with {base_ref} (merge base {commit[:12]})",
        flush=True,
    )
    with tempfile.TemporaryDirectory(prefix="openapi-diff-") as temporary:
        directory = Path(temporary)
        export_in(repository, directory / HEAD_SCHEMA)
        export_base(commit, repository, directory / BASE_SCHEMA)
        return changelog(oasdiff, directory)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="write the OpenAPI schema of the app in the cwd")
    export.add_argument("--output", type=Path, required=True)
    diff = commands.add_parser("diff", help="fail on breaking changes against the base branch")
    diff.add_argument("--base", default="origin/main")
    diff.add_argument("--oasdiff", default="oasdiff")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "export":
        export_schema(Path.cwd(), args.output.resolve())
        return 0
    try:
        return diff_command(args.base, args.oasdiff, Path.cwd())
    except OpenApiDiffError as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
