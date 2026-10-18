from collections.abc import Iterator
from pathlib import Path
import ast, itertools, re, tokenize

ROOT       = Path(__file__).resolve().parents[1]
SOURCE     = ROOT / "src"
SCANNED    = ("src", "tests", "benches")
PARTS      = ("core", "app", "config", "routes", "bootstrap", "database")
ALLOWED    = {
    "core"      : {"core"},
    "config"    : {"core", "app"},
    "app"       : {"core", "app"},
    "database"  : {"core", "app"},
    "routes"    : {"core", "app"},
    "bootstrap" : set(PARTS),
}
MAIN       = 'if __name__ == "__main__":'
LONGEST    = 300
STDLIB     = frozenset({
    "datetime", "uuid", "pathlib", "decimal", "json", "orjson", "asyncio", "os", "re", "hashlib", "base64", "secrets",
    "random", "time",
})
SQL        = re.compile(r"\b(create|alter|drop|select|insert|update|delete|truncate)\b\s+\w", re.IGNORECASE)
RAW_CALLS  = frozenset({"script", "execute", "fetch", "sql", "text", "run_sync"})

def python_files ( *folders: str ) -> Iterator[Path]:

    for folder in folders:

        for path in sorted((ROOT / folder).rglob("*.py")):

            if "__pycache__" not in path.parts: yield path

def part_of ( path: Path ) -> str:
    return path.relative_to(SOURCE).parts[0]

def domains () -> list[Path]:

    entries = (SOURCE / "core").iterdir()

    return sorted(entry for entry in entries if entry.is_dir() and not entry.name.startswith("_"))

def assigned ( tree: ast.Module ) -> set[str]:

    statements = [node for node in tree.body if isinstance(node, ast.Assign)]

    return { getattr(target, "id", "") for node in statements for target in node.targets }

def imported_roots ( tree: ast.AST ) -> set[str]:

    roots: set[str] = set()

    for node in ast.walk(tree):

        if isinstance(node, ast.Import): roots.update(alias.name.split(".")[0] for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module: roots.add(node.module.split(".")[0])

    return roots

def core_domains_used ( tree: ast.AST ) -> set[str]:

    used: set[str] = set()

    for node in ast.walk(tree):

        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and node.module.startswith("core."):
            used.add(node.module.split(".")[1])

    return used

def cycle_in ( graph: dict[str, set[str]] ) -> list[str]:

    state: dict[str, int] = {}
    trail: list[str] = []

    def visit ( node: str ) -> list[str]:

        if state.get(node) == 1: return [*trail[trail.index(node):], node]
        if state.get(node) == 2: return []

        state[node] = 1
        trail.append(node)

        for child in sorted(graph.get(node, ())):

            found = visit(child)

            if found: return found

        trail.pop()
        state[node] = 2

        return []

    for start in sorted(graph):

        found = visit(start)

        if found: return found

    return []

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

        assert offenses == []

    def test_core_files_stay_flat_and_short ( self ) -> None:

        long = [
            f"{path.relative_to(ROOT)} has {count} lines"
            for path in python_files("src/core")
            if (count := len(path.read_text().split("\n"))) > LONGEST + 1
        ]
        deep = [
            str(path.relative_to(ROOT)) for path in python_files("src/core") if len(path.relative_to(SOURCE).parts) > 3
        ]

        assert long == []
        assert deep == []

    def test_parts_import_in_one_direction_and_core_domains_form_a_dag ( self ) -> None:

        offenses: list[str] = []
        graph: dict[str, set[str]] = {}

        for path in python_files("src"):

            part = part_of(path)
            tree = ast.parse(path.read_text())
            used = imported_roots(tree) & set(PARTS)

            offenses.extend(f"{path.relative_to(ROOT)} imports {name}" for name in sorted(used - ALLOWED[part]))

            if part != "core":

                leaked = sorted(imported_roots(tree) & STDLIB)

                offenses.extend(f"{path.relative_to(ROOT)} uses stdlib {name}" for name in leaked)

            if part == "core" and len(path.relative_to(SOURCE).parts) > 2:

                domain = path.relative_to(SOURCE).parts[1]

                graph.setdefault(domain, set()).update(core_domains_used(tree) - {domain})

        assert offenses == []
        assert cycle_in(graph) == []
        assert sorted(graph) == [folder.name for folder in domains()]

    def test_migrations_speak_only_the_schema_dsl ( self ) -> None:

        folder   = SOURCE / "database" / "migrations"
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

        assert len(files) >= 4
        assert offenses == []

    def test_core_domains_export_a_facade_and_the_root_imports_every_domain ( self ) -> None:

        folders = domains()
        root    = ast.parse((SOURCE / "core" / "__init__.py").read_text())
        local   = [node for node in root.body if isinstance(node, ast.ImportFrom) and node.level == 1]
        wired   = { alias.name for node in local for alias in node.names }
        missing = [
            folder.name for folder in folders
            if "__all__" not in assigned(ast.parse((folder / "__init__.py").read_text()))
        ]

        assert missing == []
        assert wired == { folder.name for folder in folders }
