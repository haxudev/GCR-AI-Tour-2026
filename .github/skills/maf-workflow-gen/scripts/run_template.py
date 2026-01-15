#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from maf_declarative_runtime import AgentInvoker, DeclarativeWorkflowRunner


try:  # Best-effort: allow loading config from a nearby .env without stack-frame hacks
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


_LLM_REASONING_EFFORT_ENV = "SIXYAO_LLM_REASONING_EFFORT"


def _llm_reasoning_effort() -> str | None:
    """Reasoning effort for supported models/endpoints.

    Values: low|medium|high. Empty/'none' disables passing the parameter.
    Defaults to 'low' to keep responses decisive.
    """

    raw = (os.getenv(_LLM_REASONING_EFFORT_ENV) or "low").strip().lower()
    if raw in {"", "none", "null", "off", "disabled"}:
        return None
    if raw in {"low", "medium", "high"}:
        return raw
    return "low"


def _default_reasoning_options() -> dict[str, Any] | None:
    effort = _llm_reasoning_effort()
    if not effort:
        return None
    return {"summary": "auto", "effort": effort}


class MockAgentInvoker(AgentInvoker):
    def __init__(self) -> None:
        super().__init__(interactive=False)

    def invoke(self, agent_name: str, prompt: str) -> str:
        name = (agent_name or "agent").lower()
        if "research" in name:
            return "Research summary: (mock) Key points, pitfalls, and references TBD."
        if "planner" in name or "outline" in name:
            return """## Outline (mock)

- Intro
- Step-by-step
- Troubleshooting
- Conclusion"""
        if "writer" in name:
            return """# (mock) Technical Blog

## Intro
(mock)

## Step-by-step
(mock)

## Troubleshooting
(mock)

## Conclusion
(mock)"""
        if "editor" in name:
            pattern = r"""Draft [(]Markdown[)]:
(?P<draft>.*?)

Output the improved Markdown only[.]"""
            m = re.search(pattern, prompt, flags=re.DOTALL)
            draft = m.group("draft") if m else ""
            return (draft or "(mock, polished)").replace("(mock)", "(mock, polished)")
        return "(mock)"


