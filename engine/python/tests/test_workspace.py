from collections.abc import Iterator
from pathlib import Path

from engine.test import expect
import ast, importlib.metadata, re, sys, tomllib

ROOT    = Path(__file__).resolve().parents[1]
SOURCE  = ROOT / "src"
PINNED  = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(\[[a-z,]+\])?==[0-9][0-9A-Za-z.+-]*$")
RUNTIME = frozenset({"asyncpg", "python-multipart", "httpx2"})

def manifest ( path: Path ) -> dict[str, object]:

    with path.open("rb") as handle: return tomllib.load(handle)

def project ( path: Path ) -> dict[str, object]:

    found = manifest(path)["project"]

    return found if isinstance(found, dict) else {}

def normalized ( name: str ) -> str:

    return re.sub(r"[-_.]+", "-", name).lower()

def requirement ( text: str ) -> str:

    return normalized(re.split(r"[\[=<>!~ ;]", text, maxsplit=1)[0])

def members () -> list[str]:

    return sorted(entry.name for entry in SOURCE.iterdir() if entry.is_dir() and (entry / "pyproject.toml").is_file())

def requires ( member: str ) -> list[str]:

    found = project(SOURCE / member / "pyproject.toml").get("dependencies", [])

    return [str(item) for item in found] if isinstance(found, list) else []

def imported ( member: str ) -> Iterator[str]:

    for path in sorted((SOURCE / member / "engine" / member).glob("*.py")):

        source = path.read_text().replace("lazy import ", "import ").replace("lazy from ", "from ")

        for node in ast.walk(ast.parse(source)):

            if isinstance(node, ast.Import): yield from (alias.name for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module: yield node.module

def engines ( member: str ) -> set[str]:

    names = (name.split(".") for name in imported(member))

    return { f"engine-{parts[1]}" for parts in names if parts[0] == "engine" and len(parts) > 1 and parts[1] != member }

def libraries ( member: str ) -> set[str]:

    owners = importlib.metadata.packages_distributions()
    roots  = { name.split(".")[0] for name in imported(member) } - {"engine"} - set(sys.stdlib_module_names)

    return { normalized(owners.get(root, [root])[0]) for root in roots }

def engines_declared ( member: str ) -> set[str]:

    return { requirement(item) for item in requires(member) if item.startswith("engine-") }

def requires_of_root () -> list[str]:

    found = project(ROOT / "pyproject.toml").get("dependencies", [])

    return [requirement(str(item)) for item in found] if isinstance(found, list) else []

class TestWorkspace:

    def test_the_facade_is_the_workspace_root_over_every_member_and_nothing_else ( self ) -> None:

        root    = manifest(ROOT / "pyproject.toml")
        tool    = root["tool"]
        uv      = tool.get("uv", {}) if isinstance(tool, dict) else {}
        sources = uv.get("sources", {}) if isinstance(uv, dict) else {}
        named   = [f"engine-{member}" for member in members()]

        mypy    = tool.get("mypy", {}) if isinstance(tool, dict) else {}

        expect(project(ROOT / "pyproject.toml")["name"]).equals("engine")
        expect(str(mypy.get("mypy_path", "")).split(",")).equals([f"src/{member}" for member in members()])
        expect(sorted(requires_of_root())).equals(named)
        expect(uv.get("workspace", {})).equals({ "members": ["src/*"] })
        expect(sources).equals({ name: { "workspace": True } for name in named })

    def test_every_member_is_one_domain_package_on_the_facade_version ( self ) -> None:

        version  = project(ROOT / "pyproject.toml")["version"]
        offenses = [
            member for member in members()
            if project(SOURCE / member / "pyproject.toml").get("name") != f"engine-{member}"
            or project(SOURCE / member / "pyproject.toml").get("version") != version
            or not (SOURCE / member / "engine" / member / "__init__.py").is_file()
        ]

        expect(offenses).equals([])

    def test_every_member_declares_exactly_the_engine_domains_it_imports ( self ) -> None:

        declared = { member: engines_declared(member) for member in members() }
        offenses = [
            f"{member}: declares {sorted(declared[member])} imports {sorted(engines(member))}"
            for member in members() if declared[member] != engines(member)
        ]

        expect(offenses).equals([])

    def test_every_member_pins_exactly_the_libraries_it_imports ( self ) -> None:

        offenses: list[str] = []

        for member in members():

            listed   = [item for item in requires(member) if not item.startswith("engine-")]
            declared = { requirement(item) for item in listed }
            used     = libraries(member)

            offenses.extend(f"{member} imports undeclared {name}" for name in sorted(used - declared))
            offenses.extend(f"{member} declares unused {name}" for name in sorted(declared - used - RUNTIME))
            offenses.extend(f"{member} leaves {item} unpinned" for item in listed if not PINNED.match(item))

        expect(offenses).equals([])
