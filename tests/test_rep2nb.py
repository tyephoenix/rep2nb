"""End-to-end and unit tests for rep2nb."""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from rep2nb import convert
from rep2nb.analyzer import (
    analyze_file,
    detect_entry_points,
    get_all_module_names,
    get_defined_names,
    get_module_name,
)
from rep2nb.discovery import discover_python_files, find_data_files, find_readme, group_by_section
from rep2nb.graph import build_dependency_graph, topological_sort
from rep2nb.transformer import transform_entry_point, transform_module

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class TestDiscovery:
    def test_finds_all_py_files(self):
        files = discover_python_files(FIXTURES / "simple_repo")
        names = {f.name for f in files}
        assert names == {"main.py", "utils.py"}

    def test_excludes_dirs(self):
        files = discover_python_files(FIXTURES / "multi_dep_repo", exclude=["helpers.py"])
        names = {f.name for f in files}
        assert "helpers.py" not in names

    def test_finds_readme(self):
        assert find_readme(FIXTURES / "simple_repo") is not None
        assert find_readme(FIXTURES / "multi_dep_repo") is None

    def test_finds_data_files(self):
        py = discover_python_files(FIXTURES / "multi_dep_repo")
        data = find_data_files(FIXTURES / "multi_dep_repo", py)
        names = {f.name for f in data}
        assert "data.csv" in names


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class TestAnalyzer:
    def test_module_name_flat(self):
        repo = FIXTURES / "simple_repo"
        assert get_module_name(repo / "utils.py", repo) == "utils"
        assert get_module_name(repo / "main.py", repo) == "main"

    def test_module_name_package(self):
        repo = FIXTURES / "package_repo"
        assert get_module_name(repo / "mypackage" / "__init__.py", repo) == "mypackage"
        assert get_module_name(repo / "mypackage" / "core.py", repo) == "mypackage.core"

    def test_local_vs_external_imports(self):
        repo = FIXTURES / "multi_dep_repo"
        py_files = discover_python_files(repo)
        names = get_all_module_names(py_files, repo)
        info = analyze_file(repo / "data_processor.py", repo, names)
        assert "config" in info.local_imports
        assert "helpers" in info.local_imports
        assert "json" in info.external_imports

    def test_detects_name_main_guard(self):
        repo = FIXTURES / "simple_repo"
        py_files = discover_python_files(repo)
        names = get_all_module_names(py_files, repo)
        main_info = analyze_file(repo / "main.py", repo, names)
        utils_info = analyze_file(repo / "utils.py", repo, names)
        assert main_info.has_name_main_guard is True
        assert utils_info.has_name_main_guard is True

    def test_defined_names(self):
        source = textwrap.dedent("""\
            import os
            X = 1
            def foo(): pass
            class Bar: pass
        """)
        names = get_defined_names(source)
        assert "os" in names
        assert "X" in names
        assert "foo" in names
        assert "Bar" in names

    def test_detect_entry_points_by_name(self):
        repo = FIXTURES / "simple_repo"
        py_files = discover_python_files(repo)
        names = get_all_module_names(py_files, repo)
        analyses = {}
        for f in py_files:
            info = analyze_file(f, repo, names)
            analyses[info.module_name] = info
        eps = detect_entry_points(analyses, None, repo)
        assert "main" in eps

    def test_detect_entry_points_explicit(self):
        repo = FIXTURES / "simple_repo"
        py_files = discover_python_files(repo)
        names = get_all_module_names(py_files, repo)
        analyses = {}
        for f in py_files:
            info = analyze_file(f, repo, names)
            analyses[info.module_name] = info
        eps = detect_entry_points(analyses, ["utils.py"], repo)
        assert eps == ["utils"]

    def test_relative_import_in_init(self):
        repo = FIXTURES / "package_repo"
        py_files = discover_python_files(repo)
        names = get_all_module_names(py_files, repo)
        info = analyze_file(repo / "mypackage" / "__init__.py", repo, names)
        assert "mypackage.core" in info.local_imports


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


