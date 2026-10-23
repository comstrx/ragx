from collections.abc import Iterator
from pathlib import Path

from engine.test import expect
import ast, builtins, importlib, inspect, itertools, sys, tokenize, typing

ROOT       = Path(__file__).resolve().parents[1]
SOURCE     = ROOT / "src"
SCANNED    = ("src", "tests", "benches")
MAIN       = 'if __name__ == "__main__":'
LONGEST    = 300
SHORTEST   = 100
TOOLS      = frozenset({"pytest"})
PRODUCT    = frozenset({"app", "bootstrap", "config", "database", "routes", "views"})
PROOFS     = { "test_contracts.py": frozenset({"jsonschema", "yaml"}) }
BUILTINS   = frozenset(name for name in dir(builtins) if isinstance(getattr(builtins, name), type)
    and issubclass(getattr(builtins, name), BaseException))
PROTOCOL   = { "src/json/engine/json/json.py": {"TypeError"} }
RAW        = { "database": "sqlalchemy" }
TYPES      = frozenset({"list", "dict", "set", "str", "int", "float", "bool", "bytes", "tuple", "type", "frozenset"})

def python_files ( *folders: str ) -> Iterator[Path]:

    for folder in folders:

        for path in sorted((ROOT / folder).rglob("*.py")):

            if "__pycache__" not in path.parts: yield path

def domains () -> list[Path]:

    members = (entry for entry in SOURCE.iterdir() if entry.is_dir() and not entry.name.startswith("_"))

    return sorted(member / "engine" / member.name for member in members)

def engine_files () -> Iterator[Path]:

    for folder in domains():

        for path in sorted(folder.rglob("*.py")):

            if "__pycache__" not in path.parts: yield path

def assigned ( tree: ast.Module ) -> set[str]:

    statements = [node for node in tree.body if isinstance(node, ast.Assign)]

    return { getattr(target, "id", "") for node in statements for target in node.targets }

def tight_bodies ( path: Path ) -> Iterator[int]:

    lines = path.read_text().split("\n")

    for node in ast.walk(ast.parse("\n".join(lines))):

        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef): continue

        first = node.body[0]
        start = min([first.lineno, *(item.lineno for item in getattr(first, "decorator_list", []))])

        inline = lines[start - 1][:first.col_offset].strip() != ""

        if start > node.lineno and not inline and lines[start - 2].strip() != "": yield start

def owned ( value: object ) -> bool:

    if typing.get_origin(value) is typing.Annotated:

        base, *meta = typing.get_args(value)

        return owned(base) and all(owned(type(item)) for item in meta)

    origin = getattr(value, "__module__", None) if isinstance(value, type) or callable(value) else None
    module = str(origin or type(value).__module__).split(".")[0]

    return module == "engine" or module in sys.stdlib_module_names

def foreign ( hint: object ) -> set[str]:

    if isinstance(hint, typing.TypeAliasType): return foreign(hint.__value__)

    found  = { str(arg) for arg in typing.get_args(hint) for arg in foreign(arg) }
    origin = typing.get_origin(hint) or hint
    module = str(getattr(origin, "__module__", "builtins"))

    if isinstance(origin, type) and module.partition(".")[0] not in ("engine", *sys.stdlib_module_names):
        found.add(f"{module}.{origin.__qualname__}")

    return found

def leaked_signatures () -> list[str]:

    found: list[str] = []

    for folder in domains():

        facade = importlib.import_module(f"engine.{folder.name}")
        owned  = RAW.get(folder.name, "")

        for name in facade.__all__:

            value = getattr(facade, name)
            kind  = value if isinstance(value, type) else type(value)

            if not kind.__module__.startswith("engine."): continue

            for verb, member in inspect.getmembers(kind, callable):

                if verb.startswith("_") or not str(getattr(member, "__module__", "")).startswith("engine."): continue

                hints  = typing.get_type_hints(member, include_extras=True)
                alien  = { library for hint in hints.values() for library in foreign(hint) }
                alien  = { library for library in alien if not (owned and library.startswith(owned)) }

                named = f"engine.{folder.name}.{kind.__name__}.{verb}"

                found.extend(f"{named} speaks {library}" for library in sorted(alien))

    return found

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

def leaked_exports () -> list[str]:

    found: list[str] = []

    for folder in domains():

        facade = importlib.import_module(f"engine.{folder.name}")

        found.extend(f"engine.{folder.name}.{name}" for name in facade.__all__ if not owned(getattr(facade, name)))

    return found

def raised_builtins ( tree: ast.AST ) -> list[tuple[int, str]]:

    found: list[tuple[int, str]] = []

    for node in ast.walk(tree):

        if not isinstance(node, ast.Raise) or node.exc is None: continue

        target = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        name   = target.id if isinstance(target, ast.Name) else ""

        if name in BUILTINS: found.append((node.lineno, name))

    return found

