"""Shared Tools Registry for MAF Workflows.

This is the source of truth for all local deterministic tools.

Key behaviors:
- Auto-discover tools from this `shared_tools/` directory.
- Optionally load workflow-specific tools from a generated workflow directory
    (e.g. `generated/<workflow>/social_insight_tools.py`) when `workflow_tools_dir`
    is provided.

Tools are discovered via a `register_tools(registry)` function inside modules.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union


class SharedToolsRegistry:
    """Registry for local deterministic tools."""
    
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
    
    def register_tool(self, name: str, func: Callable) -> None:
        """Register a tool with the given name."""
        self._tools[name] = func
    
    def get_tool(self, name: str) -> Callable:
        """Get a tool by name."""
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found in registry")
        return self._tools[name]
    
    def list_tools(self) -> list:
        """List all registered tool names."""
        return sorted(self._tools.keys())
    
    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools


_REGISTRY_CACHE: dict[str, SharedToolsRegistry] = {}


def _load_module_from_path(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(path.stem, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to load module spec: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _register_tools_from_module_path(registry: SharedToolsRegistry, path: Path) -> None:
    try:
        module = _load_module_from_path(path)
    except Exception:
        return
    register_tools = getattr(module, "register_tools", None)
    if callable(register_tools):
        try:
            register_tools(registry)
        except Exception:
            return


def _discover_shared_tool_modules(shared_tools_dir: Path) -> list[Path]:
    modules: list[Path] = []
    for p in sorted(shared_tools_dir.glob("*.py")):
        if p.name in {"__init__.py", "maf_shared_tools_registry.py"}:
            continue
        modules.append(p)
    return modules


def _discover_workflow_tool_modules(workflow_tools_dir: Path) -> list[Path]:
    # Convention: workflow tool modules end with `_tools.py`.
    # Keep it narrow to avoid importing unrelated runtime files.
    modules = sorted(workflow_tools_dir.glob("*_tools.py"))
    return [p for p in modules if p.is_file()]


def get_registry(workflow_tools_dir: Optional[Union[str, Path]] = None) -> SharedToolsRegistry:
    """Get or create a shared tools registry instance.

    Args:
        workflow_tools_dir: Optional directory containing workflow-specific tools
            (e.g. generated/<workflow>/social_insight_tools.py).
    """

    cache_key = str(Path(workflow_tools_dir).resolve()) if workflow_tools_dir else "<shared-only>"
    cached = _REGISTRY_CACHE.get(cache_key)
    if cached is not None:
        return cached

    registry = SharedToolsRegistry()
    shared_tools_dir = Path(__file__).parent

    # Load shared tool modules.
    for module_path in _discover_shared_tool_modules(shared_tools_dir):
        _register_tools_from_module_path(registry, module_path)

    # Load workflow-specific tool modules if provided.
    if workflow_tools_dir:
        wdir = Path(workflow_tools_dir).expanduser().resolve()
        if wdir.exists() and wdir.is_dir():
            for module_path in _discover_workflow_tool_modules(wdir):
                _register_tools_from_module_path(registry, module_path)

    _REGISTRY_CACHE[cache_key] = registry
    return registry


def call_tool(
    tool_name: str,
    args: Optional[dict] = None,
    workflow_tools_dir: Optional[Union[str, Path]] = None,
) -> Any:
    """
    Call a tool by name with the given arguments.
    
    Args:
        tool_name: Name of the tool to call
        args: Dictionary of arguments to pass to the tool
        workflow_tools_dir: Optional workflow-specific tools directory (unused for now)
        
    Returns:
        Result of the tool execution
    """
    registry = get_registry(workflow_tools_dir=workflow_tools_dir)
    tool = registry.get_tool(tool_name)
    return tool(**(args or {}))


def list_tools(workflow_tools_dir: Optional[Union[str, Path]] = None) -> list:
    """
    List all registered tool names.
    
    Args:
        workflow_tools_dir: Optional workflow-specific tools directory (unused for now)
        
    Returns:
        List of tool names
    """
    registry = get_registry(workflow_tools_dir=workflow_tools_dir)
    return registry.list_tools()


if __name__ == "__main__":
    # Allow running as standalone to list tools
    registry = get_registry()
    print("Registered tools:")
    for tool_name in registry.list_tools():
        print(f"  - {tool_name}")
