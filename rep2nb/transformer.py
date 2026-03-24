import ast
import textwrap

from .analyzer import ModuleInfo, get_defined_names


def transform_module(info: ModuleInfo) -> str:
    """Transform a dependency module: strip __name__ guard, add registration."""
    source = info.source

    if info.module_docstring:
        source = _strip_module_docstring(source)

    if info.has_name_main_guard:
        source = _remove_name_main_guard(source)

    is_pkg = info.path.name == "__init__.py"
    source = _rewrite_relative_imports(source, info.module_name, is_package=is_pkg)

    defined = get_defined_names(source)
    registration = _generate_module_registration(info.module_name, defined)

    return source.rstrip("\n") + "\n\n" + registration + "\n"


def transform_entry_point(info: ModuleInfo) -> str:
    """Transform an entry-point module: unwrap __name__ guard."""
    source = info.source

    if info.module_docstring:
        source = _strip_module_docstring(source)

    if info.has_name_main_guard:
        source = _unwrap_name_main_guard(source)

    is_pkg = info.path.name == "__init__.py"
    source = _rewrite_relative_imports(source, info.module_name, is_package=is_pkg)

    if _uses_argparse(source):
        source = "import sys as _sys; _sys.argv = [_sys.argv[0]]; del _sys\n" + source

    return source


def _uses_argparse(source: str) -> bool:
    """Detect if the source code calls argparse.parse_args()."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "argparse":
                    return True
        if isinstance(node, ast.ImportFrom) and node.module == "argparse":
            return True
    return False


# ---------------------------------------------------------------------------
# Module docstring stripping
# ---------------------------------------------------------------------------


def _strip_module_docstring(source: str) -> str:
    """Remove the module-level docstring from source code."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    if not tree.body:
        return source

    first = tree.body[0]
    if not (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return source

    lines = source.splitlines(keepends=True)
    start = first.lineno - 1
    end = first.end_lineno  # type: ignore[assignment]
    del lines[start:end]

    # Remove leading blank lines left behind
    while lines and lines[0].strip() == "":
        del lines[0]

    return "".join(lines)


# ---------------------------------------------------------------------------
# __name__ guard manipulation
# ---------------------------------------------------------------------------


def _remove_name_main_guard(source: str) -> str:
    """Delete ``if __name__ == '__main__':`` blocks entirely."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    lines = source.splitlines(keepends=True)
    ranges: list[tuple[int, int]] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.If) and _is_name_main_guard(node):
            ranges.append((node.lineno - 1, node.end_lineno))  # type: ignore[arg-type]

    for start, end in reversed(ranges):
        del lines[start:end]

    return "".join(lines)


def _unwrap_name_main_guard(source: str) -> str:
    """Replace the guard with its dedented body so the code always runs."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    lines = source.splitlines(keepends=True)

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.If) and _is_name_main_guard(node):
            guard_start = node.lineno - 1
            guard_end = node.end_lineno  # type: ignore[assignment]

            body_start = node.body[0].lineno - 1
            body_text = "".join(lines[body_start:guard_end])
            dedented = textwrap.dedent(body_text)

            lines[guard_start:guard_end] = dedented.splitlines(keepends=True)

    return "".join(lines)


# ---------------------------------------------------------------------------
# Relative import rewriting
# ---------------------------------------------------------------------------


def _rewrite_relative_imports(
    source: str, module_name: str, is_package: bool = False
) -> str:
    """Convert relative imports (``from . import X``) to absolute form."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    lines = source.splitlines(keepends=True)
    replacements: list[tuple[int, int, str]] = []

    for node in ast.walk(tree):
        if not (isinstance(node, ast.ImportFrom) and node.level and node.level > 0):
            continue

        if is_package:
            package = module_name
        else:
            idx = module_name.rfind(".")
            package = module_name[:idx] if idx >= 0 else ""

        pkg_parts = package.split(".") if package else []
        go_up = node.level - 1
        if go_up > len(pkg_parts):
            continue
        base_parts = pkg_parts[: len(pkg_parts) - go_up] if go_up > 0 else pkg_parts
        base = ".".join(base_parts)
        if node.module:
            abs_module = f"{base}.{node.module}" if base else node.module
        else:
            abs_module = base
        if not abs_module:
            continue

        names = ", ".join(
            f"{a.name} as {a.asname}" if a.asname else a.name for a in node.names
        )
        new_line = f"from {abs_module} import {names}\n"
        start = node.lineno - 1
        end = node.end_lineno  # type: ignore[assignment]
        replacements.append((start, end, new_line))

    for start, end, new_line in sorted(replacements, key=lambda r: r[0], reverse=True):
        lines[start:end] = [new_line]

    return "".join(lines)


# ---------------------------------------------------------------------------
# Module registration epilogue
# ---------------------------------------------------------------------------


def _generate_module_registration(module_name: str, defined_names: list[str]) -> str:
    """Generate the snippet that registers a module in ``sys.modules``.

    Reuses an existing module object when present so that attributes set
    by earlier cells (e.g. submodule references on a parent package) are
    preserved.
    """
    parts = module_name.split(".")
    names_literal = ", ".join(repr(n) for n in defined_names)

    lines: list[str] = [
        "# --- rep2nb: register module so imports resolve ---",
        "import types as _types, sys as _sys",
    ]

    for i in range(1, len(parts)):
        pkg = ".".join(parts[:i])
        lines.append(f"if {pkg!r} not in _sys.modules:")
        lines.append(f"    _pkg = _types.ModuleType({pkg!r})")
        lines.append("    _pkg.__path__ = []")
        lines.append(f"    _sys.modules[{pkg!r}] = _pkg")

    lines.append(
        f"_mod = _sys.modules.get({module_name!r}) or _types.ModuleType({module_name!r})"
    )
    if defined_names:
        lines.append(f"for _n in [{names_literal}]:")
        lines.append("    if _n in globals(): setattr(_mod, _n, globals()[_n])")
    lines.append(f"_sys.modules[{module_name!r}] = _mod")

    if len(parts) > 1:
        parent = ".".join(parts[:-1])
        attr = parts[-1]
        lines.append(
            f"if {parent!r} in _sys.modules: "
            f"setattr(_sys.modules[{parent!r}], {attr!r}, _mod)"
        )

    lines.append("del _types, _sys, _mod")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


def _is_name_main_guard(node: ast.If) -> bool:
    test = node.test
    if not isinstance(test, ast.Compare):
        return False
    if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
        return False
    left, right = test.left, test.comparators[0]
    return (_is_dunder(left) and _is_main(right)) or (
        _is_main(left) and _is_dunder(right)
    )


def _is_dunder(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id == "__name__"


def _is_main(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value == "__main__"