def imported_roots ( tree: ast.AST ) -> set[str]:

    roots: set[str] = set()

    for node in ast.walk(tree):

        if isinstance(node, ast.Import): roots.update(alias.name.split(".")[0] for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module: roots.add(node.module.split(".")[0])

    return roots

def domains_used ( tree: ast.AST ) -> set[str]:

    used: set[str] = set()

    for node in ast.walk(tree):

        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and node.module.startswith("engine."):
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

        expect(offenses).equals([])

    def test_every_definition_opens_with_a_blank_line ( self ) -> None:

        files    = python_files(*SCANNED)
        offenses = [f"{path.relative_to(ROOT)}:{line}" for path in files for line in tight_bodies(path)]

        expect(offenses).equals([])

    def test_the_engine_raises_only_faults ( self ) -> None:

        offenses: list[str] = []

        for path in engine_files():

            label   = str(path.relative_to(ROOT))
            allowed = PROTOCOL.get(label, set())

            offenses.extend(
                f"{label}:{line} raises {name}" for line, name in raised_builtins(ast.parse(path.read_text()))
                if name not in allowed
            )

        expect(offenses).equals([])

    def test_engine_files_stay_flat_and_between_one_and_three_hundred_lines ( self ) -> None:

        files = [path for path in engine_files() if path.name != "__init__.py"]
        sized = [(path, len(path.read_text().rstrip("\n").split("\n"))) for path in files]
        long  = [f"{path.relative_to(ROOT)} has {count} lines" for path, count in sized if count > LONGEST]
        short = [f"{path.relative_to(ROOT)} has {count} lines" for path, count in sized if count < SHORTEST]
        nests = [(folder, path) for folder in domains() for path in folder.rglob("*.py")]
        deep  = [str(path.relative_to(ROOT)) for folder, path in nests if path.parent != folder]

        expect(long).equals([])
        expect(short).equals([])
        expect(deep).equals([])

    def test_engine_domains_form_a_dag_and_reach_no_product ( self ) -> None:

        offenses: list[str] = []
        graph: dict[str, set[str]] = {}

        for path in engine_files():

            tree    = ast.parse(path.read_text())
            domain  = path.relative_to(SOURCE).parts[0]
            reached = sorted(imported_roots(tree) & PRODUCT)

            offenses.extend(f"{path.relative_to(ROOT)} reaches {name}" for name in reached)
            graph.setdefault(domain, set()).update(domains_used(tree) - {domain})

        expect(offenses).equals([])
        expect(cycle_in(graph)).equals([])
        expect(sorted(graph)).equals([folder.name for folder in domains()])

    def test_test_files_keep_unique_names_so_no_suite_shadows_another ( self ) -> None:

        names = [path.name for path in (ROOT / "tests").rglob("test_*.py")]

        expect(sorted(name for name in set(names) if names.count(name) > 1)).equals([])

    def test_tests_and_benches_touch_only_the_engine_and_their_tools ( self ) -> None:

        files   = [(path, imported_roots(ast.parse(path.read_text()))) for path in python_files("tests", "benches")]
        known   = {*sys.stdlib_module_names, "engine", "benches", *TOOLS}
        foreign = [
            f"{path.relative_to(ROOT)} imports {name}"
            for path, roots in files for name in sorted(roots - known - PROOFS.get(path.name, frozenset()))
        ]

        expect(foreign).equals([])

    def test_engine_facades_export_only_names_the_engine_or_the_stdlib_defines ( self ) -> None:

        expect(leaked_exports()).equals([])

    def test_a_verb_named_like_a_builtin_never_hides_that_builtin_from_its_own_class ( self ) -> None:

        found = [
            f"{path.relative_to(ROOT)}:{line} annotates {name} under a {name} verb"
            for path in python_files("src") for line, name in shadowed(ast.parse(path.read_text()))
        ]

        expect(found).equals([])

    def test_public_engine_verbs_speak_no_library_type_but_the_declared_raw_one ( self ) -> None:

        expect(leaked_signatures()).equals([])

    def test_every_domain_exports_a_typed_facade_inside_the_shared_namespace ( self ) -> None:

        folders  = domains()
        missing  = [
            folder.name for folder in folders
            if "__all__" not in assigned(ast.parse((folder / "__init__.py").read_text()))
        ]
        untyped  = [folder.name for folder in folders if not (folder / "py.typed").is_file()]
        claimed  = [folder.name for folder in folders if (folder.parent / "__init__.py").exists()]

        expect(missing).equals([])
        expect(untyped).equals([])
        expect(claimed).equals([])
