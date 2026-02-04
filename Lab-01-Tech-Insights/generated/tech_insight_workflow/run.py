#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import contextlib
import importlib.util
import json
import os
import re
import sys
import random
import inspect
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

        mapped = self._agent_id_map.get(key)
        if isinstance(mapped, str) and mapped.strip():
            return mapped.strip()

        if key in self._resolved_cache:
            return self._resolved_cache[key]

        if not self._auto_resolve_agent_ids:
            return self._agent_id

        try:
            from azure.ai.projects import AIProjectClient  # type: ignore
            from azure.identity import DefaultAzureCredential  # type: ignore
        except Exception:
            return self._agent_id

        # Best-effort: auto-resolve is optional; any failure should fall back to configured agent id.
        client = None
        try:
            client = AIProjectClient(
                endpoint=self._project_endpoint,
                credential=DefaultAzureCredential(exclude_interactive_browser_credential=False),
            )
            versions = list(client.agents.list_versions(key, order="desc", limit=1))
            if not versions:
                return self._agent_id
        except Exception:
            return self._agent_id
        finally:
            try:
                close = getattr(client, "close", None)
                if callable(close):
                    close()
            except Exception:
                pass

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

        # Optional: aiohttp exceptions (agent-framework uses aiohttp under the hood).
        try:  # pragma: no cover
            import aiohttp  # type: ignore

            _AIOHTTP_RETRYABLE: tuple[type[BaseException], ...] = (
                aiohttp.ClientConnectionError,
                aiohttp.ClientPayloadError,
                aiohttp.ServerDisconnectedError,
                aiohttp.ClientOSError,
                aiohttp.ClientResponseError,
            )
        except Exception:  # pragma: no cover
            _AIOHTTP_RETRYABLE = ()

        def _is_retryable(exc: BaseException) -> bool:
            msg = str(exc)
            # Don't retry obvious auth/config issues.
            lowered = msg.lower()
            if any(k in lowered for k in ["unauthorized", "forbidden", "invalidauthentication", "authentication", "credential"]):
                return False
            # Common transient patterns.
            if any(k in msg for k in [
                "TransferEncodingError",
                "Incomplete download",
                "Response payload is not completed",
                "Connection reset by peer",
                "Server disconnected",
            ]):
                return True
            if isinstance(exc, (ConnectionResetError, TimeoutError, asyncio.TimeoutError, OSError)):
                return True
            if _AIOHTTP_RETRYABLE and isinstance(exc, _AIOHTTP_RETRYABLE):
                return True
            return False

        def _coerce_text(result: Any) -> str:
            if result is None:
                return ""
            if isinstance(result, str):
                return result
            text = getattr(result, "text", None)
            if isinstance(text, str):
                return text
            if isinstance(result, dict) and isinstance(result.get("text"), str):
                return str(result["text"])
            return str(result)

        async def _maybe_await(value: Any) -> Any:
            if inspect.isawaitable(value):
                return await value
            return value

        async def _run_agent_handle(agent_handle: Any, prompt_text: str) -> str:
            async def _run_on(handle: Any) -> str:
                run_fn = getattr(handle, "run", None)
                if callable(run_fn):
                    res = run_fn(prompt_text, additional_chat_options={"stream": False})
                    res = await _maybe_await(res)
                    return _coerce_text(res)

                invoke_fn = getattr(handle, "invoke", None)
                if callable(invoke_fn):
                    res = invoke_fn(prompt_text)
                    res = await _maybe_await(res)
                    return _coerce_text(res)

                raise AttributeError("Agent handle has no runnable method (run/invoke)")

            # Prefer running directly; many handles are already runnable.
            try:
                return await _run_on(agent_handle)
            except AttributeError:
                pass

            # Some SDKs return an async context manager for an agent handle.
            aenter = getattr(agent_handle, "__aenter__", None)
            if callable(aenter) and inspect.iscoroutinefunction(aenter):
                inner_result: str | None = None
                try:
                    async with agent_handle as entered:
                        inner_result = await _run_on(entered)
                except RecursionError as exc:
                    if inner_result is not None:
                        if self._verbose:
                            print(f"[AzureAI] WARNING: suppressed RecursionError during agent handle shutdown: {exc}")
                        return inner_result
                    raise
                return inner_result

            enter = getattr(agent_handle, "__enter__", None)
            if callable(enter):
                inner_result2: str | None = None
                try:
                    with agent_handle as entered:  # type: ignore[func-returns-value]
                        inner_result2 = await _run_on(entered)
                except RecursionError as exc:
                    if inner_result2 is not None:
                        if self._verbose:
                            print(f"[AzureAI] WARNING: suppressed RecursionError during agent handle shutdown: {exc}")
                        return inner_result2
                    raise
                return inner_result2

            raise AttributeError("Agent handle has no runnable method (run/invoke) and is not a context manager")

        async def _call() -> str:
            async with DefaultAzureCredential(exclude_interactive_browser_credential=False) as credential:
                result_text: str | None = None
                try:
                    async with AzureAIAgentClient(
                        project_endpoint=self._project_endpoint,
                        model_deployment_name=(self._model_deployment_name or None),
                        credential=credential,
                        # Streaming responses can take a while; keep read timeout generous.
                        connection_timeout=30,
                        read_timeout=1200,
                    ) as client:
                        resolved_id = self._resolve_agent_id(agent_name)

                        instructions = (
                            "You are a specialized assistant for a workflow step. "
                            "Follow the user's prompt exactly and return only what it requests."
                        )

                        # agent-framework versions may differ: some expose client.create_agent(), others expose
                        # a different API. Try the most specific path first, then fall back.
                        agent_handle: Any | None = None

                        create_agent = getattr(client, "create_agent", None)
                        if callable(create_agent):
                            if resolved_id:
                                agent_handle = create_agent(id=resolved_id)
                            else:
                                agent_handle = create_agent(name=agent_name or "Agent", instructions=instructions)
                        else:
                            # Alternative naming patterns.
                            if resolved_id:
                                for getter_name in ["get_agent", "agent", "load_agent"]:
                                    getter = getattr(client, getter_name, None)
                                    if not callable(getter):
                                        continue
                                    try:
                                        agent_handle = getter(id=resolved_id)
                                    except TypeError:
                                        agent_handle = getter(resolved_id)
                                    if agent_handle is not None:
                                        break

                        if agent_handle is not None:
                            result_text = await _run_agent_handle(agent_handle, prompt)
                            return result_text

                        # Final fallback: run directly on client if supported.
                        client_run = getattr(client, "run", None)
                        if callable(client_run):
                            # Best-effort parameter binding across versions.
                            for kwargs in [
                                {"prompt": prompt, "agent_id": resolved_id, "additional_chat_options": {"stream": False}},
                                {"prompt": prompt, "agent": resolved_id, "additional_chat_options": {"stream": False}},
                                {"prompt": prompt, "agent_name": agent_name, "additional_chat_options": {"stream": False}},
                                {"prompt": prompt},
                            ]:
                                try:
                                    res = client_run(**{k: v for k, v in kwargs.items() if v is not None})
                                    res = await _maybe_await(res)
                                    result_text = _coerce_text(res)
                                    return result_text
                                except TypeError:
                                    continue

                        raise AttributeError(
                            "AzureAIAgentClient API mismatch: missing create_agent (and no compatible fallback like get_agent/run). "
                            "Pin compatible versions of agent-framework and agent-framework-azure-ai, or update the runner to match the installed SDK."
                        )
                except RecursionError as exc:
                    # Known issue in some azure/agent-framework versions: close() can recurse.
                    if result_text is not None:
                        if self._verbose:
                            print(f"[AzureAI] WARNING: suppressed RecursionError during client shutdown: {exc}")
                        return result_text
                    raise

        import time

        max_attempts = 5
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
            except KeyboardInterrupt:
                raise
            except (ServiceResponseTimeoutError, IncompleteReadError, ServiceRequestError) as exc:
                if attempt >= max_attempts:
                    raise
                delay = min(30.0, (2.0**attempt) + random.random())
                if self._verbose:
                    print(f"[AzureAI] transient error (attempt {attempt}/{max_attempts}): {exc} -> retry in {delay:.1f}s")
                time.sleep(delay)
            except Exception as exc:
                if attempt >= max_attempts or not _is_retryable(exc):
                    raise
                delay = min(30.0, (2.0**attempt) + random.random())
                if self._verbose:
                    print(f"[AzureAI] transient error (attempt {attempt}/{max_attempts}): {exc} -> retry in {delay:.1f}s")
                time.sleep(delay)


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
    start = start.resolve()
    if start.is_file():
        start = start.parent
    for p in [start, *start.parents]:
        # This repo may not have requirements.txt / pyproject.toml.
        # Prefer stable markers that exist in this workspace.
        if (p / "shared_tools").is_dir():
            return p
        if (p / ".git").exists():
            return p
        if (p / ".github").exists() and ((p / "generated").is_dir() or (p / "workflows").is_dir()):
            return p
    return start


