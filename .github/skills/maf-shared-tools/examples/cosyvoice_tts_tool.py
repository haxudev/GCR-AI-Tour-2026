#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _repo_root() -> Path:
    # .github/skills/maf-shared-tools/examples -> repo root
    return Path(__file__).resolve().parents[4]


def register_tools(registry: object) -> None:
    """Expose the repo's CosyVoice tool in the skill example registry.

    This keeps the skill example registry lightweight while reusing the
    canonical implementation under tools/.
    """

    tools_dir = _repo_root() / "tools"
    tool_path = tools_dir / "cosyvoice_tts_tool.py"
    if not tool_path.exists():
        return

    # Load by file path to avoid importing this module (same name) recursively.
    spec = importlib.util.spec_from_file_location("repo_cosyvoice_tts_tool", str(tool_path))
    if spec is None or spec.loader is None:
        return

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    register = getattr(module, "register_tools", None)
    if callable(register):
        register(registry)
