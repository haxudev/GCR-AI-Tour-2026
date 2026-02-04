#!/usr/bin/env python3
"""File I/O tools for MAF local workflows.

These are deterministic local tools used by generated workflows.
Discovered by shared_tools/maf_shared_tools_registry.py via register_tools(registry).
"""

from __future__ import annotations

from pathlib import Path


def write_text_file(path: str, text: str, overwrite: bool = True, encoding: str = "utf-8") -> str:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)

    if p.exists() and not overwrite:
        raise FileExistsError(str(p))

    p.write_text(text or "", encoding=encoding)
    return str(p)


def register_tools(registry: object) -> None:
    register = getattr(registry, "register_tool", None)
    if not callable(register):
        return

    register("write_text_file", write_text_file)
