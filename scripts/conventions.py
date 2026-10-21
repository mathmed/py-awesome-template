import argparse
import ast
import io
import json
import re
import sys
import tokenize
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

DEFAULT_ROOTS = (Path("app"), Path("scripts"), Path("tests"))
RESULT_PREFIX = "CONVENTIONS_RESULT: "
MAX_MODULE_LINES = 400
MAX_FUNCTION_LINES = 50
MAX_CLASS_LINES = 250
MAX_PUBLIC_METHODS = 20
BOOL_PREFIXES = ("is_", "has_", "should_", "can_")
TEST_PREFIX = "test_"
TEST_NAME_PREFIX = "test_should_"
FIXTURE = "fixture"
SHEBANG = "#!"
COMMENT_MARKS = ("Constraint:", "Pitfall:", "Tradeoff:")
CONSTANT_NAME = re.compile(r"^_?[A-Z][A-Z0-9_]*$")
DIRECTIVE_PATTERNS = (
    re.compile(r"\bnoqa\b", re.IGNORECASE),
    re.compile(r"\btype:\s*ignore\b"),
    re.compile(r"\bnosec\b", re.IGNORECASE),
    re.compile(r"\bpragma:\s*no\s*(?:cover|branch)\b", re.IGNORECASE),
    re.compile(r"\bpragma:\s*no\s*mutate\b", re.IGNORECASE),
    re.compile(r"\bpylint:\s*disable", re.IGNORECASE),
    re.compile(r"\bmypy:"),
    re.compile(r"\bpyright:"),
    re.compile(r"\b(?:fmt|isort|yapf):\s*(?:off|skip|skip_file|disable)\b"),
    re.compile(r"\b(?:fmt|isort|yapf):\s*on\b"),
)
MUTABLE_LITERALS = (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)
FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)
DOCUMENTED_NODES = (ast.Module, ast.ClassDef, *FUNCTION_NODES)


class Kind(StrEnum):
    PRIVATE_CLASS = "private-class"
    UNMARKED_COMMENT = "unmarked-comment"
    DOCSTRING = "docstring"
    LONG_MODULE = "long-module"
    LONG_FUNCTION = "long-function"
    LONG_CLASS = "long-class"
    PUBLIC_METHODS = "public-methods"
    BOOL_NAME = "bool-name"
    FILE_ORDER = "file-order"
    MUTABLE_CONSTANT = "mutable-constant"
    TEST_NAME = "test-name"


class Scope(StrEnum):
    APP = "app"
    SCRIPTS = "scripts"
    TESTS = "tests"


@dataclass(frozen=True)
class Comment:
    line: int
    text: str
    is_inline: bool


@dataclass(frozen=True)
class Finding:
    line: int
    kind: Kind
    count: int = 1


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    kind: Kind
    count: int = 1

    def describe(self) -> str:
        excess = f" ({self.count} over the limit)" if self.count > 1 else ""
        return f"  {self.path}:{self.line}: {self.kind}{excess}"


EVERYWHERE = frozenset(Scope)
KIND_SCOPES: Mapping[Kind, frozenset[Scope]] = MappingProxyType(
    {
        Kind.PRIVATE_CLASS: EVERYWHERE,
        Kind.UNMARKED_COMMENT: EVERYWHERE,
        Kind.DOCSTRING: EVERYWHERE,
        Kind.LONG_MODULE: frozenset({Scope.APP}),
        Kind.LONG_FUNCTION: frozenset({Scope.APP}),
        Kind.LONG_CLASS: frozenset({Scope.APP}),
        Kind.PUBLIC_METHODS: frozenset({Scope.APP, Scope.SCRIPTS}),
        Kind.BOOL_NAME: frozenset({Scope.APP, Scope.SCRIPTS}),
        Kind.FILE_ORDER: frozenset({Scope.APP}),
        Kind.MUTABLE_CONSTANT: frozenset({Scope.APP}),
        Kind.TEST_NAME: frozenset({Scope.TESTS}),
    }
)


def scan_source(path: str, source: str) -> list[Violation]:
    tree = ast.parse(source, filename=path)
    kinds = kinds_in_scope(Scope(Path(path).parts[0]))
    found = sorted(
        (finding for finding in findings(source, tree) if finding.kind in kinds),
        key=lambda finding: (finding.line, finding.kind),
    )
    return [Violation(path, finding.line, finding.kind, finding.count) for finding in found]