class AzureAIFoundryAgentInvoker(AgentInvoker):
    def __init__(
        self,
        *,
        project_endpoint: str,
        agent_id: str | None,
        agent_id_map: dict[str, str] | None,
        model_deployment_name: str,
        interactive: bool,
        auto_resolve_agent_ids: bool,
        verbose: bool,
    ) -> None:
        super().__init__(interactive=interactive)
        self._project_endpoint = project_endpoint
        self._agent_id = agent_id
        self._agent_id_map = dict(agent_id_map or {})
        self._model_deployment_name = model_deployment_name
        self._auto_resolve_agent_ids = auto_resolve_agent_ids
        self._verbose = verbose
        self._resolved_cache: dict[str, str] = {}

    def _resolve_agent_id(self, agent_name: str) -> str | None:
        key = (agent_name or "").strip()
        if not key:
            return self._agent_id

        if key in self._agent_id_map:
            return self._agent_id_map[key]

        if key in self._resolved_cache:
            return self._resolved_cache[key]

        if not self._auto_resolve_agent_ids:
            return self._agent_id

        try:
            from azure.ai.projects import AIProjectClient  # type: ignore
            from azure.identity import DefaultAzureCredential  # type: ignore
        except Exception:
            return self._agent_id

        client = AIProjectClient(
            endpoint=self._project_endpoint,
            credential=DefaultAzureCredential(exclude_interactive_browser_credential=False),
        )
        versions = list(client.agents.list_versions(key, order="desc", limit=1))
        if not versions:
            return self._agent_id

        resolved = getattr(versions[0], "id", None)
        if isinstance(resolved, str) and resolved:
            self._resolved_cache[key] = resolved
            if self._verbose:
                print(f"[AzureAI] Resolved agent '{key}' -> '{resolved}'")
            return resolved

        return self._agent_id

    def invoke(self, agent_name: str, prompt: str) -> str:
        try:
            from agent_framework.azure import AzureAIAgentClient  # type: ignore
            from azure.core.exceptions import IncompleteReadError, ServiceRequestError, ServiceResponseTimeoutError  # type: ignore
            from azure.identity.aio import DefaultAzureCredential  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "Missing dependencies for Azure AI Foundry invocation. "
                "Install with: pip install -U agent-framework-azure-ai --pre"
            ) from exc

        async def _call() -> str:
            async with DefaultAzureCredential(exclude_interactive_browser_credential=False) as credential:
                async with AzureAIAgentClient(
                    project_endpoint=self._project_endpoint,
                    model_deployment_name=(self._model_deployment_name or None),
                    credential=credential,
                    # Streaming responses can take a while; keep read timeout generous.
                    connection_timeout=30,
                    read_timeout=1200,
                ) as client:
                    resolved_id = self._resolve_agent_id(agent_name)

                    if resolved_id:
                        agent = client.create_agent(id=resolved_id)
                    else:
                        agent = client.create_agent(
                            name=agent_name or "Agent",
                            instructions=(
                                "You are a specialized assistant for a workflow step. "
                                "Follow the user's prompt exactly and return only what it requests."
                            ),
                        )
                    async with agent:
                        # Streaming can be flaky on some networks; request non-streaming.
                        # Pass provider-specific reasoning options by default (best-effort).
                        chat_options: dict[str, Any] = {"stream": False}
                        reasoning = _default_reasoning_options()
                        if reasoning is not None:
                            chat_options["reasoning"] = reasoning

                        try:
                            result = await agent.run(prompt, additional_chat_options=chat_options)
                        except Exception as exc:
                            # Some backends may not accept OpenAI Responses-specific fields.
                            if reasoning is None:
                                raise
                            if self._verbose:
                                print(f"[AzureAI] Retrying without reasoning options: {exc}")
                            result = await agent.run(prompt, additional_chat_options={"stream": False})

                        return result.text

        import time

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                try:
                    return asyncio.run(_call())
                except RuntimeError as exc:
                    if "asyncio.run() cannot be called from a running event loop" not in str(exc):
                        raise
                    loop = asyncio.new_event_loop()
                    try:
                        return loop.run_until_complete(_call())
                    finally:
                        loop.close()
            except (ServiceResponseTimeoutError, IncompleteReadError, ServiceRequestError):
                if attempt >= max_attempts:
                    raise
                time.sleep(2.0 * attempt)


