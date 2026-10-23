from collections.abc import Iterator
from pathlib import Path

from engine.test import expect
import ast, itertools, re, sys, tokenize

ROOT       = Path(__file__).resolve().parents[1]
LAYERS     = ("app", "config", "routes", "bootstrap", "database")
SCANNED    = (*LAYERS, "tests", "benches")
PARTS      = ("engine", *LAYERS, "tests")
ALLOWED    = {
    "config"    : {"engine", "app"},
    "app"       : {"engine", "app"},
    "database"  : {"engine", "app"},
    "routes"    : {"engine", "app"},
    "bootstrap" : set(PARTS) - {"tests"},
    "tests"     : set(PARTS),
}
MAIN       = 'if __name__ == "__main__":'
STDLIB     = frozenset({
    "datetime", "uuid", "pathlib", "decimal", "json", "orjson", "asyncio", "os", "re", "hashlib", "base64", "secrets",
    "random", "time",
})
UPPER      = frozenset({"collections", "typing", "enum", "dataclasses", "contextlib"})
TOOLS      = frozenset({"pytest"})
SQL        = re.compile(r"\b(create|alter|drop|select|insert|update|delete|truncate)\b\s+\w", re.IGNORECASE)
RAW_CALLS  = frozenset({"script", "execute", "fetch", "sql", "run_sync"})
TYPES      = frozenset({"list", "dict", "set", "str", "int", "float", "bool", "bytes", "tuple", "type", "frozenset"})

def python_files ( *folders: str ) -> Iterator[Path]:

    for folder in folders:

        for path in sorted((ROOT / folder).rglob("*.py")):

            if "__pycache__" not in path.parts: yield path

def part_of ( path: Path ) -> str:

    return path.relative_to(ROOT).parts[0]

def tight_bodies ( path: Path ) -> Iterator[int]:

    lines = path.read_text().split("\n")

    for node in ast.walk(ast.parse("\n".join(lines))):

        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef): continue

        first = node.body[0]
        start = min([first.lineno, *(item.lineno for item in getattr(first, "decorator_list", []))])

        inline = lines[start - 1][:first.col_offset].strip() != ""

        if start > node.lineno and not inline and lines[start - 2].strip() != "": yield start

def shadowed ( tree: ast.AST ) -> Iterator[tuple[int, str]]:

    for kind in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):

        verbs  = { node.name for node in kind.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) }
        clash  = verbs & TYPES
        marks  = [node.annotation for node in kind.body if isinstance(node, ast.AnnAssign)]

        for node in kind.body:

            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef): continue

            given = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs, node.args.vararg, node.args.kwarg]

            marks.extend(arg.annotation for arg in given if arg is not None and arg.annotation is not None)
            marks.extend([node.returns] if node.returns is not None else [])

        for mark in marks:

            names = (name for name in ast.walk(mark) if isinstance(name, ast.Name))

            yield from ((name.lineno, name.id) for name in names if name.id in clash)

def imported_roots ( tree: ast.AST ) -> set[str]:

    roots: set[str] = set()

    for node in ast.walk(tree):

        if isinstance(node, ast.Import): roots.update(alias.name.split(".")[0] for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module: roots.add(node.module.split(".")[0])

    return roots

class TestLaws:

    def test_source_files_keep_the_hand_style ( self ) -> None:

        offenses: list[str] = []

        for path in python_files(*SCANNED):

            label = path.relative_to(ROOT)
            lines = path.read_text().split("\n")

            for number, (previous, current) in enumerate(itertools.pairwise(lines), start=2):

                blank = previous.strip() == "" and current.strip() == ""
                tight = previous.strip() == MAIN and current.strip() != ""

                if blank: offenses.append(f"{label}:{number} double blank")
                if tight: offenses.append(f"{label}:{number} unpadded main")

            with path.open("rb") as handle:

                offenses.extend(
                    f"{label}:{token.start[0]} comment"
                    for token in tokenize.tokenize(handle.readline) if token.type == tokenize.COMMENT
                )

        expect(offenses).equals([])

    def test_every_definition_opens_with_a_blank_line ( self ) -> None:

        files    = python_files(*SCANNED)
        offenses = [f"{path.relative_to(ROOT)}:{line}" for path in files for line in tight_bodies(path)]

        expect(offenses).equals([])

    def test_parts_import_in_one_direction_over_the_engine ( self ) -> None:

        offenses: list[str] = []

        for path in python_files(*LAYERS):

            part    = part_of(path)
            tree    = ast.parse(path.read_text())
            used    = imported_roots(tree) & set(PARTS)
            leaked  = sorted(imported_roots(tree) & STDLIB)
            foreign = sorted(imported_roots(tree) - set(PARTS) - UPPER)

            offenses.extend(f"{path.relative_to(ROOT)} imports {name}" for name in sorted(used - ALLOWED[part]))
            offenses.extend(f"{path.relative_to(ROOT)} uses stdlib {name}" for name in leaked)
            offenses.extend(f"{path.relative_to(ROOT)} imports {name} above the engine" for name in foreign)

        expect(offenses).equals([])

    def test_tests_and_benches_touch_only_the_engine_the_parts_and_their_tools ( self ) -> None:

        files   = [(path, imported_roots(ast.parse(path.read_text()))) for path in python_files("tests", "benches")]
        known   = {*sys.stdlib_module_names, *PARTS, *TOOLS}
        foreign = [
            f"{path.relative_to(ROOT)} imports {name}" for path, roots in files for name in sorted(roots - known)
        ]

        expect(foreign).equals([])

    def test_test_files_keep_unique_names_so_no_suite_shadows_another ( self ) -> None:

        names = [path.name for path in (ROOT / "tests").rglob("test_*.py")]

        expect(sorted(name for name in set(names) if names.count(name) > 1)).equals([])

    def test_migrations_speak_only_the_schema_dsl ( self ) -> None:

        folder   = ROOT / "database" / "migrations"
        files    = [path for path in sorted(folder.glob("*.py")) if not path.name.startswith("_")]
        offenses: list[str] = []

        for path in files:

            tree  = ast.parse(path.read_text())
            label = path.name

            for node in ast.walk(tree):

                if isinstance(node, ast.Constant) and isinstance(node.value, str) and SQL.search(node.value):
                    offenses.append(f"{label} carries sql {node.value!r}")
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in RAW_CALLS:
                    offenses.append(f"{label} calls {node.func.attr}")

            classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Migration"]
            members = classes[0].body if classes else []
            methods = { node.name for node in members if isinstance(node, ast.AsyncFunctionDef) }

            if methods != {"up", "down"}: offenses.append(f"{label} lacks async up/down")
            if not re.match(r"^\d{4}_[a-z0-9_]+\.py$", path.name): offenses.append(f"{label} is not numbered")

        expect(len(files) >= 1).true()
        expect(offenses).equals([])

    def test_a_verb_named_like_a_builtin_never_hides_that_builtin_from_its_own_class ( self ) -> None:

        found = [
            f"{path.relative_to(ROOT)}:{line} annotates {name} under a {name} verb"
            for path in python_files(*LAYERS) for line, name in shadowed(ast.parse(path.read_text()))
        ]

        expect(found).equals([])
