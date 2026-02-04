#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import yaml


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _dump_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def _walk(obj: Any) -> list[Any]:
    out: list[Any] = [obj]
    if isinstance(obj, dict):
        for v in obj.values():
            out.extend(_walk(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_walk(v))
    return out


def _extract_agent_names_from_workflow(workflow: Any) -> list[str]:
    names: list[str] = []
    for node in _walk(workflow):
        if not isinstance(node, dict):
            continue
        if node.get("kind") != "InvokeAzureAgent":
            continue
        agent = node.get("agent")
        if not isinstance(agent, dict):
            continue
        name = agent.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())

    # Preserve order, de-dupe
    seen: set[str] = set()
    deduped: list[str] = []
    for n in names:
        if n in seen:
            continue
        seen.add(n)
        deduped.append(n)
    return deduped


def _ensure_spec(spec_path: Path, *, agent_names: list[str]) -> dict[str, Any]:
    default_instructions = (
        "You are a specialized assistant for a workflow step. "
        "Follow the prompt and return only what it requests."
    )

    spec: dict[str, Any]
    if spec_path.exists():
        spec_loaded = _load_yaml(spec_path)
        if isinstance(spec_loaded, dict):
            spec = spec_loaded
        else:
            spec = {}
    else:
        spec = {}

    agents = spec.get("agents")
    if not isinstance(agents, list):
        agents = []

    by_name: dict[str, dict[str, Any]] = {}
    for item in agents:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            by_name[name.strip()] = item

    changed = False
    for name in agent_names:
        if name not in by_name:
            by_name[name] = {"name": name, "instructions": default_instructions}
            changed = True

    # Keep a stable order: workflow order first, then any extras already in the spec.
    ordered: list[dict[str, Any]] = []
    for name in agent_names:
        ordered.append(by_name[name])
    for name, item in by_name.items():
        if name not in agent_names:
            ordered.append(item)

    spec["agents"] = ordered

    if changed or not spec_path.exists():
        _dump_yaml(spec_path, spec)

    return spec


def _create_or_reuse_agents_and_write_id_map(
    *,
    project_endpoint: str,
    model_deployment_name: str,
    spec: dict[str, Any],
    id_map_path: Path,
) -> dict[str, str]:
    try:
        from azure.ai.projects import AIProjectClient  # type: ignore
        from azure.ai.projects.models import PromptAgentDefinition  # type: ignore
        from azure.core.exceptions import ResourceNotFoundError  # type: ignore
        from azure.identity import DefaultAzureCredential  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Missing Azure dependencies. Install with requirements.txt (azure-ai-projects, azure-identity)."
        ) from exc

    agents = spec.get("agents")
    if not isinstance(agents, list):
        raise ValueError("Invalid spec: expected top-level 'agents: [...]'")

    credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)
    client = AIProjectClient(endpoint=project_endpoint, credential=credential)

    try:
        id_map: dict[str, str] = {}
        for item in agents:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            name = name.strip()
            instructions = item.get("instructions")
            if not isinstance(instructions, str) or not instructions.strip():
                instructions = (
                    "You are a specialized assistant for a workflow step. "
                    "Follow the user's prompt exactly and return only what it requests."
                )

            details = None
            try:
                details = client.agents.get(name)
            except ResourceNotFoundError:
                details = client.agents.create(
                    name=name,
                    definition=PromptAgentDefinition(
                        model=model_deployment_name,
                        instructions=instructions,
                    ),
                )

            latest = getattr(getattr(details, "versions", None), "latest", None)
            latest_id = getattr(latest, "id", None)

            if not isinstance(latest_id, str) or not latest_id:
                # Fallback to listing versions
                versions = list(client.agents.list_versions(name, order="desc", limit=1))
                latest_id = getattr(versions[0], "id", None) if versions else None

            if not isinstance(latest_id, str) or not latest_id:
                raise RuntimeError(f"Failed to resolve agent version id for: {name}")

            id_map[name] = latest_id

        id_map_path.parent.mkdir(parents=True, exist_ok=True)
        id_map_path.write_text(json.dumps(id_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return id_map
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create/reuse Azure AI Foundry agents from a workflow and write agent id map.")
    parser.add_argument("--workflow", required=True, help="Path to workflow YAML (e.g. workflows/social_insight_workflow.yaml)")
    parser.add_argument("--spec", required=True, help="Path to agents spec YAML to create/update")
    parser.add_argument("--write-id-map", required=True, help="Path to write agent_id_map.json")
    args = parser.parse_args()

    workflow_path = Path(args.workflow)
    spec_path = Path(args.spec)
    id_map_path = Path(args.write_id_map)

    project_endpoint = os.environ.get("AZURE_AI_PROJECT_ENDPOINT", "").strip()
    if not project_endpoint:
        raise SystemExit("Missing env AZURE_AI_PROJECT_ENDPOINT")

    model_deployment_name = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5-mini").strip() or "gpt-5-mini"

    workflow = _load_yaml(workflow_path)
    agent_names = _extract_agent_names_from_workflow(workflow)
    if not agent_names:
        raise SystemExit(f"No agents found in workflow: {workflow_path}")

    spec = _ensure_spec(spec_path, agent_names=agent_names)

    id_map = _create_or_reuse_agents_and_write_id_map(
        project_endpoint=project_endpoint,
        model_deployment_name=model_deployment_name,
        spec=spec,
        id_map_path=id_map_path,
    )

    print(f"Wrote agent id map: {id_map_path}")
    print(f"Agents: {', '.join(sorted(id_map.keys()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