class AzureOpenAIResponsesInvoker(AgentInvoker):
    """(Legacy) Invoke Azure OpenAI Responses API via OpenAI SDK.

    Kept for backwards compatibility, but not used by default.
    """

    def __init__(self, *, interactive: bool, verbose: bool) -> None:
        super().__init__(interactive=interactive)
        self._verbose = verbose
        self._previous_response_id: str | None = None
        self._responses_thread: list[str] = []

    def invoke(self, agent_name: str, prompt: str) -> str:
        endpoint = (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip()
        api_key = (os.getenv("AZURE_OPENAI_API_KEY") or "").strip()
        api_version = (os.getenv("AZURE_OPENAI_API_VERSION") or "2024-10-21").strip()
        deployment = (
            (os.getenv("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME") or "").strip()
            or (os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME") or "").strip()
            or (os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME") or "").strip()
            or (os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME") or "").strip()
        )

        if not endpoint or not api_key or not deployment:
            raise RuntimeError(
                "Azure OpenAI Responses invoker is not configured. Set env vars: "
                "AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME "
                "(or AZURE_OPENAI_CHAT_DEPLOYMENT_NAME / AZURE_OPENAI_DEPLOYMENT_NAME)."
            )

        try:
            from openai import AzureOpenAI  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "Missing dependency for Azure OpenAI Responses invocation. Install with: pip install -U openai"
            ) from exc

        client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )

        reasoning = _default_reasoning_options()
        kwargs: dict[str, Any] = {
            "model": deployment,
            "input": [{"role": "user", "content": prompt}],
        }
        if reasoning is not None:
            kwargs["reasoning"] = reasoning
        if self._previous_response_id:
            kwargs["previous_response_id"] = self._previous_response_id

        import time

        max_attempts = 3
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = client.responses.create(**kwargs)
                rid = getattr(resp, "id", None)
                if isinstance(rid, str) and rid:
                    self._previous_response_id = rid
                    self._responses_thread.append(rid)
                    if self._verbose:
                        print(f"[Responses] response_id={rid}")
                else:
                    raise RuntimeError("Responses API did not return a response id")

                text = getattr(resp, "output_text", None)
                if isinstance(text, str) and text.strip():
                    return text.strip()

                output = getattr(resp, "output", None)
                if isinstance(output, list) and output:
                    first = output[0]
                    content = getattr(first, "content", None) if first is not None else None
                    if isinstance(content, list) and content:
                        c0 = content[0]
                        t0 = getattr(c0, "text", None)
                        if isinstance(t0, str) and t0.strip():
                            return t0.strip()

                return ""
            except TypeError as exc:
                # previous_response_id is mandatory for single-threaded workflows.
                if self._previous_response_id:
                    raise RuntimeError(
                        "Responses API client does not accept previous_response_id; cannot enable threaded workflow"
                    ) from exc
                raise
            except Exception as exc:
                last_exc = exc
                if attempt >= max_attempts:
                    break
                time.sleep(2.0 * attempt)

        raise RuntimeError(f"Azure OpenAI Responses invocation failed: {last_exc}")


class AzureResponsesV1Invoker(AgentInvoker):
    """Invoke the OpenAI-compatible Responses API endpoint on Azure.

    - Uses `previous_response_id` to thread context across steps.
    - Does NOT send `api-version`, `temperature`, or other unsupported params.
    - Uses AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY + AZURE_AI_MODEL_DEPLOYMENT_NAME.
    """

    def __init__(self, *, interactive: bool, verbose: bool) -> None:
        super().__init__(interactive=interactive)
        self._verbose = verbose
        self._previous_response_id: str | None = None
        self._responses_thread: list[str] = []

    @staticmethod
    def _responses_url(endpoint: str) -> str:
        base = endpoint.strip().rstrip("/")
        return f"{base}/openai/v1/responses"

    @staticmethod
    def _extract_output_text(payload: dict[str, Any]) -> str:
        t = payload.get("output_text")
        if isinstance(t, str) and t.strip():
            return t.strip()

        output = payload.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        return text.strip()
                    if isinstance(text, dict) and isinstance(text.get("value"), str) and text["value"].strip():
                        return str(text["value"]).strip()

        return ""

    def invoke(self, agent_name: str, prompt: str) -> str:
        try:
            import httpx  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "Missing dependency: httpx. Install with: pip install httpx"
            ) from exc

        endpoint = (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip()
        api_key = (os.getenv("AZURE_OPENAI_API_KEY") or "").strip()
        deployment = (
            (os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME") or "").strip()
            or (os.getenv("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME") or "").strip()
        )
        if not endpoint or not api_key or not deployment:
            raise RuntimeError(
                "Azure Responses (v1) invoker is not configured. Set env vars: "
                "AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_AI_MODEL_DEPLOYMENT_NAME."
            )

        url = self._responses_url(endpoint)
        headers = {
            "api-key": api_key,
            "content-type": "application/json",
        }
        body: dict[str, Any] = {
            "model": deployment,
            "input": [{"role": "user", "content": prompt}],
        }
        if self._previous_response_id:
            body["previous_response_id"] = self._previous_response_id

        import time
        import random

        max_attempts = 8
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                with httpx.Client(timeout=httpx.Timeout(1200.0, connect=30.0)) as client:
                    resp = client.post(url, headers=headers, json=body)

                if resp.status_code in {429, 500, 502, 503, 504}:
                    retry_after = resp.headers.get("retry-after") or resp.headers.get("Retry-After")
                    if retry_after:
                        try:
                            delay = float(str(retry_after).strip())
                        except Exception:
                            delay = 0.0
                    else:
                        delay = 0.0

                    if delay <= 0:
                        delay = min(60.0, 1.5 * (2.0 ** (attempt - 1))) + random.random() * 1.0
                    if self._verbose:
                        print(f"[Responses] HTTP {resp.status_code}, retrying in {delay:.1f}s (attempt {attempt}/{max_attempts})")
                    time.sleep(delay)
                    continue

                if resp.status_code >= 400:
                    snippet = (resp.text or "").strip()
                    if len(snippet) > 800:
                        snippet = snippet[:800] + "..."
                    raise RuntimeError(f"Responses API HTTP {resp.status_code}: {snippet}")

                payload = resp.json()
                if not isinstance(payload, dict):
                    raise RuntimeError("Responses API returned non-object JSON")

                rid = payload.get("id")
                if isinstance(rid, str) and rid:
                    self._previous_response_id = rid
                    self._responses_thread.append(rid)
                    if self._verbose:
                        print(f"[Responses] response_id={rid}")
                else:
                    raise RuntimeError("Responses API did not return a response id")

                return self._extract_output_text(payload)
            except Exception as exc:
                last_exc = exc
                if attempt >= max_attempts:
                    break
                time.sleep(min(20.0, 1.5 * attempt) + random.random() * 0.5)

        raise RuntimeError(f"Azure Responses (v1) invocation failed: {last_exc}")


def _safe_slug(value: str, *, max_len: int = 80) -> str:
    s = (value or "").strip()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "_", s)
    s = s.strip("_-")
    return (s[:max_len] or "podcast")


def _find_repo_root(start: Path) -> Path:
    """Find the repository root from a path within generated/*.

    This makes generated runners resilient to being executed from different working dirs.
    """
    env_root = os.getenv("MAF_REPO_ROOT")
    if env_root:
        p = Path(env_root).expanduser().resolve()
        if p.exists():
            return p

    start = start.resolve()
    if start.is_file():
        start = start.parent
    for p in [start, *start.parents]:
        has_github = (p / ".github").exists()
        has_workflows = (p / "workflows").exists()
        has_shared_tools = (p / "shared_tools").exists()
        has_git = (p / ".git").exists()
        has_python_marker = (p / "pyproject.toml").exists() or (p / "requirements.txt").exists()

        if has_github and (has_workflows or has_shared_tools or has_git or has_python_marker):
            return p
    return start


def _extract_json_object(text: str) -> dict[str, Any]:
    # First, try strict parsing (most tool prompts are pure JSON).
    t = (text or "").strip()
    try:
        obj = json.loads(t)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # Fallback: handle optional ```json fences and leading/trailing chatter.
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"```\s*$", "", t)

    start = t.find("{")
    if start == -1:
        raise ValueError("No JSON object found in script")

    # Find the matching closing brace for the first '{', respecting strings.
    depth = 0
    in_str = False
    esc = False
    end = None
    for i, ch in enumerate(t[start:], start=start):
        if in_str:
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end is None:
        raise ValueError("Unbalanced JSON braces in script")

    candidate = t[start : end + 1]
    return json.loads(candidate)


def _parse_tts_prompt(prompt: str) -> tuple[dict[str, Any], str | None]:
    # Expected to include a JSON object after '解析对话稿JSON:' and a path after '输出文件:'
    p = prompt or ""

    json_obj: dict[str, Any] | None = None
    m = re.search(r"解析对话稿JSON:\s*(\{.*?\})\s*(?:\n\s*2\.|\n\s*2\))", p, flags=re.DOTALL)
    if m:
        json_obj = _extract_json_object(m.group(1))
    else:
        # Fallback: try parsing the whole prompt
        json_obj = _extract_json_object(p)

    out_path = None
    m2 = re.search(r"输出文件:\s*(.+)$", p, flags=re.MULTILINE)
    if m2:
        out_path = m2.group(1).strip().strip('"').strip("'")

    return json_obj, out_path


class LocalSharedToolsInvoker(AgentInvoker):
    def __init__(self, *, repo_root: Path, interactive: bool) -> None:
        super().__init__(interactive=interactive)
        self._repo_root = repo_root
        self._registry_module: Any | None = None
        preferred = repo_root / "shared_tools" / "maf_shared_tools_registry.py"
        fallback = (
            repo_root
            / ".github"
            / "skills"
            / "maf-shared-tools"
            / "examples"
            / "maf_shared_tools_registry.py"
        )
        self._registry_path = preferred if preferred.exists() else fallback

    def _get_registry_module(self) -> Any:
        if self._registry_module is not None:
            return self._registry_module

        if not self._registry_path.exists():
            raise RuntimeError(
                "Shared tools registry not found. "
                "Expected one of: shared_tools/maf_shared_tools_registry.py OR .github/skills/maf-shared-tools/examples/maf_shared_tools_registry.py"
            )

        spec = importlib.util.spec_from_file_location(
            "maf_shared_tools_registry_skill", str(self._registry_path)
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Failed to load registry module spec: {self._registry_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self._registry_module = module
        return module

    def _render_result(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, (dict, list, bool, int, float)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def _invoke_tool(self, tool_name: str, args: dict[str, Any] | None) -> str:
        registry = self._get_registry_module()
        call_tool = getattr(registry, "call_tool", None)
        if not callable(call_tool):
            raise RuntimeError("Registry module missing call_tool")
        result = call_tool(tool_name, args)
        return self._render_result(result)

    def _handle_tool_executor(self, prompt: str) -> str:
        try:
            obj = _extract_json_object(prompt)
        except Exception as exc:
            debug_dir = (self._repo_root / "output" / "_debug").resolve()
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_path = debug_dir / "tool_executor_last_prompt.txt"
            try:
                # Keep a cap to avoid massive dumps in pathological cases.
                debug_path.write_text((prompt or "")[:200_000], encoding="utf-8")
            except Exception:
                pass
            raise RuntimeError(
                f"Failed to parse LocalToolExecutorAgent prompt as JSON. Saved to: {debug_path}"
            ) from exc
        tool = obj.get("tool")
        args = obj.get("args")
        if not isinstance(tool, str) or not tool.strip():
            raise ValueError("Tool call JSON missing non-empty 'tool' string")
        if args is None:
            args_dict: dict[str, Any] | None = None
        else:
            if not isinstance(args, dict):
                raise ValueError("Tool call JSON 'args' must be an object")
            args_dict = args
        return self._invoke_tool(tool.strip(), args_dict)

    def _handle_podcast_tts(self, prompt: str) -> str:
        data, out_path = _parse_tts_prompt(prompt)
        dialogues = data.get("dialogues")
        if not isinstance(dialogues, list) or not dialogues:
            raise ValueError("Script JSON missing non-empty 'dialogues' array")

        topic = str(data.get("title") or "podcast")
        slug = _safe_slug(topic)

        if not out_path:
            out_path = f"./output/podcast_workflow/podcast_{slug}.mp3"

        out_file = Path(out_path)
        if not out_file.is_absolute():
            out_file = (self._repo_root / out_file).resolve()
        out_file.parent.mkdir(parents=True, exist_ok=True)

        male_voice = os.environ.get("AZURE_SPEECH_GUEST_VOICE") or "zh-CN-YunxiNeural"
        female_voice = os.environ.get("AZURE_SPEECH_HOST_VOICE") or "zh-CN-XiaoxiaoNeural"

        # Prefer shared tool registry if present (so tools are reusable across workflows).
        try:
            self._invoke_tool(
                "podcast_tts_from_dialogues",
                {
                    "dialogues": dialogues,
                    "output_file": str(out_file),
                    "male_voice": male_voice,
                    "female_voice": female_voice,
                    "pause_between_speakers_ms": 500,
                },
            )
        except Exception:
            # Fallback: load the skill example TTS module directly.
            tts_path = (
                self._repo_root
                / ".github"
                / "skills"
                / "maf-shared-tools"
                / "examples"
                / "azure_tts_tool.py"
            )
            try:
                spec = importlib.util.spec_from_file_location("azure_tts_tool_skill", str(tts_path))
                if spec is None or spec.loader is None:
                    raise RuntimeError(f"Failed to load module spec: {tts_path}")
                azure_tts_tool = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = azure_tts_tool
                spec.loader.exec_module(azure_tts_tool)
            except Exception as exc:
                raise RuntimeError(
                    "Failed to load Azure TTS example module. "
                    "Expected: .github/skills/maf-shared-tools/examples/azure_tts_tool.py"
                ) from exc

            result = azure_tts_tool.generate_podcast_with_ssml(
                dialogues=dialogues,
                output_file=str(out_file),
                male_voice=male_voice,
                female_voice=female_voice,
                pause_between_speakers_ms=500,
            )
            if not isinstance(result, dict) or result.get("status") != "success":
                raise RuntimeError(f"TTS failed: {result}")

        return str(out_file)

    def invoke(self, agent_name: str, prompt: str) -> str:
        name = (agent_name or "").strip()
        if name == "TTSExecutorAgent":
            return self._handle_podcast_tts(prompt)
        if name == "LocalToolExecutorAgent":
            return self._handle_tool_executor(prompt)
        raise RuntimeError("LocalSharedToolsInvoker only supports TTSExecutorAgent and LocalToolExecutorAgent")


class HybridAgentInvoker(AgentInvoker):
    def __init__(
        self,
        *,
        primary: AgentInvoker | None,
        tts: AgentInvoker,
        interactive: bool,
    ) -> None:
        super().__init__(interactive=interactive)
        self._primary = primary
        self._tts = tts

    def invoke(self, agent_name: str, prompt: str) -> str:
        if (agent_name or "") in {"TTSExecutorAgent", "LocalToolExecutorAgent"}:
            return self._tts.invoke(agent_name, prompt)
        if not self._primary:
            raise RuntimeError("No primary agent invoker configured for non-TTS steps")
        return self._primary.invoke(agent_name, prompt)


def _parse_set_values(items: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid --set value (expected key=value): {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()

        lowered = value.lower()
        if lowered in {"true", "false"}:
            parsed: Any = lowered == "true"
        else:
            try:
                parsed = int(value)
            except Exception:
                try:
                    parsed = float(value)
                except Exception:
                    parsed = value
        result[key] = parsed
    return result


def _parse_agent_id_map(items: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid --azure-ai-agent-id-map value (expected name=id): {item}")
        name, agent_id = item.split("=", 1)
        name = name.strip()
        agent_id = agent_id.strip()
        if not name or not agent_id:
            raise ValueError(f"Invalid --azure-ai-agent-id-map value (empty name or id): {item}")
        result[name] = agent_id
    return result


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a generated MAF declarative workflow locally")
    parser.add_argument("--workflow", default="__WORKFLOW_YAML__", help="Path to workflow YAML")
    parser.add_argument("--non-interactive", action="store_true", help="Fail instead of prompting")
    parser.add_argument("--mock-agents", action="store_true", help="Use mock responses for InvokeAzureAgent")
    parser.add_argument(
        "--azure-ai",
        action="store_true",
        help="Call Azure AI Foundry Agents via agent-framework (requires AZURE_AI_PROJECT_ENDPOINT + AZURE_AI_MODEL_DEPLOYMENT_NAME or explicit flags)",
    )
    # Default invocation mode is Azure Responses v1 (no api-version, no temperature).
    parser.add_argument(
        "--azure-ai-project-endpoint",
        default=(
            os.getenv("AZURE_AI_PROJECT_ENDPOINT")
            or os.getenv("AZURE_EXISTING_AIPROJECT_ENDPOINT")
        ),
        help="Azure AI project endpoint (or env AZURE_AI_PROJECT_ENDPOINT)",
    )
    parser.add_argument(
        "--azure-ai-agent-id",
        default=os.getenv("AZURE_AI_AGENT_ID") or os.getenv("AZURE_EXISTING_AGENT_ID"),
        help="Optional existing agent id (or env AZURE_AI_AGENT_ID / AZURE_EXISTING_AGENT_ID). Note: model deployment name is still required by the SDK.",
    )
    parser.add_argument(
        "--azure-ai-agent-id-map",
        action="append",
        default=[],
        help="Map workflow agent name to Foundry agent id (repeatable): --azure-ai-agent-id-map ResearchAgent=ResearchAgent:2",
    )
    parser.add_argument(
        "--azure-ai-agent-id-map-json",
        default=None,
        help='Path to JSON object mapping agent name to id (example: {"ResearchAgent": "ResearchAgent:2"})',
    )
    parser.add_argument(
        "--azure-ai-model-deployment-name",
        default=os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
        help="Model deployment name (or env AZURE_AI_MODEL_DEPLOYMENT_NAME)",
    )
    parser.add_argument(
        "--no-azure-ai-auto-resolve-agent-ids",
        action="store_true",
        help="Disable auto-resolving agent ids from Foundry by agent name.",
    )
    parser.add_argument(
        "--azure-ai-verbose",
        action="store_true",
        help="Print agent id resolution details.",
    )
    parser.add_argument(
        "--vars-json",
        default=None,
        help='Path to a JSON file providing initial variables (example: {"Local.Topic": "..."})',
    )
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        help="Set a variable before running (repeatable): --set Local.Topic=Hello",
    )
    parser.add_argument(
        "--save-markdown",
        default=None,
        help="Write the final Markdown to a file after execution.",
    )
    parser.add_argument(
        "--save-var",
        default="Local.EditedDraft",
        help="Which workflow variable to save (default: Local.EditedDraft)",
    )
    args = parser.parse_args()

    # Normalize runtime base dir to the repository root.
    # This makes relative paths (e.g., workflows/*.yaml) stable when executing generated runners.
    repo_root = _find_repo_root(Path(__file__).resolve())
    try:
        os.chdir(str(repo_root))
    except Exception:
        pass

    # By default we ship a workflow.yaml next to this runner.
    # Since we chdir(repo_root) above, the plain "workflow.yaml" would otherwise resolve to repo_root/workflow.yaml.
    wf_arg = str(args.workflow)
    wf_candidate = Path(wf_arg).expanduser()
    if wf_arg == "workflow.yaml" and not wf_candidate.is_absolute():
        workflow_path = (Path(__file__).resolve().parent / wf_arg).resolve()
    else:
        workflow_path = wf_candidate.resolve()

    initial_vars: dict[str, Any] = {}
    if args.vars_json:
        payload = json.loads(Path(args.vars_json).expanduser().resolve().read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("--vars-json must contain a JSON object")
        initial_vars.update(payload)
    if args.set:
        initial_vars.update(_parse_set_values(list(args.set)))

    # Provide a deterministic default output directory for workflows that reference Local.RunOutputDir.
    # This avoids accidental writes to absolute paths like `/signals/...` when OutputDir resolves to empty.
    if "Local.RunOutputDir" not in initial_vars:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        folder_slug = _safe_slug(Path(__file__).resolve().parent.name)
        # Prefer repo_root/output/<workflow-folder>/<timestamp>
        # repo_root is computed below; stash the intended suffix for now.
        initial_vars["Local.RunOutputDir"] = str(Path("output") / folder_slug / ts)

    # Workflow defaults should be override-able via --set.
    defaults: dict[str, Any] = {
        "Local.TimeWindowHours": 168,
        "Local.MinHeat": 0,
        "Local.LimitPerQuery": 30,
        "Local.OverallLimit": 120,
        "Local.AnalysisLimit": 80,
        "Local.CandidateK": 8,
        "Local.MaxFetchUrls": 30,

        # ---- Per-step timeout + retry (enforced by maf_declarative_runtime.py) ----
        # Keys are matched in order:
        #   Local.TimeoutSeconds.Action.<action_id>
        #   Local.TimeoutSeconds.Agent.<agent_name>
        #   Local.TimeoutSeconds.Kind.<kind>
        #   Local.TimeoutSeconds.Default
        "Local.TimeoutSeconds.Default": 900,
        "Local.TimeoutSeconds.Kind.InvokeAzureAgent": 900,
        "Local.TimeoutSeconds.Agent.LocalToolExecutorAgent": 900,

        # Retry config (same key precedence as timeout)
        "Local.Retry.MaxAttempts.Default": 2,
        "Local.Retry.MaxAttempts.Kind.InvokeAzureAgent": 3,
        "Local.Retry.MaxAttempts.Agent.LocalToolExecutorAgent": 2,
        "Local.Retry.BackoffBaseSeconds": 2.0,
        "Local.Retry.BackoffMaxSeconds": 30.0,
        "Local.Retry.RetryOnAllErrors": False,
        # In interactive/manual mode, timeouts are disabled by default.
        "Local.TimeoutInteractive": False,
    }
    for k, v in defaults.items():
        initial_vars.setdefault(k, v)

    agent_id_map: dict[str, str] = {}
    if args.azure_ai_agent_id_map_json:
        payload = json.loads(
            Path(args.azure_ai_agent_id_map_json).expanduser().resolve().read_text(encoding="utf-8")
        )
        if not isinstance(payload, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in payload.items()
        ):
            raise ValueError("--azure-ai-agent-id-map-json must be a JSON object of string->string")
        agent_id_map.update(payload)
    if args.azure_ai_agent_id_map:
        agent_id_map.update(_parse_agent_id_map(list(args.azure_ai_agent_id_map)))

    agent_invoker: AgentInvoker | None
    if args.mock_agents:
        agent_invoker = MockAgentInvoker()
    elif args.azure_ai:
        if not args.azure_ai_project_endpoint:
            raise ValueError(
                "Azure AI mode requires --azure-ai-project-endpoint (or env AZURE_AI_PROJECT_ENDPOINT / AZURE_EXISTING_AIPROJECT_ENDPOINT)"
            )
        if not args.azure_ai_model_deployment_name:
            raise ValueError(
                "Azure AI mode requires --azure-ai-model-deployment-name (or env AZURE_AI_MODEL_DEPLOYMENT_NAME)"
            )
        agent_invoker = AzureAIFoundryAgentInvoker(
            project_endpoint=args.azure_ai_project_endpoint,
            agent_id=args.azure_ai_agent_id,
            agent_id_map=agent_id_map,
            model_deployment_name=args.azure_ai_model_deployment_name,
            interactive=not args.non_interactive,
            auto_resolve_agent_ids=not args.no_azure_ai_auto_resolve_agent_ids,
            verbose=bool(args.azure_ai_verbose),
        )
    else:
        agent_invoker = AzureResponsesV1Invoker(
            interactive=not args.non_interactive,
            verbose=bool(args.azure_ai_verbose),
        )

    # Always enable local tools for LocalToolExecutorAgent/TTSExecutorAgent; other steps use selected invoker.
    # If we set a relative default above, make it repo_root-relative.
    rod = initial_vars.get("Local.RunOutputDir")
    if isinstance(rod, str) and rod and not Path(rod).is_absolute():
        initial_vars["Local.RunOutputDir"] = str((repo_root / rod).resolve())
    agent_invoker = HybridAgentInvoker(
        primary=agent_invoker,
        tts=LocalSharedToolsInvoker(repo_root=repo_root, interactive=not args.non_interactive),
        interactive=not args.non_interactive,
    )

    runner = DeclarativeWorkflowRunner.from_yaml(
        workflow_path,
        interactive=not args.non_interactive,
        agent_invoker=agent_invoker,
        initial_vars=initial_vars,
    )
    runner.run()

    if args.save_markdown:
        out_path = Path(args.save_markdown).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        content = _as_text(runner.get_var(args.save_var))
        out_path.write_text(content, encoding="utf-8")
        print(f"\nSaved Markdown to: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