def scan(roots: Iterable[Path]) -> tuple[Violation, ...]:
    violations: list[Violation] = []
    for root in roots:
        if not root.is_dir():
            raise FileNotFoundError(f"scan root not found: {root}")
        for file in sorted(root.rglob("*.py")):
            path = (Path(root.name) / file.relative_to(root)).as_posix()
            violations += scan_source(path, file.read_text(encoding="utf-8"))
    return tuple(violations)


def check(roots: Iterable[Path]) -> int:
    violations = scan(roots)
    print_report(violations)
    print(result_line(violations))
    if violations:
        return 1
    print("No convention violations.")
    return 0


def print_report(violations: tuple[Violation, ...]) -> None:
    print(f"Convention violations: {len(violations)}")
    for violation in violations:
        print(violation.describe())


def result_line(violations: tuple[Violation, ...]) -> str:
    totals = Counter(violation.kind.value for violation in violations)
    return RESULT_PREFIX + json.dumps(
        {
            "total": len(violations),
            "totals": dict(sorted(totals.items())),
            "violations": [
                {
                    "path": violation.path,
                    "line": violation.line,
                    "kind": violation.kind.value,
                    "count": violation.count,
                }
                for violation in violations
            ],
        }
    )


def kinds_in_scope(scope: Scope) -> frozenset[Kind]:
    return frozenset(kind for kind, scopes in KIND_SCOPES.items() if scope in scopes)


def findings(source: str, tree: ast.Module) -> Iterator[Finding]:
    yield from private_classes(tree)
    yield from unmarked_comments(source)
    yield from docstrings(tree)
    yield from long_module(source)
    yield from long_definitions(tree)
    yield from crowded_classes(tree)
    yield from bool_names(tree)
    yield from file_order(tree)
    yield from mutable_constants(tree)
    yield from misnamed_tests(tree)


def private_classes(tree: ast.Module) -> Iterator[Finding]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name.startswith("_"):
            yield Finding(node.lineno, Kind.PRIVATE_CLASS)


def unmarked_comments(source: str) -> Iterator[Finding]:
    previous_line: int | None = None
    for comment in prose_comments(source):
        is_block_start = (
            comment.is_inline or previous_line is None or comment.line != previous_line + 1
        )
        if is_block_start and not is_marked(comment.text):
            yield Finding(comment.line, Kind.UNMARKED_COMMENT)
        previous_line = None if comment.is_inline else comment.line


def prose_comments(source: str) -> Iterator[Comment]:
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT and is_prose(token):
            is_inline = bool(token.line[: token.start[1]].strip())
            yield Comment(line=token.start[0], text=token.string, is_inline=is_inline)


def is_marked(comment: str) -> bool:
    return comment.lstrip("#").strip().startswith(COMMENT_MARKS)


def is_prose(token: tokenize.TokenInfo) -> bool:
    if token.start == (1, 0) and token.string.startswith(SHEBANG):
        return False
    return not any(pattern.search(token.string) for pattern in DIRECTIVE_PATTERNS)


def docstrings(tree: ast.Module) -> Iterator[Finding]:
    for node in ast.walk(tree):
        if isinstance(node, DOCUMENTED_NODES) and ast.get_docstring(node) is not None:
            yield Finding(node.body[0].lineno, Kind.DOCSTRING)


def long_module(source: str) -> Iterator[Finding]:
    excess = len(source.splitlines()) - MAX_MODULE_LINES
    if excess > 0:
        yield Finding(MAX_MODULE_LINES + 1, Kind.LONG_MODULE, excess)


def long_definitions(node: ast.AST, *, is_in_class: bool = False) -> Iterator[Finding]:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, FUNCTION_NODES):
            yield from over_limit(child, Kind.LONG_FUNCTION, MAX_FUNCTION_LINES)
        elif isinstance(child, ast.ClassDef):
            if not is_in_class:
                yield from over_limit(child, Kind.LONG_CLASS, MAX_CLASS_LINES)
            yield from long_definitions(child, is_in_class=True)
        else:
            yield from long_definitions(child, is_in_class=is_in_class)