class TestGraph:
    def test_topological_order(self):
        repo = FIXTURES / "multi_dep_repo"
        py_files = discover_python_files(repo)
        names = get_all_module_names(py_files, repo)
        analyses = {}
        for f in py_files:
            info = analyze_file(f, repo, names)
            analyses[info.module_name] = info

        graph = build_dependency_graph(analyses)
        order = topological_sort(graph, ["main"])

        assert order.index("config") < order.index("helpers")
        assert order.index("helpers") < order.index("data_processor")
        assert order[-1] == "main"

    def test_cycle_detection(self):
        graph = {"a": {"b"}, "b": {"a"}}
        with pytest.raises(ValueError, match="Circular dependency"):
            topological_sort(graph)


# ---------------------------------------------------------------------------
# Transformer
# ---------------------------------------------------------------------------


class TestTransformer:
    def test_strips_name_main_guard(self):
        repo = FIXTURES / "simple_repo"
        py_files = discover_python_files(repo)
        names = get_all_module_names(py_files, repo)
        info = analyze_file(repo / "utils.py", repo, names)
        result = transform_module(info)
        assert 'if __name__' not in result
        assert "def greet" in result
        assert "sys.modules" in result

    def test_unwraps_name_main_guard(self):
        repo = FIXTURES / "simple_repo"
        py_files = discover_python_files(repo)
        names = get_all_module_names(py_files, repo)
        info = analyze_file(repo / "main.py", repo, names)
        info.is_entry_point = True
        result = transform_entry_point(info)
        assert 'if __name__' not in result
        assert 'greet("World")' in result

    def test_rewrites_relative_imports(self):
        repo = FIXTURES / "package_repo"
        py_files = discover_python_files(repo)
        names = get_all_module_names(py_files, repo)
        info = analyze_file(repo / "mypackage" / "core.py", repo, names)
        result = transform_module(info)
        assert "from mypackage.utils import validate" in result

    def test_module_registration_preserves_existing(self):
        repo = FIXTURES / "package_repo"
        py_files = discover_python_files(repo)
        names = get_all_module_names(py_files, repo)
        info = analyze_file(repo / "mypackage" / "__init__.py", repo, names)
        result = transform_module(info)
        assert "_sys.modules.get('mypackage')" in result


# ---------------------------------------------------------------------------
# End-to-end: convert() API
# ---------------------------------------------------------------------------


