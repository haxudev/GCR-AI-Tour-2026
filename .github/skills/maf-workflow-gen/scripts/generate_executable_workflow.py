#!/usr/bin/env python3
"""Generate an executable local runner from a MAF declarative workflow YAML.

This script creates a self-contained output folder with:
- workflow.yaml (copied from input)
- maf_declarative_runtime.py (runtime/interpreter)
- run.py (entrypoint, rendered from templates)
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _tool_file_for_workflow(in_yaml: Path) -> Path | None:
    """Return the canonical workflow tools file next to the workflow YAML, if present.

    Convention:
      workflows/<name>.yaml -> workflows/<name>_tools.py (or <name>_tool.py)
    """

    base = in_yaml.resolve().parent
    stem = in_yaml.stem
    for suffix in ("_tools.py", "_tool.py"):
        candidate = base / f"{stem}{suffix}"
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _collect_existing_tool_files(out_dir: Path) -> dict[str, bytes]:
    """Collect existing workflow-specific tool modules in an output folder."""

    keep: dict[str, bytes] = {}
    if not out_dir.exists() or not out_dir.is_dir():
        return keep
    for py in sorted({*out_dir.glob("*_tools.py"), *out_dir.glob("*_tool.py")}):
        try:
            keep[py.name] = _read_bytes(py)
        except Exception:
            continue
    return keep


def _read_run_template(workflow_yaml_name: str) -> str:
    template_path = Path(__file__).resolve().parent / "run_template.py"
    template = template_path.read_text(encoding="utf-8")
    return template.replace("__WORKFLOW_YAML__", workflow_yaml_name)


def generate(in_path: Path, out_dir: Path, *, force: bool) -> None:
    if not in_path.exists():
        raise FileNotFoundError(f"Input workflow not found: {in_path}")

    out_dir = out_dir.resolve()

    # Preserve any existing workflow-specific tools that live in generated/<workflow>/.
    # This ensures tools survive `--force` regeneration even if their source is not in workflows/.
    preserved_tools: dict[str, bytes] = {}
    if out_dir.exists() and force:
        preserved_tools = _collect_existing_tool_files(out_dir)

    if out_dir.exists():
        if not force:
            raise FileExistsError(
                f"Output directory already exists: {out_dir} (use --force to overwrite)"
            )
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    workflow_yaml_name = "workflow.yaml"
    shutil.copyfile(in_path, out_dir / workflow_yaml_name)

    runtime_src = Path(__file__).resolve().parent / "maf_declarative_runtime.py"
    shutil.copyfile(runtime_src, out_dir / "maf_declarative_runtime.py")

    run_py = _read_run_template(workflow_yaml_name)
    (out_dir / "run.py").write_text(run_py, encoding="utf-8")

    # Copy workflow-specific tools into the generated runner folder.
    # Priority:
    # 1) A canonical tools file next to the input YAML (workflows/<stem>_tools.py)
    # 2) Previously preserved tool modules from the existing out_dir
    tools_src = _tool_file_for_workflow(in_path)
    if tools_src is not None:
        shutil.copyfile(tools_src, out_dir / tools_src.name)
    elif preserved_tools:
        for name, content in preserved_tools.items():
            (out_dir / name).write_bytes(content)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a runnable local Python runner from a MAF declarative workflow YAML."
    )
    parser.add_argument("--in", dest="in_path", required=True, help="Input workflow YAML")
    parser.add_argument(
        "--out", dest="out_dir", required=True, help="Output folder (will be created)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite output folder if it already exists",
    )
    return parser


def main() -> int:
    args = _build_arg_parser().parse_args()
    generate(Path(args.in_path), Path(args.out_dir), force=bool(args.force))
    print(f"Generated runner at: {Path(args.out_dir).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
