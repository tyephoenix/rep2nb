from collections import defaultdict
from pathlib import Path

from .config import DEFAULT_EXCLUDE_DIRS, ENTRY_POINT_NAMES, README_NAMES


def discover_python_files(
    repo_path: Path,
    exclude: list[str] | None = None,
) -> list[Path]:
    """Find all .py files in the repo, respecting exclusions."""
    exclude_set = set(DEFAULT_EXCLUDE_DIRS)
    if exclude:
        for pattern in exclude:
            exclude_set.add(pattern.strip("/\\"))

    py_files: list[Path] = []
    for path in sorted(repo_path.rglob("*.py")):
        rel = path.relative_to(repo_path)
        parts = rel.parts

        if any(_matches_exclude(part, exclude_set) for part in parts):
            continue

        py_files.append(path)

    return py_files


def _matches_exclude(part: str, exclude_set: set[str]) -> bool:
    """Check if a path component matches any exclusion pattern."""
    if part in exclude_set:
        return True
    for pattern in exclude_set:
        if pattern.endswith(".egg-info") and part.endswith(".egg-info"):
            return True
    return False


def find_readme(repo_path: Path) -> Path | None:
    """Find the README file at the repo root."""
    for name in README_NAMES:
        readme = repo_path / name
        if readme.exists():
            return readme
    return None


def group_by_section(
    py_files: list[Path],
    repo_path: Path,
) -> dict[str | None, list[Path]]:
    """Group Python files into independent sections by top-level directory.

    A top-level directory is treated as a section when it does *not*
    contain an ``__init__.py`` (i.e. it is not a Python package).
    Files directly under *repo_path* form the ``None`` (root) section.

    Returns a mapping from section name (or ``None`` for root) to the
    list of Python files belonging to that section.
    """
    all_names = {f.relative_to(repo_path).parts[0] for f in py_files if len(f.relative_to(repo_path).parts) > 1}
    package_dirs = {
        name for name in all_names if (repo_path / name / "__init__.py").exists()
    }

    groups: dict[str | None, list[Path]] = defaultdict(list)
    for f in py_files:
        rel = f.relative_to(repo_path)
        if len(rel.parts) == 1:
            groups[None].append(f)
        else:
            top = rel.parts[0]
            if top in package_dirs:
                groups[None].append(f)
            else:
                groups[top].append(f)

    return dict(groups)


def find_data_files(
    repo_path: Path,
    py_files: list[Path],
    exclude: list[str] | None = None,
) -> list[Path]:
    """Find non-Python, non-config files that the repo might depend on."""
    exclude_set = set(DEFAULT_EXCLUDE_DIRS)
    if exclude:
        for pattern in exclude:
            exclude_set.add(pattern.strip("/\\"))

    skip_names = {
        "LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "LICENCE.md",
        "pyproject.toml", "setup.py", "setup.cfg",
        "requirements.txt", "requirements-dev.txt",
        "Makefile", "Dockerfile", ".dockerignore",
        ".gitignore", ".gitattributes",
        "MANIFEST.in", "tox.ini", ".flake8", ".pylintrc",
        "mypy.ini", ".pre-commit-config.yaml",
    }
    py_set = set(py_files)
    data_files: list[Path] = []

    for path in sorted(repo_path.rglob("*")):
        if path.is_dir():
            continue
        if path in py_set:
            continue

        rel = path.relative_to(repo_path)
        parts = rel.parts

        if any(_matches_exclude(part, exclude_set) for part in parts):
            continue
        if path.name.startswith("."):
            continue
        if path.name in skip_names:
            continue
        if path.name.upper().startswith("README"):
            continue

        data_files.append(path)

    return data_files
