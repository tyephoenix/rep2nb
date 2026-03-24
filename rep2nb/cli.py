import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="rep2nb",
        description="Convert a Python repository into a single executable Jupyter notebook.",
    )
    parser.add_argument(
        "repo",
        type=Path,
        help="Path to the repository root",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output .ipynb path (default: <repo-name>.ipynb)",
    )
    parser.add_argument(
        "--entry",
        action="append",
        default=[],
        help="Entry-point file relative to repo (e.g. main.py). "
        "Repeatable; order is preserved. Auto-detected if omitted.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Directories or files to exclude (repeatable)",
    )
    parser.add_argument(
        "--include-pip-install",
        action="store_true",
        help="Add a !pip install cell for detected external dependencies",
    )
    parser.add_argument(
        "--no-sections",
        action="store_true",
        help="Treat the entire repo as one flat project (disable auto-section detection)",
    )

    args = parser.parse_args(argv)

    repo: Path = args.repo.resolve()
    if not repo.is_dir():
        print(f"Error: {repo} is not a directory", file=sys.stderr)
        sys.exit(1)

    output: Path = args.output or Path(f"{repo.name}.ipynb")

    from . import convert

    try:
        result = convert(
            repo_path=str(repo),
            output=str(output),
            entry=args.entry or None,
            exclude=args.exclude or None,
            include_pip_install=args.include_pip_install,
            no_sections=args.no_sections,
        )
        print(f"Notebook written to {result}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
