#!/usr/bin/env python3
"""Self-contained shared local tools registry (skill example).

This file is intentionally located under `.github/skills/maf-shared-tools/examples/`

Discovery convention:
- Any Python module in `examples/*.py` (excluding this file) may export `register_tools(registry)`.
- The registry is duck-typed and only requires `register_tool(name, func)`.

This registry is designed to be used by:
- `.github/skills/maf-shared-tools/scripts/call_shared_tool.py`
- The workflow runner template in `.github/skills/maf-workflow-gen/scripts/run_template.py`
"""

from __future__ import annotations

import importlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ToolFunc = Callable[..., Any]


@dataclass
class ToolRegistry:
    tools: dict[str, ToolFunc] = field(default_factory=dict)

    def register_tool(self, name: str, func: ToolFunc) -> None:
        key = (name or "").strip()
        if not key:
            raise ValueError("Tool name must be non-empty")
        if not callable(func):
            raise TypeError("Tool func must be callable")
        self.tools[key] = func

    def call(self, name: str, args: dict[str, Any] | None = None) -> Any:
        key = (name or "").strip()
        if key not in self.tools:
            raise KeyError(f"Unknown tool: {key}")
        payload = args or {}
        if not isinstance(payload, dict):
            raise TypeError("args must be a JSON object")
        return self.tools[key](**payload)

    def list_tools(self) -> list[str]:
        return sorted(self.tools.keys())


_REGISTRY = ToolRegistry()
_DISCOVERED = False


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_text_file(path: str, text: str, overwrite: bool = True) -> str:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    _ensure_parent(p)
    if p.exists() and not overwrite:
        raise FileExistsError(str(p))
    p.write_text(text, encoding="utf-8")
    return str(p)


def write_json_file(path: str, data: Any, indent: int = 2, overwrite: bool = True) -> str:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    _ensure_parent(p)
    if p.exists() and not overwrite:
        raise FileExistsError(str(p))
    p.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
    return str(p)


def _register_builtin_tools(registry: ToolRegistry) -> None:
    registry.register_tool("write_text_file", write_text_file)
    registry.register_tool("write_json_file", write_json_file)


def _try_register_podcast_wrapper(registry: ToolRegistry) -> None:
    """Register a convenience wrapper used by TTSExecutorAgent.

    We keep it optional: if Azure Speech deps or config are missing, discovery should still work.
    """

    try:
        import azure_tts_tool  # type: ignore

        def podcast_tts_from_dialogues(
            dialogues: list[dict[str, Any]],
            output_file: str,
            male_voice: str | None = None,
            female_voice: str | None = None,
            pause_between_speakers_ms: int = 500,
        ) -> str:
            out = Path(output_file).expanduser()
            if not out.is_absolute():
                out = (Path.cwd() / out).resolve()
            out.parent.mkdir(parents=True, exist_ok=True)

            mv = male_voice or "zh-CN-YunxiNeural"
            fv = female_voice or "zh-CN-XiaoxiaoNeural"

            result = azure_tts_tool.generate_podcast_with_ssml(
                dialogues=dialogues,
                output_file=str(out),
                male_voice=mv,
                female_voice=fv,
                pause_between_speakers_ms=int(pause_between_speakers_ms),
            )
            if isinstance(result, dict) and result.get("status") == "success":
                return str(out)
            raise RuntimeError(f"TTS failed: {result}")

        registry.register_tool("podcast_tts_from_dialogues", podcast_tts_from_dialogues)
    except Exception:
        # Optional.
        return


def discover_tools() -> None:
    """One-time discovery of built-in and examples/*.py register_tools hooks."""

    global _DISCOVERED
    if _DISCOVERED:
        return

    examples_dir = Path(__file__).resolve().parent

    # Add examples/ to sys.path so `import <module_stem>` works.
    if str(examples_dir) not in sys.path:
        sys.path.insert(0, str(examples_dir))

    _register_builtin_tools(_REGISTRY)
    _try_register_podcast_wrapper(_REGISTRY)

    for py in sorted(examples_dir.glob("*.py")):
        if py.name.startswith("_"):
            continue
        if py.name == Path(__file__).name:
            continue
        mod_name = py.stem
        try:
            mod = importlib.import_module(mod_name)
        except Exception:
            continue
        register = getattr(mod, "register_tools", None)
        if callable(register):
            try:
                register(_REGISTRY)
            except Exception:
                continue

    _DISCOVERED = True


def list_tools(workflow_tools_dir: str | Path | None = None) -> list[str]:
    discover_tools()
    return _REGISTRY.list_tools()


def call_tool(
    name: str,
    args: dict[str, Any] | None = None,
    workflow_tools_dir: str | Path | None = None,
) -> Any:
    discover_tools()
    return _REGISTRY.call(name, args)


def _find_repo_shared_registry() -> Path | None:
    here = Path(__file__).resolve()
    for p in [here.parent, *here.parents]:
        candidate = p / "shared_tools" / "maf_shared_tools_registry.py"
        if candidate.exists():
            return candidate
    return None


# When this skill lives inside a repo that already has `shared_tools/`, delegate to it
# so we keep a single source of truth for tool discovery.
_repo_registry_path = _find_repo_shared_registry()
if _repo_registry_path:
    shared_dir = _repo_registry_path.parent
    if str(shared_dir) not in sys.path:
        sys.path.insert(0, str(shared_dir))
    try:
        import maf_shared_tools_registry as _repo_registry  # type: ignore

        def list_tools(workflow_tools_dir: str | Path | None = None) -> list[str]:  # type: ignore[no-redef]
            return _repo_registry.list_tools(workflow_tools_dir=workflow_tools_dir)

        def call_tool(  # type: ignore[no-redef]
            name: str,
            args: dict[str, Any] | None = None,
            workflow_tools_dir: str | Path | None = None,
        ) -> Any:
            return _repo_registry.call_tool(name, args, workflow_tools_dir=workflow_tools_dir)
    except Exception:
        # Keep the self-contained example behavior.
        pass