class TestConvertAPI:
    def test_simple_repo(self, tmp_path):
        out = tmp_path / "simple.ipynb"
        convert(str(FIXTURES / "simple_repo"), output=str(out))
        nb = json.loads(out.read_text("utf-8"))
        code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
        assert len(code_cells) == 2
        assert any("def greet" in "".join(c["source"]) for c in code_cells)

    def test_multi_dep_repo(self, tmp_path):
        out = tmp_path / "multi.ipynb"
        convert(str(FIXTURES / "multi_dep_repo"), output=str(out))
        nb = json.loads(out.read_text("utf-8"))
        code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
        sources = ["".join(c["source"]) for c in code_cells]
        config_idx = next(i for i, s in enumerate(sources) if "API_KEY" in s)
        main_idx = next(i for i, s in enumerate(sources) if "fetch_data" in s and "from" in s)
        assert config_idx < main_idx

    def test_package_repo(self, tmp_path):
        out = tmp_path / "pkg.ipynb"
        convert(str(FIXTURES / "package_repo"), output=str(out))
        nb = json.loads(out.read_text("utf-8"))
        code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
        sources = ["".join(c["source"]) for c in code_cells]
        utils_idx = next(i for i, s in enumerate(sources) if "def validate" in s)
        init_idx = next(i for i, s in enumerate(sources) if "from mypackage.core" in s)
        assert utils_idx < init_idx

    def test_include_pip_install(self, tmp_path):
        out = tmp_path / "pip.ipynb"
        convert(
            str(FIXTURES / "external_deps_repo"),
            output=str(out),
            include_pip_install=True,
        )
        nb = json.loads(out.read_text("utf-8"))
        code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
        first_code = "".join(code_cells[0]["source"])
        assert "-m pip install" in first_code
        assert "numpy" in first_code
        assert "scikit-learn" in first_code

    def test_entry_ordering(self, tmp_path):
        out = tmp_path / "fileio.ipynb"
        convert(
            str(FIXTURES / "file_io_repo"),
            output=str(out),
            entry=["generate.py", "analyze.py"],
        )
        nb = json.loads(out.read_text("utf-8"))
        code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
        sources = ["".join(c["source"]) for c in code_cells]
        gen_idx = next(i for i, s in enumerate(sources) if "generate.py" in s)
        ana_idx = next(i for i, s in enumerate(sources) if "analyze.py" in s)
        assert gen_idx < ana_idx

    def test_readme_included(self, tmp_path):
        out = tmp_path / "readme.ipynb"
        convert(str(FIXTURES / "simple_repo"), output=str(out))
        nb = json.loads(out.read_text("utf-8"))
        md_cells = [c for c in nb["cells"] if c["cell_type"] == "markdown"]
        first_md = "".join(md_cells[0]["source"])
        assert "Simple Test Repo" in first_md

    def test_data_files_notice(self, tmp_path):
        out = tmp_path / "data.ipynb"
        convert(str(FIXTURES / "multi_dep_repo"), output=str(out))
        nb = json.loads(out.read_text("utf-8"))
        md_cells = [c for c in nb["cells"] if c["cell_type"] == "markdown"]
        all_md = " ".join("".join(c["source"]) for c in md_cells)
        assert "data.csv" in all_md

    def test_no_python_files_raises(self, tmp_path):
        empty = tmp_path / "empty_repo"
        empty.mkdir()
        with pytest.raises(ValueError, match="No Python files"):
            convert(str(empty))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_cli_runs(self, tmp_path):
        out = tmp_path / "cli_test.ipynb"
        result = subprocess.run(
            [sys.executable, "-m", "rep2nb.cli", str(FIXTURES / "simple_repo"), "-o", str(out)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert out.exists()

    def test_cli_bad_path(self):
        result = subprocess.run(
            [sys.executable, "-m", "rep2nb.cli", "nonexistent_dir_12345"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_cli_no_sections_flag(self, tmp_path):
        out = tmp_path / "nosec.ipynb"
        result = subprocess.run(
            [
                sys.executable, "-m", "rep2nb.cli",
                str(FIXTURES / "sections_repo"),
                "-o", str(out),
                "--no-sections",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert out.exists()


# ---------------------------------------------------------------------------
# Docstring Extraction
# ---------------------------------------------------------------------------


class TestDocstringExtraction:
    def test_analyzer_extracts_module_docstring(self):
        repo = FIXTURES / "docstring_repo"
        py_files = discover_python_files(repo)
        names = get_all_module_names(py_files, repo)
        info = analyze_file(repo / "utils.py", repo, names)
        assert info.module_docstring is not None
        assert "Utility functions" in info.module_docstring

    def test_analyzer_no_module_docstring(self):
        repo = FIXTURES / "sections_repo" / "project_a"
        py_files = discover_python_files(repo)
        names = get_all_module_names(py_files, repo)
        info = analyze_file(repo / "main.py", repo, names)
        assert info.module_docstring is None

    def test_transformer_strips_module_docstring(self):
        repo = FIXTURES / "docstring_repo"
        py_files = discover_python_files(repo)
        names = get_all_module_names(py_files, repo)
        info = analyze_file(repo / "utils.py", repo, names)
        result = transform_module(info)
        assert '"""Utility functions' not in result
        assert "def add" in result
        assert '"""Add two numbers."""' in result

    def test_docstring_becomes_markdown_cell(self, tmp_path):
        out = tmp_path / "doc.ipynb"
        convert(str(FIXTURES / "docstring_repo"), output=str(out))
        nb = json.loads(out.read_text("utf-8"))
        md_cells = [c for c in nb["cells"] if c["cell_type"] == "markdown"]
        md_text = " ".join("".join(c["source"]) for c in md_cells)
        assert "Utility functions" in md_text
        assert "Main entry point" in md_text

    def test_function_docstrings_preserved(self, tmp_path):
        out = tmp_path / "doc.ipynb"
        convert(str(FIXTURES / "docstring_repo"), output=str(out))
        nb = json.loads(out.read_text("utf-8"))
        code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
        all_code = " ".join("".join(c["source"]) for c in code_cells)
        assert "Add two numbers" in all_code
        assert "Multiply two numbers" in all_code


# ---------------------------------------------------------------------------
# Sections Mode
# ---------------------------------------------------------------------------


class TestSections:
    def test_group_by_section(self):
        repo = FIXTURES / "sections_repo"
        py_files = discover_python_files(repo)
        groups = group_by_section(py_files, repo)
        assert "project_a" in groups
        assert "project_b" in groups
        assert len(groups["project_a"]) == 2
        assert len(groups["project_b"]) == 2

    def test_group_by_section_package_stays_in_root(self):
        repo = FIXTURES / "package_repo"
        py_files = discover_python_files(repo)
        groups = group_by_section(py_files, repo)
        assert None in groups
        assert "mypackage" not in groups

    def test_sections_notebook_has_headers(self, tmp_path):
        out = tmp_path / "sections.ipynb"
        convert(str(FIXTURES / "sections_repo"), output=str(out))
        nb = json.loads(out.read_text("utf-8"))
        md_cells = [c for c in nb["cells"] if c["cell_type"] == "markdown"]
        md_text = " ".join("".join(c["source"]) for c in md_cells)
        assert "project_a" in md_text
        assert "project_b" in md_text

    def test_sections_have_cleanup_cells(self, tmp_path):
        out = tmp_path / "sections.ipynb"
        convert(str(FIXTURES / "sections_repo"), output=str(out))
        nb = json.loads(out.read_text("utf-8"))
        code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
        cleanup_cells = [
            c for c in code_cells
            if "section cleanup" in "".join(c["source"])
        ]
        assert len(cleanup_cells) >= 1

    def test_sections_isolate_same_module_names(self, tmp_path):
        out = tmp_path / "sections.ipynb"
        convert(str(FIXTURES / "sections_repo"), output=str(out))
        nb = json.loads(out.read_text("utf-8"))
        code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
        sources = ["".join(c["source"]) for c in code_cells]
        helpers_cells = [s for s in sources if "helpers.py" in s]
        assert len(helpers_cells) == 2

    def test_no_sections_flag(self, tmp_path):
        out = tmp_path / "flat.ipynb"
        convert(
            str(FIXTURES / "sections_repo"),
            output=str(out),
            no_sections=True,
        )
        nb = json.loads(out.read_text("utf-8"))
        md_cells = [c for c in nb["cells"] if c["cell_type"] == "markdown"]
        md_text = " ".join("".join(c["source"]) for c in md_cells)
        assert "## project_a" not in md_text
        assert "## project_b" not in md_text

    def test_section_specific_entry_points(self, tmp_path):
        out = tmp_path / "sec_entry.ipynb"
        convert(
            str(FIXTURES / "sections_repo"),
            output=str(out),
            entry=["project_a/main.py", "project_b/main.py"],
        )
        nb = json.loads(out.read_text("utf-8"))
        code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
        sources = ["".join(c["source"]) for c in code_cells]
        main_cells = [s for s in sources if "main.py" in s]
        assert len(main_cells) == 2
