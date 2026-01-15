#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


def _skill_root() -> Path:
    # scripts/call_shared_tool.py -> maf-shared-tools/
    return Path(__file__).resolve().parents[1]


def _repo_root() -> Path:
    # .github/skills/maf-shared-tools/scripts -> repo root
    return Path(__file__).resolve().parents[4]


def _load_registry_module() -> object:
    # New convention: repo-level registry lives in shared_tools/.
    repo_root = _repo_root()
    shared_registry = repo_root / "shared_tools" / "maf_shared_tools_registry.py"

    if shared_registry.exists():
        registry_path = shared_registry
    else:
        # Fallback to the self-contained skill example registry.
        skill_root = _skill_root()
        registry_path = skill_root / "examples" / "maf_shared_tools_registry.py"
        if not registry_path.exists():
            raise RuntimeError(f"Missing registry at {registry_path}")

    spec = importlib.util.spec_from_file_location("maf_shared_tools_registry_skill", str(registry_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module spec for {registry_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Call a shared local tool via the repo shared_tools registry"
    )
    parser.add_argument("--tool", required=True, help="Tool name (e.g. audio.get_audio_duration)")
    parser.add_argument(
        "--args-json",
        default="{}",
        help='JSON object string for args (e.g. {"file_path":"..."})',
    )

    args = parser.parse_args()

    registry = _load_registry_module()
    call_tool = getattr(registry, "call_tool", None)
    list_tools = getattr(registry, "list_tools", None)
    if not callable(call_tool) or not callable(list_tools):
        raise RuntimeError("Registry module missing call_tool/list_tools")

    try:
        payload: Any = json.loads(args.args_json)
    except json.JSONDecodeError as e:
        raise SystemExit(f"Invalid --args-json: {e}")

    if not isinstance(payload, dict):
        raise SystemExit("--args-json must be a JSON object")

    if args.tool == "__list__":
        print(json.dumps({"tools": list_tools()}, ensure_ascii=False, indent=2))
        return 0

    result = call_tool(args.tool, payload)
    print(json.dumps({"result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
