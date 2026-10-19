from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1] / "src" / "core"

def test_new_domains_keep_technical_ownership_and_acyclic_imports () -> None:

    edges: dict[str, set[str]] = {}
    for path in ROOT.glob("*/*.py"):
        domain = path.parent.name
        edges.setdefault(domain, set())
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            module = node.module if isinstance(node, ast.ImportFrom) else ""
            if module and module.startswith("core."):
                target = module.split(".")[1]
                if target != domain: edges[domain].add(target)
            if domain in ("rag", "llm"):
                imports = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [module or ""]
                assert not any(item.split(".")[0] in {"httpx", "requests", "urllib", "re", "subprocess", "os"}
                               for item in imports), path
            if domain == "rag":
                assert not any(isinstance(item, (ast.Import, ast.ImportFrom)) and
                               getattr(item, "module", "") in {"numpy", "pypdf", "regex"}
                               for item in ast.walk(tree)), path

    def visit ( domain: str, stack: frozenset[str] ) -> None:

        assert domain not in stack, f"Domain cycle: {stack} -> {domain}"
        for target in edges.get(domain, set()): visit(target, stack | {domain})

    for domain in ("rag", "llm"): visit(domain, frozenset())

def test_new_core_domains_are_flat_small_and_have_no_docstrings () -> None:

    for domain in ("rag", "llm"):
        for path in (ROOT / domain).glob("*.py"):
            source = path.read_text()
            assert len(source.splitlines()) <= 300, path
            tree = ast.parse(source)
            assert ast.get_docstring(tree) is None
            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    assert ast.get_docstring(node) is None, path
