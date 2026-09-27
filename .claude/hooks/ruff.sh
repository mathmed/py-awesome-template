#!/usr/bin/env bash
# PostToolUse hook: formats Python files edited by Claude Code and reports lint errors ruff
# could not fix back to Claude (exit 2), so the agent fixes them before moving on.
file=$(python3 -c 'import json, sys; print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))')
[[ "$file" == *.py && -f "$file" ]] || exit 0
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

lint=$(uv run --quiet ruff check --fix --quiet "$file" 2>&1)
lint_status=$?
uv run --quiet ruff format --quiet "$file"

if [[ $lint_status -ne 0 ]]; then
  echo "ruff found issues it could not fix automatically in $file:" >&2
  echo "$lint" >&2
  exit 2
fi
