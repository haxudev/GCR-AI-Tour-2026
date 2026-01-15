# Shared Tools Contract (LocalToolExecutorAgent)

This repo supports running deterministic local tools from a MAF workflow runner.

## Where tools live

- Registry entrypoint: `shared_tools/maf_shared_tools_registry.py`
- Shared tools: `shared_tools/*.py` (excluding the registry) may export `register_tools(registry)`
- Workflow-specific tools: `generated/<workflow>/*_tools.py` (and `*_tool.py` for compatibility)

Note: The skill-local registry at `.github/skills/maf-shared-tools/examples/maf_shared_tools_registry.py` is kept as an example/shim.

## How the runner calls tools

The workflow uses an `InvokeAzureAgent` action with `agent.name: LocalToolExecutorAgent`.

The prompt MUST be a single JSON object:

```json
{"tool":"<tool-name>","args":{}}
```

Rules:

- `tool` is a string; lookups are exact.
- `args` is a JSON object; it is expanded into keyword arguments.
- Tool results should be JSON-serializable when possible (dict/list/str/number/bool/null).

## Tool naming conventions

Prefer `namespace.verb_noun`:

- `audio.get_audio_duration`
- `audio.merge_audio_files`
- `tts.text_to_speech_ssml`

Avoid ambiguous names that collide across domains.

## Adding a new tool

Preferred (repo convention): create `shared_tools/my_feature_tool.py`:

```python
from typing import Any

def my_tool(x: int) -> dict[str, Any]:
    return {"ok": True, "x": x}

def register_tools(registry: object) -> None:
    register = getattr(registry, "register_tool", None)
    if not callable(register):
        return
    register("my_feature.my_tool", my_tool)

If you need a self-contained example for the skill folder only, you can put the same module under `.github/skills/maf-shared-tools/examples/`.
```

## Podcast / TTS shortcut (TTSExecutorAgent)

Some workflows use `TTSExecutorAgent` for generating a two-speaker podcast mp3.

Prompt is JSON:

```json
{"dialogues":[{"speaker":"male","text":"..."}],"output_file":"output/podcast.mp3"}
```

The runner tries to execute this locally via the registry wrapper `podcast_tts_from_dialogues` when available.

## Local smoke tests

From repo root:

- List tools: `python .github/skills/maf-shared-tools/scripts/call_shared_tool.py --tool __list__`
- Call tool: `python .github/skills/maf-shared-tools/scripts/call_shared_tool.py --tool audio.check_ffmpeg`

## Optional tools: Tavily web search

Canonical implementation: `shared_tools/tavily_web_search_tool.py` (skill folder keeps a copy under `.github/skills/maf-shared-tools/examples/` as an example)

- Install: `pip install tavily-python`
- Env: `TAVILY_API_KEY`

Example:

```json
{"tool":"web.tavily_search","args":{"query":"MAF workflow yaml example","max_results":5,"search_depth":"basic"}}
```

## Optional tools: Image generation

Canonical implementation: `shared_tools/image_generation_tool.py` (skill folder keeps a copy under `.github/skills/maf-shared-tools/examples/` as an example)

- Install: `pip install openai`
- Env: `ENDPOINT` + `KEY` (or `AZURE_OPENAI_ENDPOINT` + `AZURE_OPENAI_API_KEY`)

Example:

```json
{"tool":"image.generate_png","args":{"prompt":"A cute baby polar bear","output_file":"output/polar.png","model":"gpt-image-1"}}
```
