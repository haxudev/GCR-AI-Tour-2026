#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Missing dependency: pyyaml. Install with: pip install pyyaml"
        ) from exc

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Root YAML must be a mapping/object")
    return data


def _walk_for_ids(root: Dict[str, Any]) -> List[Tuple[str, str, str, Dict[str, Any]]]:
    results: List[Tuple[str, str, str, Dict[str, Any]]] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            kind = node.get("kind")
            node_id = node.get("id")
            if isinstance(kind, str) and isinstance(node_id, str):
                results.append((path, node_id, kind, node))
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]" if path else f"[{i}]")

    walk(root, "")
    return results


def validate_workflow(doc: Dict[str, Any]) -> List[str]:
    issues: List[str] = []

    if doc.get("kind") != "Workflow":
        issues.append("Root kind should be 'Workflow'.")

    trigger = doc.get("trigger")
    if not isinstance(trigger, dict):
        issues.append("Missing or invalid 'trigger' mapping.")
        return issues

    if trigger.get("kind") is None:
        issues.append("trigger.kind is required (commonly 'OnConversationStart').")
    if trigger.get("id") is None:
        issues.append("trigger.id is required.")

    actions = trigger.get("actions")
    if not isinstance(actions, list):
        issues.append("trigger.actions must be a list.")

    # ID uniqueness across all action-like nodes
    seen: Set[str] = set()
    duplicates: Set[str] = set()
    for path, node_id, kind, node in _walk_for_ids(doc):
        if node_id in seen:
            duplicates.add(node_id)
        else:
            seen.add(node_id)

        # Basic required fields per kind (lightweight heuristics)
        if kind == "InvokeAzureAgent":
            agent = node.get("agent")
            if not (isinstance(agent, dict) and isinstance(agent.get("name"), str) and agent.get("name")):
                issues.append(f"{path or '<root>'}: InvokeAzureAgent requires agent.name")
        if kind == "Question":
            prop = node.get("property")
            if not (isinstance(prop, str) and prop):
                issues.append(f"{path or '<root>'}: Question requires property")

    if duplicates:
        issues.append("Duplicate action ids found: " + ", ".join(sorted(duplicates)))

    return issues


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("Usage: validate_maf_workflow_yaml.py <path/to/workflow.yaml>")
        return 2

    path = Path(argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        return 2

    try:
        doc = _load_yaml(path)
        issues = validate_workflow(doc)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    if issues:
        print("Validation issues:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("OK: no issues found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
