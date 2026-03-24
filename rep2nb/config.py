import sys

DEFAULT_EXCLUDE_DIRS: set[str] = {
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "env",
    ".env",
    "node_modules",
    "build",
    "dist",
    ".eggs",
    ".tox",
    ".nox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pypackages__",
    ".ipynb_checkpoints",
    "site-packages",
}

ENTRY_POINT_NAMES: set[str] = {"main.py", "app.py", "run.py", "pipeline.py"}

README_NAMES: list[str] = ["README.md", "README.rst", "README.txt", "README"]

STDLIB_MODULES: set[str] = sys.stdlib_module_names

# Common import-name -> pip-package-name mismatches
IMPORT_TO_PIP: dict[str, str] = {
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "PIL": "Pillow",
    "bs4": "beautifulsoup4",
    "yaml": "pyyaml",
    "attr": "attrs",
    "serial": "pyserial",
    "usb": "pyusb",
    "skimage": "scikit-image",
    "dateutil": "python-dateutil",
    "dotenv": "python-dotenv",
    "jose": "python-jose",
    "Crypto": "pycryptodome",
    "jwt": "PyJWT",
    "gi": "PyGObject",
    "wx": "wxPython",
    "lxml": "lxml",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "xlrd": "xlrd",
    "openpyxl": "openpyxl",
}
