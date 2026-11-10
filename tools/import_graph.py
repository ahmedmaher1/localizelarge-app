"""Who imports what, from the source (AST), without running anything.

    python tools/import_graph.py                 every third-party package and its importers
    python tools/import_graph.py name [name…]    importers of the named modules or packages

A name matches a local module (``modules/voice_commands.py`` → ``voice_commands``)
or the top-level name of a package (``fitz``, ``PyQt6.QtWebEngineWidgets``).
Imports inside functions and ``try`` blocks are included, with their line.
"""
from __future__ import annotations

import ast
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIRS = ("modules", "localizelarge", "tests", "tools", "scripts")
SKIP_PARTS = {".venv", "__pycache__", "build", "dist"}


def source_files() -> list[Path]:
    files = [p for p in ROOT.glob("*.py")]
    for folder in SOURCE_DIRS:
        files += [p for p in (ROOT / folder).rglob("*.py") if not SKIP_PARTS & set(p.parts)]
    return sorted(files)


def imports_of(path: Path) -> list[tuple[str, int]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as error:
        print(f"!! {path}: {error}", file=sys.stderr)
        return []
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(alias.name, node.lineno) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append((node.module, node.lineno))
            if node.module in ("modules", "localizelarge"):
                found += [(f"{node.module}.{alias.name}", node.lineno) for alias in node.names]
    return found


def build() -> dict[str, list[tuple[str, int]]]:
    """Imported dotted name → [(importing file, line)]."""
    graph: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for path in source_files():
        rel = str(path.relative_to(ROOT))
        for name, line in imports_of(path):
            graph[name].append((rel, line))
    return graph


def matches(imported: str, wanted: str) -> bool:
    parts = imported.split(".")
    if imported == wanted or imported.startswith(wanted + "."):
        return True
    return parts[0] in ("modules", "localizelarge") and len(parts) > 1 and parts[1] == wanted


def main(argv: list[str]) -> int:
    graph = build()
    if argv:
        for wanted in argv:
            hits = sorted({(f, n) for name, users in graph.items() if matches(name, wanted) for f, n in users})
            print(f"{wanted}: {len(hits)} import(s)")
            for file, line in hits:
                print(f"    {file}:{line}")
        return 0
    local = {p.stem for p in (ROOT / "modules").glob("*.py")} | {p.stem for p in ROOT.glob("*.py")}
    stdlib = set(sys.stdlib_module_names)
    packages: dict[str, set[str]] = defaultdict(set)
    for name, users in graph.items():
        top = name.split(".")[0]
        if top in stdlib or top in local or top in ("modules", "localizelarge"):
            continue
        packages[top] |= {file for file, _ in users}
    for top in sorted(packages, key=str.lower):
        files = sorted(packages[top])
        shown = ", ".join(files[:4]) + (f", … (+{len(files) - 4})" if len(files) > 4 else "")
        print(f"{top}: {len(files)} file(s): {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
