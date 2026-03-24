# rep2nb

[![CI](https://github.com/tyephoenix/rep2nb/actions/workflows/ci.yml/badge.svg)](https://github.com/tyephoenix/rep2nb/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/rep2nb)](https://pypi.org/project/rep2nb/)
[![Python](https://img.shields.io/pypi/pyversions/rep2nb)](https://pypi.org/project/rep2nb/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://opensource.org/licenses/MIT)

Convert a Python repository into a single executable Jupyter notebook.

**The problem:** You built a well-structured repo with multiple files, proper separation of concerns, clean imports — then someone says "we need a `.ipynb`." You now have to manually copy-paste everything into cells, figure out the right order, inline your imports, and pray it runs.

**The solution:** One command.

```bash
rep2nb /path/to/your/repo -o submission.ipynb
```

`rep2nb` analyzes your repo's dependency graph, topologically sorts your files, and produces a single notebook where every cell runs in order — just like your repo does.

## Installation

```bash
pip install rep2nb
```

### From source

```bash
git clone https://github.com/tyephoenix/rep2nb.git
cd rep2nb
pip install .
```

## Usage

### CLI

```bash
# Auto-detect entry point, output to <repo-name>.ipynb
rep2nb myproject/

# Specify entry point and output file
rep2nb myproject/ --entry main.py -o submission.ipynb

# Exclude directories
rep2nb myproject/ --exclude tests/ --exclude docs/

# Add a pip install cell for external dependencies
rep2nb myproject/ --include-pip-install

# Multiple entry points in a specific order (e.g. generate data, then analyze it)
rep2nb myproject/ --entry generate.py --entry analyze.py

# Repo with multiple independent sub-projects (sections auto-detected)
rep2nb contest-repo/ --entry problem-1/pipeline.py --entry problem-2/main.py

# Disable auto-section detection
rep2nb myproject/ --no-sections
```

### Python API

```python
from rep2nb import convert

# Basic usage
convert("myproject/", output="submission.ipynb")

# With options
convert(
    "myproject/",
    output="submission.ipynb",
    entry="main.py",
    exclude=["tests/", "docs/"],
    include_pip_install=True,
)

# Multiple entry points with explicit ordering
convert("myproject/", entry=["generate.py", "analyze.py"])

# Multi-project repo with section-specific entries
convert(
    "contest-repo/",
    entry=["problem-1/pipeline.py", "problem-2/main.py"],
    output="submission.ipynb",
)
```

## How It Works

1. **Discovery** — finds all `.py` files, skipping `venv/`, `__pycache__/`, etc.
2. **Section Detection** — subdirectories without `__init__.py` are treated as independent sections; packages stay in the root section
3. **AST Analysis** — parses each file to extract imports, definitions, docstrings, and `if __name__ == '__main__'` blocks
4. **Dependency Graph** — builds a directed graph of which files import from which (per section)
5. **Topological Sort** — determines the correct execution order (dependencies first)
6. **Transform** — for each file:
   - Library modules: strips `if __name__ == '__main__'` test blocks, adds `sys.modules` registration so imports resolve correctly
   - Entry points: unwraps `if __name__ == '__main__'` so the code runs, resets `sys.argv` for argparse compatibility
   - Relative imports (`from . import X`) are rewritten to absolute form
   - Module-level docstrings are extracted and placed in markdown cells
7. **Notebook Assembly** — produces a valid `.ipynb` with:
   - README content as a markdown header (if found)
   - A notice about required data files
   - Optional `!pip install` cell (uses kernel-safe `sys.executable`)
   - Section headers and `os.chdir` for multi-project repos
   - Markdown cells with module docstrings above each code cell
   - `sys.modules` cleanup between sections to prevent name collisions

## Features

- **Dependency resolution** — handles `import X`, `from X import Y`, relative imports, and packages with `__init__.py`
- **Correct execution order** — topological sort ensures definitions exist before use
- **Cross-file imports just work** — each module is registered in `sys.modules`, so all import styles resolve correctly
- **Sections mode** — independent subdirectories (e.g. `problem-1/`, `problem-2/`) become isolated notebook sections with `sys.modules` cleanup between them, so files with the same name (like `helpers.py`) don't collide
- **Docstring extraction** — module-level docstrings become markdown cells above each code cell for readability; function/class docstrings stay in the code
- **Smart entry point detection** — auto-detects `main.py`, `app.py`, `pipeline.py`, `run.py`, or files with `if __name__ == '__main__'` that nothing else imports
- **Argparse handling** — resets `sys.argv` in entry points so `argparse` uses defaults instead of crashing on Jupyter kernel args
- **`__file__` support** — injects `__file__` so scripts using `os.path.dirname(__file__)` for relative paths still work
- **README at the top** — your repo's README becomes the notebook's header
- **Data file awareness** — lists non-Python files that should be in the working directory
- **Portable notebooks** — zero absolute paths; the generated notebook can be moved anywhere (bring your data files)
- **Zero config** — works out of the box for typical repo structures

## Limitations

- **Python only** — only converts `.py` files (notebooks run Python kernels)
- **Dynamic imports** — `importlib.import_module(name)` where `name` is a runtime value can't be detected statically
- **Subprocess calls** — if your code shells out to other scripts, those won't be inlined
- **Circular imports** — detected and reported as an error (fix them in your repo first)

## Development

```bash
git clone https://github.com/tyephoenix/rep2nb.git
cd rep2nb
pip install -e ".[dev]"
pytest
```

## Requirements

- Python >= 3.10
- `nbformat` (installed automatically)

## License

MIT
