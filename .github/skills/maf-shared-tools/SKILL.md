---
name: maf-shared-tools
description: Define and execute deterministic local Python tools for MAF declarative workflows via the repo-level `shared_tools/` registry (source of truth). The skill-local registry under `.github/skills/maf-shared-tools/examples/` is kept as an example/fallback. Use when a workflow needs reproducible local steps (write files, run ffmpeg audio ops, Azure Speech TTS) executed through LocalToolExecutorAgent/TTSExecutorAgent.
---

# Maf Shared Tools

## Tool Directory Structure

This repository uses a two-tier tool organization:

1. **Shared Tools (`shared_tools/`)**: Generic, reusable tools across all workflows
   - TTS (Azure Speech, CosyVoice)
   - Web fetch/search (Tavily, URL fetch)
   - Data sources (Hacker News, RSS, arXiv, HuggingFace)
   - File operations (write text, write JSON)
   - Image generation

2. **Workflow-Specific Tools (`generated/<workflow>/`)**: Tools tightly coupled to a specific workflow
   - `tech_research_tools.py` in `generated/tech_research_workflow/`
   - `hol_workflow_tools.py` in `generated/hol_workflow/`
   - `ppt_processor_tool.py` in `generated/ppt2video_workflow/`
   - `social_insight_tools.py` in `generated/social_insight_workflow/`
   - `tech_memory_tools.py` in `generated/tech_memory_workflow/`

## Quick start

1) Prefer routing deterministic steps through local tools.

- In workflow YAML, call a local tool via an `InvokeAzureAgent` action where `agent.name` is `LocalToolExecutorAgent`.
- Put the tool call in the prompt as a single JSON object: `{ "tool": "...", "args": { ... } }`.

2) Use the repo tool registry.

- Tool registry entrypoint: `shared_tools/maf_shared_tools_registry.py`
- Shared tool modules: `shared_tools/*.py` (excluding the registry) may expose `register_tools(registry)`.
- Workflow-specific tools: `generated/<workflow>/*_tools.py`

## Call a shared tool from a workflow

Use `LocalToolExecutorAgent` when a step must be reproducible locally (write files, run ffmpeg, generate TTS mp3).

Prompt contract:

- Must be valid JSON
- Top-level keys: `tool` (string), `args` (object)

Example prompt:

```json
{"tool":"write_text_file","args":{"path":"generated/demo/out.txt","text":"hello"}}
```

If the tool returns a dict, store it into a `Local.*` variable via the workflow action output.

## Add a new shared tool

1) Create a module under `shared_tools/<something>_tool.py`.
2) Implement a `register_tools(registry)` function.
3) Register each callable via `registry.register_tool("namespace.tool_name", func)`.

Keep args JSON-serializable (dict/list/str/number/bool/null) so prompts and logs stay stable.

## Add a workflow-specific tool

1) Create or edit the tool file in `generated/<workflow>/<workflow>_tools.py`.
2) Implement a `register_tools(registry)` function.
3) The registry will auto-discover tools from workflow directories when the runner initializes.

## Podcast / TTS special case

Use `TTSExecutorAgent` for the podcast "two speakers" flow.

- Prompt is JSON with `dialogues` and `output_file`.
- Runner routes it to `podcast_tts_from_dialogues` (when available) and produces an mp3.

## Debug / smoke test

Use the bundled CLI script to call tools without generating a workflow:

- `.github/skills/maf-shared-tools/scripts/call_shared_tool.py`

Read the reference for the full JSON contract and examples:

- `.github/skills/maf-shared-tools/references/shared_tools_contract.md`

## Project Convention: `response_id` as the single context thread (重要)

This repo uses `response_id` (from the Responses API) as the **single source of truth** for threaded LLM context within one run.

- Deterministic local tools (this skill) should be treated as **pure functions**: they do not create/modify LLM context and therefore should not reset or fork the `response_id` chain.
- If a tool MUST call an LLM internally, it must:
   - Accept an input `previous_response_id` (or equivalent) and propagate it.
   - Return the latest `response_id` so the caller can continue the same thread.
- Logging/correlation: it is recommended to include `response_id` in tool-run metadata for debugging, but never include it in user-facing narrative output.

When calling an LLM from within a shared tool:

- Prefer the **Responses API** (not legacy chat completions) so the tool can participate in the project’s threaded context model.
- Do NOT pass `temperature` / `top_p` / penalties.
- Default to reasoning options when supported:
   - `reasoning.summary = "auto"`
   - `reasoning.effort = low|medium|high` (repo default: `low` via env `SIXYAO_LLM_REASONING_EFFORT`)

## Optional tool packs

Some tools are shipped as **optional** to avoid increasing install failure rate for the core workflow path.

- Install optional deps: `pip install tavily-python openai`

Available optional tools (when deps are installed):

- Tavily web search: `web.tavily_search`
- Image generation: `image.generate_png`
