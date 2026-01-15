#!/usr/bin/env python3
"""Image generation tools (optional, skill example).

Dependency (optional):
- pip install openai

Env (examples):
- ENDPOINT / AZURE_OPENAI_ENDPOINT / AZURE_ENDPOINT / OPENAI_BASE_URL
- KEY / AZURE_OPENAI_API_KEY / OPENAI_API_KEY / API_KEY
- API_VERSION (optional, Azure)

Notes:
- Prefers API-key based auth for reliability.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any


def _lazy_import_openai():
    try:
        from openai import AzureOpenAI, OpenAI  # type: ignore
        from openai import NotFoundError  # type: ignore

        return AzureOpenAI, OpenAI, NotFoundError
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("OpenAI SDK not available. Install `openai`.") from exc


def _build_openai_v1_base_url(endpoint: str) -> str:
    ep = endpoint.strip().rstrip("/")
    if ep.endswith("/openai/v1"):
        return ep + "/"
    if ep.endswith("/openai/v1/"):
        return ep
    return ep + "/openai/v1/"


def _resolve_endpoint(explicit: str | None) -> str | None:
    return (
        explicit
        or os.getenv("ENDPOINT")
        or os.getenv("AZURE_OPENAI_ENDPOINT")
        or os.getenv("AZURE_ENDPOINT")
        or os.getenv("OPENAI_BASE_URL")
    )


def _resolve_api_key(explicit: str | None) -> str | None:
    return (
        explicit
        or os.getenv("KEY")
        or os.getenv("AZURE_OPENAI_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("API_KEY")
    )


def generate_image_b64_png(
    prompt: str,
    output_file: str,
    model: str,
    endpoint: str | None = None,
    api_key: str | None = None,
    api_version: str | None = None,
    size: str = "1024x1024",
    n: int = 1,
) -> dict[str, Any]:
    AzureOpenAI, OpenAI, NotFoundError = _lazy_import_openai()

    ep = _resolve_endpoint(endpoint)
    key = _resolve_api_key(api_key)
    if not ep:
        return {"ok": False, "error": "Missing endpoint. Set ENDPOINT/AZURE_OPENAI_ENDPOINT/OPENAI_BASE_URL."}
    if not key:
        return {"ok": False, "error": "Missing api key. Set KEY/AZURE_OPENAI_API_KEY/OPENAI_API_KEY."}

    out = Path(output_file).expanduser()
    if not out.is_absolute():
        out = (Path.cwd() / out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    api_ver = api_version or os.getenv("API_VERSION") or "2025-04-01-preview"
    azure_style = ".azure.com" in ep

    def _call_images(client_obj):
        return client_obj.images.generate(
            model=model,
            prompt=prompt,
            n=int(n),
            size=size,
            response_format="b64_json",
        )

    try:
        if azure_style:
            client = AzureOpenAI(azure_endpoint=ep, api_key=key, api_version=api_ver)
        else:
            client = OpenAI(base_url=_build_openai_v1_base_url(ep), api_key=key)
        img = _call_images(client)
    except NotFoundError:
        client = OpenAI(base_url=_build_openai_v1_base_url(ep), api_key=key)
        img = _call_images(client)

    data0 = (getattr(img, "data", None) or [None])[0]
    b64 = getattr(data0, "b64_json", None) if data0 is not None else None
    if not b64:
        return {"ok": False, "error": "No image data returned (missing b64_json)"}

    image_bytes = base64.b64decode(b64)
    out.write_bytes(image_bytes)

    return {"ok": True, "output_file": str(out), "bytes": len(image_bytes), "model": model, "size": size, "n": int(n)}


def register_tools(registry: object) -> None:
    register = getattr(registry, "register_tool", None)
    if not callable(register):
        return

    register("image.generate_png", generate_image_b64_png)
