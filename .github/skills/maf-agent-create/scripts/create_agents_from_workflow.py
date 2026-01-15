#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


try:  # best-effort .env support (repo convention)
    from dotenv import load_dotenv  # type: ignore

    def _try_load_dotenv() -> None:
        candidates = [Path.cwd(), Path(__file__).resolve().parent]
        seen: set[Path] = set()
        for base in candidates:
            for p in [base, *base.parents]:
                if p in seen:
                    continue
                seen.add(p)
                env_path = p / ".env"
                if env_path.exists():
                    load_dotenv(str(env_path))
                    return

    _try_load_dotenv()
except Exception:
    pass


@dataclass(frozen=True)
class AgentSpec:
    name: str
    instructions: str


def _load_yaml(path: Path) -> dict[str, Any]:
    import yaml  # type: ignore

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("Workflow YAML root must be a mapping/object")
    return doc


def _iter_actions(node: Any) -> Iterable[dict[str, Any]]:
    if isinstance(node, dict):
        if isinstance(node.get("actions"), list):
            for item in node["actions"]:
                yield from _iter_actions(item)
        if isinstance(node.get("elseActions"), list):
            for item in node["elseActions"]:
                yield from _iter_actions(item)
        if isinstance(node.get("conditions"), list):
            for cond in node["conditions"]:
                yield from _iter_actions(cond)
        # Action-like dicts
        if isinstance(node.get("kind"), str) and isinstance(node.get("id"), str):
            yield node
        return

    if isinstance(node, list):
        for item in node:
            yield from _iter_actions(item)


def extract_agent_names(workflow_doc: dict[str, Any]) -> list[str]:
    trigger = workflow_doc.get("trigger")
    if not isinstance(trigger, dict):
        return []

    ordered: list[str] = []
    seen: set[str] = set()

    for action in _iter_actions(trigger):
        if str(action.get("kind")) != "InvokeAzureAgent":
            continue
        agent_obj = action.get("agent")
        name: str | None = None
        if isinstance(agent_obj, dict) and isinstance(agent_obj.get("name"), str):
            name = agent_obj.get("name")
        if not name:
            continue
        name = str(name).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        ordered.append(name)

    return ordered


def _default_instructions(agent_name: str) -> str:
    n = (agent_name or "Agent").lower()
    if "research" in n:
        return (
            "You are ResearchAgent. Provide accurate technical research. "
            "Do not invent links or claims; clearly label uncertainty."
        )
    if "planner" in n or "outline" in n:
        return (
            "You are PlannerAgent. Create a concise, actionable outline with clear headings. "
            "Prefer step-by-step structure and troubleshooting sections."
        )
    if "writer" in n:
        return (
            "You are WriterAgent. Write high-quality technical Markdown. "
            "Be precise; include runnable code blocks when requested; avoid hallucinating APIs."
        )
    if "editor" in n:
        return (
            "You are EditorAgent. Edit for clarity and correctness. "
            "Preserve technical accuracy; reduce fluff; improve structure; output Markdown only."
        )
    return (
        "You are a specialized assistant for a workflow step. "
        "Follow the prompt and return only what it requests."
    )


def _build_default_spec(agent_names: list[str]) -> list[AgentSpec]:
    return [AgentSpec(name=n, instructions=_default_instructions(n)) for n in agent_names]


def _read_agent_spec_yaml(path: Path) -> list[AgentSpec]:
    import yaml  # type: ignore

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not isinstance(doc.get("agents"), list):
        raise ValueError("Agent spec YAML must be an object with an 'agents' list")

    result: list[AgentSpec] = []
    for item in doc["agents"]:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        instructions = item.get("instructions")
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(instructions, str) or not instructions.strip():
            instructions = _default_instructions(name)
        result.append(AgentSpec(name=name.strip(), instructions=instructions))

    # de-dup while preserving order
    ordered: list[AgentSpec] = []
    seen: set[str] = set()
    for a in result:
        if a.name in seen:
            continue
        seen.add(a.name)
        ordered.append(a)

    return ordered


