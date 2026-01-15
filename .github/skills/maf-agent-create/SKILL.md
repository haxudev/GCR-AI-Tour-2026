---
name: maf-agent-create
description: >-
  Create Azure AI Foundry agents referenced by a Microsoft Agent Framework (MAF)
  declarative workflow YAML (InvokeAzureAgent.agent.name). Generates a declarative
  agent spec (YAML) and/or creates the agents in a Foundry project via SDK,
  emitting an agent name->id map JSON for use with maf-workflow-gen runners.
---

# Maf Agent Create

## What this skill is for

Use this when your workflow YAML (e.g. [workflows/tech_blog_workflow.yaml](workflows/tech_blog_workflow.yaml)) references agents by name (e.g. `ResearchAgent`, `PlannerAgent`, `WriterAgent`, `EditorAgent`) and you want a repeatable way to:

- Extract required agent names from the workflow
- Generate a small **declarative agent spec** you can edit
- Create missing agents in **Azure AI Foundry**
- Output an **agent name → agent id** map JSON usable by the generated runner (`--azure-ai-agent-id-map-json`)

## Prereqs (Foundry)

- You already authenticated: `az login`
- Your Foundry project endpoint is available as either:
  - env `AZURE_AI_PROJECT_ENDPOINT`, or
  - env `AZURE_EXISTING_AIPROJECT_ENDPOINT` (this repo’s `.env` convention)
- You know a deployed model name (e.g. `gpt-4o-mini`) as `AZURE_AI_MODEL_DEPLOYMENT_NAME` or `--model-deployment-name`

Python deps (venv recommended):

- `pip install -U agent-framework-azure-ai --pre`
  - This typically pulls in `azure-ai-projects` / `azure-identity` needed for creation.

## Quick start

### 1) Generate an editable declarative spec

- `/home/haxu/declarative_workflow/.venv/bin/python .github/skills/maf-agent-create/scripts/create_agents_from_workflow.py \
  --workflow workflows/tech_blog_workflow.yaml \
  --write-spec generated/tech_blog_workflow/agents.yaml`

Edit `generated/tech_blog_workflow/agents.yaml` if you want different instructions per agent.

Spec format reference:

- See [.github/skills/maf-agent-create/references/agent_spec_format.md](.github/skills/maf-agent-create/references/agent_spec_format.md)

### 2) Create / reuse agents in Foundry and write id map

- `/home/haxu/declarative_workflow/.venv/bin/python .github/skills/maf-agent-create/scripts/create_agents_from_workflow.py \
  --workflow workflows/tech_blog_workflow.yaml \
  --model-deployment-name gpt-4o-mini \
  --spec generated/tech_blog_workflow/agents.yaml \
  --write-id-map generated/tech_blog_workflow/agent_id_map.json`

### 3) Run the generated workflow runner using the id map

- `python generated/tech_blog_workflow/run.py --azure-ai --azure-ai-model-deployment-name gpt-4o-mini --azure-ai-agent-id-map-json generated/tech_blog_workflow/agent_id_map.json ...`

## Notes

- Default behavior is **safe**: if an agent name already exists in the Foundry project, the script will **reuse the latest version id** instead of creating duplicates.
- Use `--dry-run` to see what it would do without calling the network.

## Project Convention: `response_id` threaded context (重要)

In this repo, multi-step agentic execution is expected to preserve a **single, linear context thread** when using the **Responses API**:

- Treat each model return `response_id` as the canonical thread handle.
- The next model call MUST pass it as `previous_response_id`.
- Do not silently switch to unthreaded calls when `previous_response_id` is unsupported; fail loudly so the workflow does not produce inconsistent reasoning.

This skill focuses on Foundry agent provisioning, but runners/adapters that invoke these agents MUST follow the above convention to keep multi-stage workflows coherent.

## Project Convention: Responses API call options (temperature 禁用)

Even though some SDK samples show `temperature`, this repo standardizes on **reasoning-compatible** options:

- Do NOT pass `temperature` / `top_p` / `presence_penalty` / `frequency_penalty`.
- Default to `reasoning.summary = "auto"`.
- Default to `reasoning.effort = low|medium|high` (repo default: `low`, via env `SIXYAO_LLM_REASONING_EFFORT`).

Runners/adapters that call Foundry-hosted agents should pass these options via the SDK’s provider-specific fields:

- `ChatAgent(..., additional_chat_options={"reasoning": {"effort": "low", "summary": "auto"}})`
- `OpenAIChatClient.get_response(..., additional_properties={"reasoning": { ... }})`