def over_limit(node: ast.stmt, kind: Kind, limit: int) -> Iterator[Finding]:
    excess = (node.end_lineno or node.lineno) - node.lineno + 1 - limit
    if excess > 0:
        yield Finding(node.lineno, kind, excess)


def crowded_classes(tree: ast.Module) -> Iterator[Finding]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        methods = [child for child in node.body if isinstance(child, FUNCTION_NODES)]
        excess = sum(not method.name.startswith("_") for method in methods) - MAX_PUBLIC_METHODS
        if excess > 0:
            yield Finding(node.lineno, Kind.PUBLIC_METHODS, excess)


def bool_names(tree: ast.Module) -> Iterator[Finding]:
    for node in ast.walk(tree):
        if isinstance(node, FUNCTION_NODES):
            yield from function_bool_names(node)
        elif isinstance(node, ast.ClassDef):
            yield from field_bool_names(node)


def function_bool_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterator[Finding]:
    if is_bool(node.returns) and not is_dunder(node.name) and not is_prefixed(node.name):
        yield Finding(node.lineno, Kind.BOOL_NAME)
    arguments = (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
    for argument in arguments:
        if is_bool(argument.annotation) and not is_prefixed(argument.arg):
            yield Finding(argument.lineno, Kind.BOOL_NAME)


def field_bool_names(node: ast.ClassDef) -> Iterator[Finding]:
    for statement in node.body:
        if not isinstance(statement, ast.AnnAssign) or not isinstance(statement.target, ast.Name):
            continue
        if is_bool(statement.annotation) and not is_prefixed(statement.target.id):
            yield Finding(statement.lineno, Kind.BOOL_NAME)


def is_bool(annotation: ast.expr | None) -> bool:
    if isinstance(annotation, ast.Name):
        return annotation.id == "bool"
    return isinstance(annotation, ast.Constant) and annotation.value == "bool"


def is_prefixed(name: str) -> bool:
    return name.lstrip("_").startswith(BOOL_PREFIXES)


def is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def file_order(tree: ast.Module) -> Iterator[Finding]:
    functions: set[str] = set()
    has_private_function = False
    for statement in tree.body:
        if isinstance(statement, FUNCTION_NODES):
            is_private = statement.name.startswith("_")
            if has_private_function and not is_private:
                yield Finding(statement.lineno, Kind.FILE_ORDER)
            functions.add(statement.name)
            has_private_function = has_private_function or is_private
        elif isinstance(statement, ast.ClassDef):
            if functions:
                yield Finding(statement.lineno, Kind.FILE_ORDER)
        elif is_misplaced_constant(statement, functions):
            yield Finding(statement.lineno, Kind.FILE_ORDER)


def is_misplaced_constant(statement: ast.stmt, functions: set[str]) -> bool:
    if not functions or not constant_names(statement):
        return False
    names = {node.id for node in ast.walk(statement) if isinstance(node, ast.Name)}
    return not names & functions


def mutable_constants(tree: ast.Module) -> Iterator[Finding]:
    for statement in tree.body:
        if not isinstance(statement, ast.Assign | ast.AnnAssign) or not constant_names(statement):
            continue
        if isinstance(statement.value, MUTABLE_LITERALS):
            yield Finding(statement.lineno, Kind.MUTABLE_CONSTANT)


def constant_names(statement: ast.stmt) -> tuple[str, ...]:
    if isinstance(statement, ast.Assign):
        targets = statement.targets
    elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
        targets = [statement.target]
    else:
        return ()
    names = (target.id for target in targets if isinstance(target, ast.Name))
    return tuple(name for name in names if CONSTANT_NAME.match(name))


def misnamed_tests(tree: ast.Module) -> Iterator[Finding]:
    for node in ast.walk(tree):
        if not isinstance(node, FUNCTION_NODES) or not node.name.startswith(TEST_PREFIX):
            continue
        if not node.name.startswith(TEST_NAME_PREFIX) and not is_fixture(node):
            yield Finding(node.lineno, Kind.TEST_NAME)


def is_fixture(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(decorator_name(decorator) == FIXTURE for decorator in node.decorator_list)


def decorator_name(node: ast.expr) -> str:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Attribute):
        return target.attr
    return target.id if isinstance(target, ast.Name) else ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, action="append", dest="roots")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return check(args.roots or DEFAULT_ROOTS)


if __name__ == "__main__":
    sys.exit(main())
