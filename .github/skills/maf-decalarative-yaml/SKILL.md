---
name: maf-decalarative-yaml
description: >-
  Author, refactor, and validate Microsoft Agent Framework (MAF) declarative YAML (Workflow YAML and Hosted Agent YAML). Use when you need to convert natural-language requirements into a runnable `kind: Workflow` YAML, add/refactor actions (InvokeAzureAgent/Question/ConditionGroup/Foreach/GotoAction/SetTextVariable/SetVariable/SendActivity), generate Hosted Agent `agent.yaml`, or debug YAML loading/execution issues (indentation, Power FX expressions, variable paths, unique action ids).
---

# Goal

Turn “requirements / pseudocode / existing YAML” into MAF-compatible declarative YAML, aligned with the official repo samples and executors.

# Choose YAML type

- Orchestrate multi-step logic with actions: generate **Workflow YAML** (root `kind: Workflow`).
- Define a deployable hosted agent (metadata/resources/env): generate **Hosted Agent YAML** (commonly `agent.yaml`).

# Workflow YAML: minimal skeleton

Generate this structure (pay attention to indentation and `-` list markers):

- Root: `kind: Workflow`
- Trigger: under `trigger:` include at least
  - `kind: OnConversationStart`
  - `id: <workflow_id>`
  - `actions: [ ... ]`

Use templates first:
- [Workflow templates and action snippets](references/workflow_yaml_templates.md)
- [Power FX quick reference](references/powerfx_quickref.md)

# Key rules (common pitfalls)

- Ensure **every action `id` is globally unique** (including nested actions under `conditions[*].actions`, `elseActions`, loops).
- Every action must have `kind` and `id`, plus required fields for that kind (e.g., `InvokeAzureAgent.agent.name`).
- Power FX expressions start with `=` (e.g., `=System.ConversationId`). For multi-line prompts, use YAML block scalars: `|-` or `>`.
- Variable paths: workflow-scope variables use `Local.*`; system variables use `System.*`.
- `Question`: store the result in `property: Local.X` and use `entity.kind` for validation (String/Number/Boolean/DateTime, etc.).

# Common patterns

- **Capture input (hosted)**: `Local.InputTask = System.LastMessage.Text`.
- **Capture input (local runner)**: prefer `Question` (interactive/non-interactive `--set`) or embed text into a `SetTextVariable value: |-` block (see generator output).
- **Persist agent output**: in `InvokeAzureAgent.output` use `messages: Local.SomeMessages` or `responseObject: Local.SomeJson`.
- **Branching**: `ConditionGroup` + `conditions[*].condition` (Power FX) + `elseActions`.
- **Retry/jump**: `GotoAction.actionId` jumps back to a prior action.
- **Multiple threads**: `CreateConversation` into `Local.*ConversationId`, then bind `InvokeAzureAgent.conversationId` to that id.

# Project Convention: `response_id` threaded context (重要)

This repository standardizes on a **Responses API thread** for multi-step LLM work:

- **Canonical thread handle**: the model `response_id`.
- **Propagation rule**: every subsequent call MUST pass the last `response_id` as `previous_response_id`.
- **One run = one thread** (unless explicitly forked): do not mix multiple `previous_response_id` chains within a single logical run.
- **Hard-fail on unsupported threading**: if the SDK/endpoint does not support `previous_response_id`, do not silently downgrade to unthreaded execution.

Relationship to MAF variables:

- `System.ConversationId` / `CreateConversation` is a workflow orchestration concept.
- `response_id`/`previous_response_id` is a model-provider threading concept (Responses API).
- In this repo, when calling the Responses API, `response_id` is the source of truth for LLM continuity even if the workflow also uses `System.ConversationId` for routing.

# Project Convention: Responses API options (temperature 禁用)

When authoring YAML (or hosted agent specs) that will ultimately invoke a **Responses API-backed** client:

- Do NOT include `temperature` / `top_p` / penalties in agent configs or per-call options.
- Prefer passing reasoning options via the SDK/provider-specific option bags:
  - `ChatAgent.additional_chat_options.reasoning = {effort, summary}`
  - `OpenAIChatClient.additional_properties.reasoning = {effort, summary}`
- Defaults used in this repo:
  - `reasoning.summary = "auto"`
  - `reasoning.effort = low|medium|high` (default `low` via env `SIXYAO_LLM_REASONING_EFFORT`)
- Token naming: prefer `max_output_tokens` for Responses API (not `max_tokens`).

# Troubleshooting and quick checks

- YAML fails to load: check root `kind: Workflow`, indentation, and `trigger.kind/id/actions`.
- Variables are empty at runtime: confirm your Power FX is evaluated as an expression (avoid accidental quoting) and variable paths are correct (`Local.` vs `System.`).
- Branch not taken: ensure `ConditionGroup.conditions[*].condition` returns a boolean.
- Quickly detect duplicate ids / missing required fields (optional; requires `pyyaml`):
  - `python .github/skills/maf-decalarative-yaml/scripts/validate_maf_workflow_yaml.py path/to/workflow.yaml`

# Auto-generate a full Workflow YAML from natural language

Use the generator script to turn a requirement into a complete, runnable Workflow YAML that includes:

- Naming conventions (workflow id + action id patterns)
- Auto-generated unique action ids
- A variable table (as YAML comments at the top of the generated file)

Run:

- Print YAML to stdout:
  - `python .github/skills/maf-decalarative-yaml/scripts/generate_workflow_yaml.py --requirement "<your requirement>"`
- Write to file:
  - `python .github/skills/maf-decalarative-yaml/scripts/generate_workflow_yaml.py --requirement "<your requirement>" --out MyWorkflow.yaml`
- Control agent names:
  - `python .github/skills/maf-decalarative-yaml/scripts/generate_workflow_yaml.py --requirement "..." --planner-agent PlannerAgent --executor-agent SummaryAgent`

Notes:

- The generated YAML is a solid “starter workflow”. It assumes the referenced agents exist in your environment.
- If you want a single-agent workflow, pass `--executor-agent <AgentName>` and `--no-planner`.

# Hosted Agent YAML

When you need to define a deployable hosted agent (name/description/tags/protocol/env vars/model resources), use:
- [Hosted Agent templates](references/hosted_agent_yaml_templates.md)

# Align with the official repo (source of truth)

For fidelity, refer to `microsoft/agent-framework`:
- `dotnet/src/Microsoft.Agents.AI.Workflows.Declarative/README.md` (action catalog)
- `workflow-samples/DeepResearch.yaml` (complex orchestration, Power FX, ConditionGroup, GotoAction)
- `dotnet/tests/.../Workflows/*.yaml` (small runnable examples: Condition/InvokeAgent/ConfirmInput)
- `dotnet/samples/HostedAgents/*/agent.yaml` (hosted agent templates)
