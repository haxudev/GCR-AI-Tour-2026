---
name: maf-workflow-gen
description: >-
  Convert a Microsoft Agent Framework (MAF) declarative workflow YAML (root kind Workflow,
  trigger.actions) into a runnable local workflow runner (Python). Use when you have a
  workflow YAML like workflows/tech_blog_workflow.yaml and you want an executable artifact
  (generated folder with run.py) for demos/debugging, including support for common action
  kinds (SendActivity/Question/SetTextVariable/InvokeAzureAgent/ConditionGroup/GotoAction/
  EndConversation).
---

# Maf Workflow Gen

## Overview

Generate a self-contained, locally runnable Python artifact from a declarative workflow YAML.

## Quick Start

1) Generate an executable runner folder:

- `python .github/skills/maf-workflow-gen/scripts/generate_executable_workflow.py --in workflows/tech_blog_workflow.yaml --out generated/tech_blog_workflow`

2) Run it:

- `python generated/tech_blog_workflow/run.py`

### Run with Azure AI Foundry (no mock)

Prereqs:

- `az login` already completed
- Install dependencies: `pip install -U agent-framework-azure-ai --pre`
- Provide configuration via env or flags:
  - `AZURE_AI_PROJECT_ENDPOINT` (or this repo’s `.env` uses `AZURE_EXISTING_AIPROJECT_ENDPOINT`)
  - `AZURE_AI_MODEL_DEPLOYMENT_NAME` (required by the SDK even if you also pass an existing agent id)
  - Optional existing agent id: `AZURE_AI_AGENT_ID` / `AZURE_EXISTING_AGENT_ID`

Example (non-interactive, real Foundry calls):

- `python generated/tech_blog_workflow/run.py --non-interactive --azure-ai --azure-ai-model-deployment-name gpt-4o-mini --set Local.Topic=... --set Local.TechStack=... --set Local.AudienceLevel=... --set Local.Language=zh-CN --set Local.WordCount=1200 --set Local.UserApproved=true`

Multi-agent note:

- If your workflow references `ResearchAgent` / `PlannerAgent` / `WriterAgent` / `EditorAgent`, the generated runner can resolve agent IDs by name from the Foundry project (latest version) when running with `--azure-ai`.
- You can also provide explicit mapping: `--azure-ai-agent-id-map ResearchAgent=ResearchAgent:2` (repeatable) or `--azure-ai-agent-id-map-json path/to/map.json`.

Persist output:

- Add `--save-markdown path/to/final.md` (defaults to saving `Local.EditedDraft`; override with `--save-var`).

### Run with Azure OpenAI Responses API (response_id threaded)

Prereqs:

- Install dependency: `pip install -U openai`
- Provide configuration via env:
  - `AZURE_OPENAI_ENDPOINT`
  - `AZURE_OPENAI_API_KEY`
  - `AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME` (preferred; falls back to `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` / `AZURE_OPENAI_DEPLOYMENT_NAME`)
  - Optional: `SIXYAO_LLM_REASONING_EFFORT` (`low`/`medium`/`high`, default `low`; empty/`none` disables passing)

Example (non-interactive, direct Responses API calls with strict `previous_response_id` chaining):

- `python generated/tech_blog_workflow/run.py --non-interactive --azure-openai-responses --set Local.Topic=... --set Local.TechStack=... --set Local.AudienceLevel=... --set Local.Language=zh-CN --set Local.WordCount=1200 --set Local.UserApproved=true`

## What Gets Generated

The generator writes (by default):

- `workflow.yaml`: copied from the input
- `maf_declarative_runtime.py`: lightweight interpreter/runtime for the YAML
- `run.py`: entrypoint that loads `workflow.yaml` and executes it

## Execution Model (important)

- This runner targets local/demo execution and debugging.
- `Question` prompts for input in the terminal and stores into `Local.*` variables.
- `InvokeAzureAgent` is executed in **manual mode** by default: it prints the built prompt and asks you to paste a response; the response is stored into the configured `output.messages` variable.
- For real Azure AI Foundry calls, run the generated `run.py` with `--azure-ai`.

Additional built-in pattern:

- If your workflow invokes `InvokeAzureAgent` with `agent.name: LocalToolExecutorAgent`, the generated runner can execute a local tool from `shared_tools/maf_shared_tools_registry.py` (deterministic, no LLM).
  - Prompt should include a JSON object: `{"tool": "<tool_name>", "args": { ... }}`.

Note:

- `.github/skills/maf-shared-tools/examples/maf_shared_tools_registry.py` is kept as a self-contained example/shim (fallback) for environments that don't have the repo-level `shared_tools/` directory.

To integrate with real agents/LLM calls, replace the default invoker in the generated `run.py` (see `AgentInvoker` hook in the runtime).

## Project Convention: `response_id` as the single context thread (重要)

This repo adopts a **single-threaded context & consistency model** when calling LLMs via the **Responses API**:

- **Definition**: `response_id` is the id returned by a model response (e.g. `resp.id`). The next call MUST pass it as `previous_response_id`.
- **Single thread per run**: Within one workflow execution/run, all multi-stage LLM calls MUST be chained in one linear thread:
  - Keep `prev_response_id` in memory (and/or `Local.*` variables if your runtime supports it).
  - Each stage updates `prev_response_id` with the latest `response_id`.
- **Consistency guarantee**: We rely on the Responses API thread to preserve context across steps, so prompts can stay focused on the current step while remaining coherent end-to-end.
- **Failure semantics**: Do NOT silently drop threading.
  - If the client/endpoint does not accept `previous_response_id`, treat it as a hard error (do not “fallback” into unthreaded calls).
  - If a single step fails, keep the last known-good `prev_response_id` (do not overwrite it with null/empty).
