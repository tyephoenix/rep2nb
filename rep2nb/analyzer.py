import ast
from dataclasses import dataclass, field
from pathlib import Path

from .config import ENTRY_POINT_NAMES


@dataclass
class ModuleInfo:
    """Analysis results for a single Python file."""

    path: Path
    module_name: str
    source: str
    local_imports: list[str] = field(default_factory=list)
    external_imports: list[str] = field(default_factory=list)
    defined_names: list[str] = field(default_factory=list)
    has_name_main_guard: bool = False
    is_entry_point: bool = False
    module_docstring: str | None = None


def get_module_name(file_path: Path, repo_path: Path) -> str:
    """Convert a file path to its Python module name relative to the repo."""
    rel = file_path.relative_to(repo_path)
    if rel.name == "__init__.py":
        parts = rel.parent.parts
        if not parts:
            return repo_path.name
        return ".".join(parts)
    return ".".join(rel.with_suffix("").parts)


def get_all_module_names(py_files: list[Path], repo_path: Path) -> set[str]:
    """Build the full set of module names, including parent package prefixes."""
    names: set[str] = set()
    for f in py_files:
        mod = get_module_name(f, repo_path)
        if mod:
            names.add(mod)
            parts = mod.split(".")
            for i in range(1, len(parts)):
                names.add(".".join(parts[:i]))
    return names


def analyze_file(
    file_path: Path,
    repo_path: Path,
    local_module_names: set[str],
) -> ModuleInfo:
    """Parse a Python file and extract import/structure information."""
    source = file_path.read_text(encoding="utf-8")
    module_name = get_module_name(file_path, repo_path)

    info = ModuleInfo(path=file_path, module_name=module_name, source=source)

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return info

    for node in _walk_toplevel_imports(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local_deps = _find_local_deps(alias.name, local_module_names)
                if local_deps:
                    info.local_imports.extend(local_deps)
                else:
                    info.external_imports.append(alias.name.split(".")[0])

        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                is_pkg = file_path.name == "__init__.py"
                resolved = _resolve_relative_import(
                    node.module, node.level, module_name, is_package=is_pkg
                )
                if resolved:
                    local_deps = _find_local_deps(resolved, local_module_names)
                    info.local_imports.extend(local_deps)
            elif node.module:
                local_deps = _find_local_deps(node.module, local_module_names)
                if local_deps:
                    info.local_imports.extend(local_deps)
                else:
                    info.external_imports.append(node.module.split(".")[0])

    # Second pass: walk ALL imports (including inside functions and guards)
    # to catch external deps used anywhere in the file (e.g. torch inside
    # a function body).  Local deps only need the top-level pass above.
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _find_local_deps(alias.name, local_module_names):
                    info.external_imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if not _find_local_deps(node.module, local_module_names):
                info.external_imports.append(node.module.split(".")[0])

    info.module_docstring = ast.get_docstring(tree)

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.If) and _is_name_main_guard(node):
            info.has_name_main_guard = True
            break

    info.local_imports = [
        dep for dep in dict.fromkeys(info.local_imports) if dep != module_name
    ]
    info.external_imports = list(dict.fromkeys(info.external_imports))

    return info


def get_defined_names(source: str) -> list[str]:
    """Extract all names defined at the top level of the given source code."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    names: list[str] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names.extend(_extract_target_names(target))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.append(alias.asname or alias.name)
    return list(dict.fromkeys(names))


def detect_entry_points(
    analyses: dict[str, ModuleInfo],
    entry: list[str] | None,
    repo_path: Path,
) -> list[str]:
    """Determine which modules are entry points.

    *entry* may be a list of relative paths; their order is preserved so
    callers can control execution sequence.

    Returns a list of module names.
    """
    if entry:
        result: list[str] = []
        for e in entry:
            entry_path = (repo_path / e).resolve()
            found = False
            for mod_name, info in analyses.items():
                if info.path.resolve() == entry_path:
                    result.append(mod_name)
                    found = True
                    break
            if not found:
                raise FileNotFoundError(f"Entry point not found: {e}")
        return result

    imported_by_others: set[str] = set()
    for info in analyses.values():
        imported_by_others.update(info.local_imports)

    named = [
        mod_name
        for mod_name, info in analyses.items()
        if info.path.name in ENTRY_POINT_NAMES
        and mod_name not in imported_by_others
    ]
    if named:
        return named

    guarded = [
        mod_name
        for mod_name, info in analyses.items()
        if info.has_name_main_guard
        and mod_name not in imported_by_others
    ]
    return guarded


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _walk_toplevel_imports(tree: ast.Module):
    """Yield Import/ImportFrom nodes at module scope.

    Skips imports inside ``if __name__ == '__main__'`` guards,
    function/class bodies, and other nested scopes so that the
    dependency graph only reflects real import-time relationships.
    """
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.If) and _is_name_main_guard(node):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            yield node
        else:
            for child in ast.walk(node):
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    yield child


def _find_local_deps(import_path: str, local_module_names: set[str]) -> list[str]:
    """Return the most specific local module that matches *import_path*.

    Only the longest matching prefix is returned so that intra-package
    imports don't create false dependencies on parent ``__init__`` files
    (which commonly re-export from submodules and would cause cycles).
    """
    parts = import_path.split(".")
    for i in range(len(parts), 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in local_module_names:
            return [candidate]
    return []


def _resolve_relative_import(
    module: str | None,
    level: int,
    current_module: str,
    is_package: bool = False,
) -> str | None:
    """Resolve a relative import to an absolute module path.

    For ``__init__.py`` (*is_package=True*), ``from .X`` means "from this
    package" so the base is the module name itself.  For regular modules
    the base is the parent package.
    """
    if is_package:
        package = current_module
    else:
        idx = current_module.rfind(".")
        package = current_module[:idx] if idx >= 0 else ""

    parts = package.split(".") if package else []
    go_up = level - 1
    if go_up > len(parts):
        return None
    base_parts = parts[: len(parts) - go_up] if go_up > 0 else parts
    base = ".".join(base_parts)
    if module:
        return f"{base}.{module}" if base else module
    return base or None


def _is_name_main_guard(node: ast.If) -> bool:
    test = node.test
    if not isinstance(test, ast.Compare):
        return False
    if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
        return False
    left, right = test.left, test.comparators[0]
    return (_is_dunder_name(left) and _is_main_string(right)) or (
        _is_main_string(left) and _is_dunder_name(right)
    )


def _is_dunder_name(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id == "__name__"


def _is_main_string(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value == "__main__"


def _extract_target_names(target: ast.expr) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for elt in target.elts:
            names.extend(_extract_target_names(elt))
        return names
    return []