def _extract_json_object(text: str) -> dict[str, Any]:
    # Robust extraction: handle optional ```json fences and leading/trailing chatter.
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"```\s*$", "", t)

    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in script")

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
        # Ensure workflow-specific tools (e.g. social_insight_tools.py) are discoverable.
        result = call_tool(tool_name, args, workflow_tools_dir=Path(__file__).resolve().parent)
        return self._render_result(result)

    def _handle_tool_executor(self, prompt: str) -> str:
        obj = _extract_json_object(prompt)
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
    parser.add_argument("--workflow", default="workflow.yaml", help="Path to workflow YAML")
    parser.add_argument("--non-interactive", action="store_true", help="Fail instead of prompting")
    parser.add_argument("--mock-agents", action="store_true", help="Use mock responses for InvokeAzureAgent")
    parser.add_argument(
        "--azure-ai",
        action="store_true",
        help="Call Azure AI Foundry Agents via agent-framework (requires AZURE_AI_PROJECT_ENDPOINT + AZURE_AI_MODEL_DEPLOYMENT_NAME or explicit flags)",
    )
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
        default="Local.FinalMarkdown",
        help="Which workflow variable to save (default: Local.FinalMarkdown)",
    )
    args = parser.parse_args()

    # Convention (Plan B): keep agent id map next to the generated runner.
    # If the user didn't specify a map file explicitly, auto-load it when present.
    if args.azure_ai_agent_id_map_json is None:
        default_map = Path(__file__).resolve().parent / "agent_id_map.json"
        if default_map.exists():
            args.azure_ai_agent_id_map_json = str(default_map)

    workflow_path = Path(args.workflow)
    if not workflow_path.is_absolute():
        workflow_path = Path(__file__).resolve().parent / workflow_path
    workflow_path = workflow_path.resolve()

    initial_vars: dict[str, Any] = {}
    if args.vars_json:
        payload = json.loads(Path(args.vars_json).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("--vars-json must contain a JSON object")
        initial_vars.update(payload)
    if args.set:
        initial_vars.update(_parse_set_values(list(args.set)))

    # Provide a deterministic default output directory for workflows that reference Local.RunOutputDir.
    # This avoids accidental writes to absolute paths like `/signals/...` when OutputDir resolves to empty.
    if "Local.RunOutputDir" not in initial_vars:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        # Prefer repo_root/output/<timestamp>
        # repo_root is computed below; stash the intended suffix for now.
        initial_vars["Local.RunOutputDir"] = str(Path("output") / ts)

    agent_id_map: dict[str, str] = {}
    if args.azure_ai_agent_id_map_json:
        payload = json.loads(Path(args.azure_ai_agent_id_map_json).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in payload.items()
        ):
            raise ValueError("--azure-ai-agent-id-map-json must be a JSON object of string->string")
        # Ignore empty values so they don't block auto-resolve-by-name.
        agent_id_map.update({k: v.strip() for k, v in payload.items() if isinstance(v, str) and v.strip()})
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
        agent_invoker = None

    # Always enable local tools for LocalToolExecutorAgent/TTSExecutorAgent; other steps use selected invoker.
    repo_root = _find_repo_root(Path(__file__).resolve())
    try:
        os.chdir(str(repo_root))
    except Exception:
        pass

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