- **Branching/parallel**: If you truly need a separate context, explicitly start a new thread by setting `previous_response_id=None` and track it with a different variable name (e.g. `prev_response_id_validation`).
- **Observability**: Persist a lightweight per-step chain log for debugging (recommended structure: `responses_thread: [{step, response_id}, ...]`).
- **User-facing output**: `response_id` is for correlation/debugging and MUST NOT be shown to end users as part of the divination content.

## Project Convention: Responses API call options (temperature 禁用)

This repo standardizes Responses API request options to stay compatible with **reasoning models** and keep multi-step outputs stable.

- **Do not use sampling knobs**: do NOT pass `temperature` / `top_p` / `presence_penalty` / `frequency_penalty`.
  - Even if a client SDK supports them, reasoning models typically do not.
- **Default reasoning settings** (when supported by your endpoint/SDK):
  - Always request a reasoning summary: `reasoning.summary = "auto"`.
  - Always pass `reasoning.effort` by default: `low|medium|high`.
    - Repo default is `low` via env `SIXYAO_LLM_REASONING_EFFORT`.
    - Set it to empty/`none` to disable passing the parameter.
- **Token limit naming**: for Responses API prefer `max_output_tokens` (not `max_tokens`).
- **Pass provider-specific fields through the official escape hatches**:
  - `ChatAgent(..., additional_chat_options={"reasoning": {"effort": "low", "summary": "auto"}})`
  - `OpenAIChatClient.get_response(..., additional_properties={"reasoning": { ... }})`

## Project Convention: Workflow Observability (可观测性规范建议)

This repo treats “workflow observability” as a first-class capability for:

- Debugging multi-step failures quickly.
- Making regressions visible (prompt/rules drift, model behavior drift).
- Supporting evaluation + offline replay (especially for KB pattern extraction).

### 1) Correlation keys (must-have)

Standardize these identifiers so logs from **runner / backend SSE / tools** can be stitched together:

- `run_id`: one workflow execution. Generated once and reused everywhere.
- `session_id`: optional end-user/session correlation (HTTP header, UI session id, etc.).
- `workflow_id`: workflow trigger id (or file stem if absent).
- `action_id`: the YAML action `id` (must be globally unique).
- `agent_name` / `tool_name`: the invoked agent/tool identity.

Notes:

- The backend SSE contract already uses `run_id`/`session_id` as top-level envelope fields. Keep them consistent with workflow logs.
- Do not expose `response_id` to end users; it is debug-only.

### 2) Event model (recommended)

Emit events in a simple JSON schema that supports both streaming (SSE) and file logs:

- `type`: `run.started` | `run.completed` | `action.started` | `action.completed` | `tool.started` | `tool.completed` | `agent.started` | `agent.completed` | `error`
- `ts`: ISO timestamp
- `seq`: monotonically increasing per run (for stable UI playback)
- `run_id`, `session_id` (optional)
- `workflow_id`, `action_id`
- `ok: boolean` + `duration_ms`
- `data`: small, UI-safe payload (keep it bounded)

When an LLM is involved, add provider-specific fields (best-effort):

- `model` / `deployment`
- `response_id` / `previous_response_id` (Responses API only)
- `usage` (prompt/completion/total tokens)

### 3) Artifacts & folder conventions (local runner)

Use `Local.RunOutputDir` as the single artifact root for one execution.

- Runner default already sets `Local.RunOutputDir` to `output/<workflow-folder>/<timestamp>`.
- All file writes from local tools should prefer paths under `Local.RunOutputDir`.

Recommended artifact layout:

- `events.jsonl`: one JSON event per line (same schema as above).
- `responses_thread.json`: `[{"seq": 1, "action_id": "...", "response_id": "..."}, ...]` for strict Responses API runs.
- `final.md` / `final.json`: final outputs written via `--save-markdown` and/or a workflow-local tool.
- `inputs.json`: sanitized initial variables (omit secrets).

### 4) Redaction / safety rules

- Never write secrets: API keys, bearer tokens, connection strings.
- Prefer storing **hashes** for large prompts rather than full prompt text (unless you are in a secure, local-only debug run).
- Never include `response_id` in divination narrative output; keep it only in logs.
- Keep `data` payloads size-bounded (truncate long text, remove large arrays).

### 5) Responses API threading observability

If you run with `--azure-openai-responses`, treat the `response_id` chain as the canonical “thread timeline”:

- Append `{seq, action_id, response_id}` to `responses_thread`.
- Hard-fail if `previous_response_id` is required but unsupported (do not silently downgrade).

If you run with `--azure-ai` (Foundry Agents), you may not get Responses-style `previous_response_id` semantics. When you need strict `response_id` chaining, prefer `--azure-openai-responses`.

### 6) Batch/offline runs (current repo practice)

For batch processing (e.g., KB pattern runs), prefer per-unit log files under:

- `output/kb_pattern_logs/<source_name>/page_XXX.log`

Each log should include:

- The full command line (`COMMAND:` header)
- Stdout+stderr merged
- Enough context variables (`Local.SourceName`, offsets/limits) to replay the same page deterministically

## Resources

- scripts/
	- `generate_executable_workflow.py`: Generates a runnable folder from YAML
	- `maf_declarative_runtime.py`: Runtime/interpreter used by the generated folder
- references/
	- `declarative_runtime_notes.md`: Supported action kinds and expression notes