def _write_agent_spec_yaml(path: Path, specs: list[AgentSpec]) -> None:
    import yaml  # type: ignore

    payload = {
        "agents": [
            {
                "name": s.name,
                "instructions": s.instructions,
            }
            for s in specs
        ]
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _create_or_reuse_agents(
    *,
    project_endpoint: str,
    model_deployment_name: str,
    specs: list[AgentSpec],
    dry_run: bool,
) -> dict[str, str]:
    if dry_run:
        id_map: dict[str, str] = {}
        for spec in specs:
            print(f"[Foundry] Would create or reuse agent '{spec.name}'")
            id_map[spec.name] = "<dry-run>"
        return id_map

    try:
        from azure.ai.projects import AIProjectClient  # type: ignore
        from azure.ai.projects.models import PromptAgentDefinition  # type: ignore
        from azure.identity import DefaultAzureCredential  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Missing dependencies for Foundry agent creation. "
            "Install with: pip install -U agent-framework-azure-ai --pre"
        ) from exc

    client = AIProjectClient(
        endpoint=project_endpoint,
        credential=DefaultAzureCredential(exclude_interactive_browser_credential=False),
    )

    id_map: dict[str, str] = {}
    for spec in specs:
        # Reuse existing agent by name (latest version) if present
        existing_id: str | None = None
        try:
            versions = list(client.agents.list_versions(spec.name, order="desc", limit=1))
            if versions:
                existing_id = getattr(versions[0], "id", None)
        except Exception:
            existing_id = None

        if isinstance(existing_id, str) and existing_id:
            id_map[spec.name] = existing_id
            print(f"[Foundry] Reusing existing agent '{spec.name}' -> {existing_id}")
            continue

        created = client.agents.create(
            name=spec.name,
            definition=PromptAgentDefinition(
                model=model_deployment_name,
                instructions=spec.instructions,
            ),
        )
        created_id = getattr(created, "id", None)
        created_version = getattr(created, "version", None)

        # Some SDK versions return `id` as the agent name (without a version suffix).
        # Normalize to the `name:version` form used by list_versions() and the runner examples.
        if isinstance(created_id, str) and created_id == spec.name and created_version is not None:
            created_id = f"{spec.name}:{created_version}"

        if not isinstance(created_id, str) or not created_id:
            raise RuntimeError(f"Created agent '{spec.name}' but could not read id from response")
        id_map[spec.name] = created_id
        print(f"[Foundry] Created agent '{spec.name}' -> {created_id}")

    return id_map


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Create/reuse Azure AI Foundry agents referenced by a MAF workflow YAML."
    )
    p.add_argument("--workflow", required=True, help="Path to workflow YAML")
    p.add_argument(
        "--project-endpoint",
        default=os.getenv("AZURE_AI_PROJECT_ENDPOINT") or os.getenv("AZURE_EXISTING_AIPROJECT_ENDPOINT"),
        help="Foundry project endpoint (env AZURE_AI_PROJECT_ENDPOINT / AZURE_EXISTING_AIPROJECT_ENDPOINT)",
    )
    p.add_argument(
        "--model-deployment-name",
        default=os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
        help="Model deployment name (env AZURE_AI_MODEL_DEPLOYMENT_NAME)",
    )
    p.add_argument(
        "--spec",
        default=None,
        help="Optional agent spec YAML (generated via --write-spec). If omitted, defaults are used.",
    )
    p.add_argument(
        "--write-spec",
        default=None,
        help="Write a declarative agent spec YAML and exit (no network calls).",
    )
    p.add_argument(
        "--write-id-map",
        default=None,
        help="Write agent name->id JSON mapping (for runner --azure-ai-agent-id-map-json).",
    )
    p.add_argument("--dry-run", action="store_true", help="Print actions without creating agents")
    return p


def main() -> int:
    args = _build_arg_parser().parse_args()

    workflow_path = Path(args.workflow).expanduser().resolve()
    workflow_doc = _load_yaml(workflow_path)

    agent_names = extract_agent_names(workflow_doc)
    if not agent_names:
        print("No InvokeAzureAgent.agent.name entries found in workflow.")
        return 0

    if args.write_spec:
        spec_path = Path(args.write_spec).expanduser().resolve()
        specs = _build_default_spec(agent_names)
        _write_agent_spec_yaml(spec_path, specs)
        print(f"Wrote agent spec: {spec_path}")
        return 0

    specs: list[AgentSpec]
    if args.spec:
        specs = _read_agent_spec_yaml(Path(args.spec).expanduser().resolve())
    else:
        specs = _build_default_spec(agent_names)

    if not args.project_endpoint:
        raise SystemExit(
            "Missing project endpoint. Provide --project-endpoint or set AZURE_AI_PROJECT_ENDPOINT (or AZURE_EXISTING_AIPROJECT_ENDPOINT)."
        )
    if not args.model_deployment_name and not args.dry_run:
        raise SystemExit(
            "Missing model deployment. Provide --model-deployment-name or set AZURE_AI_MODEL_DEPLOYMENT_NAME."
        )

    id_map = _create_or_reuse_agents(
        project_endpoint=str(args.project_endpoint),
        model_deployment_name=str(args.model_deployment_name or ""),
        specs=specs,
        dry_run=bool(args.dry_run),
    )

    if args.write_id_map:
        out_path = Path(args.write_id_map).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(id_map, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote id map JSON: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
