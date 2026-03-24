"""rep2nb — Convert a Python repository into a single executable Jupyter notebook."""

__version__ = "0.1.0"

from pathlib import Path

import nbformat

from .analyzer import ModuleInfo, analyze_file, detect_entry_points, get_all_module_names
from .discovery import discover_python_files, find_data_files, find_readme, group_by_section
from .graph import build_dependency_graph, topological_sort
from .notebook_builder import CellEntry, Section, build_notebook
from .transformer import transform_entry_point, transform_module


def convert(
    repo_path: str,
    output: str = "output.ipynb",
    entry: str | list[str] | None = None,
    exclude: list[str] | None = None,
    include_pip_install: bool = False,
    no_sections: bool = False,
) -> str:
    """Convert a Python repository to an executable ``.ipynb`` file.

    Parameters
    ----------
    repo_path:
        Path to the repository root directory.
    output:
        Destination path for the generated notebook.
    entry:
        Entry-point filename(s) relative to *repo_path*.  May be a single
        string or a list.  Order is preserved so you can control execution
        sequence.  Auto-detected when omitted.
    exclude:
        Directory / file names to skip.
    include_pip_install:
        When *True*, prepend a ``!pip install`` cell for external deps.
    no_sections:
        When *True*, treat the entire repo as a single flat section
        even if independent subdirectories are detected.

    Returns
    -------
    str
        The path the notebook was written to.
    """
    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        raise ValueError(f"Not a directory: {repo}")

    # -- 1. Discovery -------------------------------------------------------
    py_files = discover_python_files(repo, exclude)
    if not py_files:
        raise ValueError(f"No Python files found in {repo}")

    readme_path = find_readme(repo)
    data_files = find_data_files(repo, py_files, exclude)

    # -- 2. Determine sections -----------------------------------------------
    if no_sections:
        file_groups: dict[str | None, list[Path]] = {None: py_files}
    else:
        file_groups = group_by_section(py_files, repo)

    # Normalise entry to a list
    if isinstance(entry, str):
        entry = [entry]

    # -- 3. Process each section ---------------------------------------------
    sections: list[Section] = []

    for section_name in sorted(file_groups, key=lambda k: (k is not None, k or "")):
        section_files = file_groups[section_name]

        if section_name is not None:
            section_root = repo / section_name
        else:
            section_root = repo

        local_module_names = get_all_module_names(section_files, section_root)

        analyses: dict[str, ModuleInfo] = {}
        for f in section_files:
            info = analyze_file(f, section_root, local_module_names)
            if info.module_name:
                analyses[info.module_name] = info

        if not analyses:
            continue

        # Filter entries belonging to this section
        section_entries: list[str] | None = None
        if entry:
            se: list[str] = []
            for e in entry:
                e_norm = e.replace("\\", "/")
                if section_name is not None and e_norm.startswith(section_name + "/"):
                    se.append(e_norm[len(section_name) + 1:])
                elif section_name is None and "/" not in e_norm:
                    se.append(e_norm)
            section_entries = se or None

        entry_modules = detect_entry_points(analyses, section_entries, section_root)
        for name in entry_modules:
            if name in analyses:
                analyses[name].is_entry_point = True

        dep_graph = build_dependency_graph(analyses)
        order = topological_sort(dep_graph, entry_modules)

        sec = Section(name=section_name)
        for mod_name in order:
            info = analyses[mod_name]
            sec.external_imports.extend(info.external_imports)
            sec.registered_modules.append(mod_name)

            if section_name is not None:
                rel_path = f"{section_name}/{info.path.relative_to(section_root)}"
            else:
                rel_path = str(info.path.relative_to(section_root))

            if info.is_entry_point:
                code = transform_entry_point(info)
            else:
                code = transform_module(info)

            sec.cells.append(CellEntry(
                filename=rel_path,
                code=code,
                docstring=info.module_docstring,
            ))

        sections.append(sec)

    if not sections:
        raise ValueError("No analysable Python modules found")

    # -- 4. Build notebook ---------------------------------------------------
    readme_content = (
        readme_path.read_text(encoding="utf-8") if readme_path else None
    )
    data_rel = [str(f.relative_to(repo)) for f in data_files]

    nb = build_notebook(
        readme_content=readme_content,
        data_files=data_rel,
        external_imports=[],
        cells=[],
        include_pip_install=include_pip_install,
        sections=sections,
    )

    # -- 5. Write ------------------------------------------------------------
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        nbformat.write(nb, fh)

    return str(out_path)
