#!/usr/bin/env python3
"""Social insight workflow local tools.

Discovered by shared_tools/maf_shared_tools_registry.py via register_tools(registry).

Note: This is a workflow-specific tool file located in generated/social_insight_workflow/.

Goals:
- Read multi-platform hot API list from input/api/hot_api_list.txt.
- Fetch each API endpoint (best-effort, tolerant to schema differences).
- Normalize into a comparable, structured signal list.
- Provide deterministic fallbacks for clustering/insight/report when LLM output is
  missing/invalid (e.g., --mock-agents mode).
"""

from __future__ import annotations

import json
import re
import ssl
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable


# ----------------------------
# Utilities
# ----------------------------


def _abs_path(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    return p


def _read_lines(path: str) -> list[str]:
    p = _abs_path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    lines: list[str] = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        lines.append(s)
    return lines


def _extract_first_json(text: str) -> Any:
    """Best-effort extraction of the first JSON value (object/array) from text."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"```\s*$", "", t)

    # Find first '{' or '[' and then bracket-match.
    starts = [i for i in [t.find("{"), t.find("[")] if i != -1]
    if not starts:
        raise ValueError("No JSON found")
    start = min(starts)
    open_ch = t[start]
    close_ch = "}" if open_ch == "{" else "]"

    depth = 0
    in_string = False
    escape_next = False
    end = -1
    for i in range(start, len(t)):
        ch = t[i]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        raise ValueError("No complete JSON found")

    return json.loads(t[start : end + 1])


def _as_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    # Accept numbers like "12.3万" -> keep as None (unknown scale)
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", s):
        try:
            return float(s)
        except Exception:
            return None
    return None


def _infer_platform(url: str) -> tuple[str, str]:
    u = (url or "").strip().lower()
    key = re.sub(r"[^a-z0-9]+", "_", u)
    if "douyin" in u:
        return "抖音", "douyin"
    if "weibo" in u:
        return "微博", "weibo"
    if "baidu" in u:
        return "百度", "baidu"
    if "csdn" in u:
        return "CSDN", "csdn"
    if "36kr" in u or "hot36kr" in u:
        return "36氪", "36kr"
    if "bilibili" in u:
        return "哔哩哔哩", "bilibili"
    # Fallback: use hostname.
    try:
        host = urllib.parse.urlparse(u).hostname or "unknown"
    except Exception:
        host = "unknown"
    host = host.lower()
    return host, host


def _normalize_url(url: str) -> str:
    """Return a URL safe for urllib (ASCII-only, properly percent-encoded).

    Some APIs in input/api/hot_api_list.txt include non-ASCII query params
    (e.g., title=知乎). urllib may attempt ASCII encoding and fail unless
    the URL is percent-encoded.
    """

    u = (url or "").strip()
    if not u:
        return u
    try:
        parts = urllib.parse.urlsplit(u)
    except Exception:
        return u

    # Encode path while preserving typical URL reserved chars.
    path = urllib.parse.quote(parts.path or "", safe="/@:+-._~!$&'()*;,=")

    # Normalize query: decode to key/value pairs, then re-encode as UTF-8.
    query = parts.query or ""
    if query:
        try:
            qsl = urllib.parse.parse_qsl(query, keep_blank_values=True)
            query = urllib.parse.urlencode(qsl, doseq=True, encoding="utf-8")
        except Exception:
            # If anything goes wrong, fall back to quoting non-ASCII.
            query = urllib.parse.quote(query, safe="=&%:+-._~!$'()*;,/")

    fragment = urllib.parse.quote(parts.fragment or "", safe="")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, fragment))


def _parse_hot_number(value: Any) -> float | None:
    """Parse common hotness formats.

    Supports:
    - numeric types
    - numeric strings
    - Chinese units like "110万", "1.2亿"
    - common suffixes like "w"/"k" (best-effort)
    """

    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip()
    if not s:
        return None

    # Plain number.
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", s):
        try:
            return float(s)
        except Exception:
            return None

    m = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)(\s*)(万|亿|千|百)", s)
    if m:
        num = float(m.group(1))
        unit = m.group(3)
        mul = {"百": 100.0, "千": 1000.0, "万": 10000.0, "亿": 100000000.0}.get(unit, 1.0)
        return num * mul

    m = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)(\s*)(k|m|b|w)", s, flags=re.IGNORECASE)
    if m:
        num = float(m.group(1))
        unit = m.group(3).lower()
        mul = {"k": 1000.0, "m": 1000000.0, "b": 1000000000.0, "w": 10000.0}.get(unit, 1.0)
        return num * mul

    return None


def _fetch_url(
    url: str,
    *,
    timeout_seconds: int,
    max_chars: int,
    retries: int = 2,
    retry_backoff_seconds: float = 1.0,
) -> dict[str, Any]:
    u = _normalize_url(url)
    if not u:
        return {"ok": False, "error": "empty url"}

    req = urllib.request.Request(
        u,
        headers={
            "User-Agent": "vibe-workflows-social-insight/1.0",
            "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
        },
        method="GET",
    )
    ctx = ssl.create_default_context()

    last_error: str | None = None
    attempts = max(1, int(retries) + 1)
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=float(timeout_seconds), context=ctx) as resp:
                status = getattr(resp, "status", None)
                ctype = resp.headers.get("Content-Type")
                raw = resp.read()
            encoding = "utf-8"
            if ctype and "charset=" in ctype.lower():
                try:
                    encoding = ctype.split("charset=", 1)[1].split(";", 1)[0].strip()
                except Exception:
                    encoding = "utf-8"
            text = raw.decode(encoding, errors="replace")
            truncated = False
            if max_chars and len(text) > int(max_chars):
                text = text[: int(max_chars)]
                truncated = True
            return {
                "ok": True,
                "url": u,
                "status": status,
                "content_type": ctype,
                "text": text,
                "truncated": truncated,
                "bytes": len(raw),
                "attempts": attempt,
            }
        except HTTPError as exc:
            # HTTPError is a file-like object; best-effort read for debugging.
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            last_error = f"HTTP {getattr(exc, 'code', None)}: {str(exc)}"
            if body:
                last_error = last_error + f"; body={body[:300]}"
        except (URLError, TimeoutError) as exc:
            last_error = str(exc)
        except Exception as exc:
            last_error = str(exc)

        if attempt < attempts:
            # Small linear backoff.
            try:
                import time

                time.sleep(float(retry_backoff_seconds) * float(attempt))
            except Exception:
                pass

    return {"ok": False, "url": u, "error": last_error or "fetch failed", "attempts": attempts}


def _extract_items(obj: Any) -> list[dict[str, Any]]:
    """Extract a best-effort list of item dicts from an arbitrary API payload."""
    if obj is None:
        return []
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if not isinstance(obj, dict):
        return []

    # Common container keys.
    for key in ["data", "result", "results", "list", "items"]:
        v = obj.get(key)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
        if isinstance(v, dict):
            # sometimes nested: data.list
            for k2 in ["list", "items", "data", "result", "results"]:
                v2 = v.get(k2)
                if isinstance(v2, list):
                    return [x for x in v2 if isinstance(x, dict)]

    # Deep-ish fallback: BFS search for first list-of-dicts.
    queue: list[tuple[Any, int]] = [(obj, 0)]
    seen: set[int] = set()
    while queue:
        cur, depth = queue.pop(0)
        if id(cur) in seen:
            continue
        seen.add(id(cur))
        if depth > 4:
            continue
        if isinstance(cur, dict):
            for v in cur.values():
                if isinstance(v, list) and v and all(isinstance(x, dict) for x in v[: min(5, len(v))]):
                    return [x for x in v if isinstance(x, dict)]
                if isinstance(v, (dict, list)):
                    queue.append((v, depth + 1))
        elif isinstance(cur, list):
            for v in cur[:20]:
                if isinstance(v, (dict, list)):
                    queue.append((v, depth + 1))

    return []


def _deep_get_first_string(obj: Any, keys: Iterable[str]) -> str | None:
    """Find the first non-empty string value by keys, searching a few levels."""
    keyset = {k for k in keys}
    queue: list[tuple[Any, int]] = [(obj, 0)]
    seen: set[int] = set()
    while queue:
        cur, depth = queue.pop(0)
        if id(cur) in seen:
            continue
        seen.add(id(cur))
        if depth > 4:
            continue
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k in keyset and isinstance(v, str) and v.strip():
                    return v.strip()
                if isinstance(v, (dict, list)):
                    queue.append((v, depth + 1))
        elif isinstance(cur, list):
            for v in cur[:20]:
                if isinstance(v, (dict, list)):
                    queue.append((v, depth + 1))
    return None


def _pick_title(item: dict[str, Any]) -> str:
    direct = _deep_get_first_string(
        item,
        [
            "title",
            "widgetTitle",
            "articleTitle",
            "name",
            "word",
            "keyword",
            "hotword",
            "desc",
            "summary",
            "topic",
            "tag",
        ],
    )
    if direct:
        return direct
    # As a last resort, stringify small dict.
    return str(item)[:200]


def _pick_url(item: dict[str, Any]) -> str | None:
    direct = _deep_get_first_string(item, ["url", "link", "href", "mobileUrl", "shareUrl", "jumpUrl"])
    if direct:
        return direct

    # 36kr: common fields.
    item_id = item.get("itemId")
    if isinstance(item_id, (int, str)) and str(item_id).strip():
        return f"https://www.36kr.com/p/{str(item_id).strip()}"

    route = item.get("route")
    if isinstance(route, str) and "itemid=" in route.lower():
        try:
            parsed = urllib.parse.urlparse("https://www.36kr.com/" + route.lstrip("/"))
            qs = urllib.parse.parse_qs(parsed.query)
            iid = (qs.get("itemId") or qs.get("itemid") or [None])[0]
            if iid:
                return f"https://www.36kr.com/p/{iid}"
        except Exception:
            pass

    return None


def _pick_hot_raw(item: dict[str, Any]) -> Any:
    for k in ["hot", "heat", "score", "hotValue", "hot_value", "views", "read", "readCount", "rank"]:
        if k in item:
            return item.get(k)
    return None


def _normalize_title(title: str) -> str:
    s = (title or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    # Remove obvious decoration / punctuation.
    s = re.sub(r"[\u3000\s\t\r\n]+", " ", s)
    s = re.sub(r"[\[\]【】()（）<>《》“”\"'`·•,，.。!！?？:：;；|/\\]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _similar(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _is_trivial_mock(text: str) -> bool:
    t = (text or "").strip().lower()
    return (not t) or t in {"(mock)", "mock", "(mock)"} or "(mock" in t


# ----------------------------
# Step 0: Fetch and save raw signals to disk
# ----------------------------


def social_fetch_all_to_disk(
    api_list_path: str = "input/api/hot_api_list.json",
    output_dir: str = "output/social_insight_workflow/signals",
    timeout_seconds: int = 15,
    max_chars: int = 200_000,
) -> dict[str, Any]:
    """Read hot API list (JSON), fetch each API, save raw response to {output_dir}/{platform}.json.

    Returns summary of fetched files and any errors.
    """
    import time

    api_list_file = _abs_path(api_list_path)
    if not api_list_file.exists():
        return {"ok": False, "error": f"API list file not found: {api_list_file}"}

    try:
        payload = json.loads(api_list_file.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "error": f"Failed to parse API list JSON: {exc}"}

    # Accept either:
    # - a JSON array of {platform,url,...}
    # - an object with a `platforms` array
    if isinstance(payload, list):
        apis = payload
    elif isinstance(payload, dict) and isinstance(payload.get("platforms"), list):
        apis = payload.get("platforms")
    else:
        return {
            "ok": False,
            "error": "API list JSON must be an array, or an object containing a 'platforms' array",
        }

    out_dir = _abs_path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for api in apis:
        if not isinstance(api, dict):
            continue
        url = str(api.get("url") or "").strip()
        platform = str(api.get("platform") or api.get("name") or f"api_{api.get('id', '')}").strip()
        if not url:
            errors.append({"platform": platform, "error": "empty url"})
            continue

        out_path = out_dir / f"{platform}.json"
        fr = _fetch_url(
            url,
            timeout_seconds=int(timeout_seconds),
            max_chars=int(max_chars),
            retries=2,
            retry_backoff_seconds=1.0,
        )

        if fr.get("ok"):
            text = str(fr.get("text") or "")
            out_path.write_text(text, encoding="utf-8")
            results.append({
                "platform": platform,
                "url": url,
                "file": str(out_path),
                "bytes": fr.get("bytes"),
                "truncated": fr.get("truncated"),
            })
        else:
            errors.append({
                "platform": platform,
                "url": url,
                "error": fr.get("error"),
            })

        time.sleep(0.3)

    return {
        "ok": True,
        "output_dir": str(out_dir),
        "fetched": results,
        "errors": errors,
        "total_fetched": len(results),
        "total_errors": len(errors),
    }


def social_load_signals_from_disk(
    signals_dir: str = "output/social_insight_workflow/signals",
    max_items_per_source: int = 30,
) -> dict[str, Any]:
    """Load previously fetched raw signals from disk and normalize into structured items.

    This reads all .json files in signals_dir and returns normalized hot signals.
    """
    from datetime import datetime

    sig_dir = _abs_path(signals_dir)
    if not sig_dir.exists():
        return {"ok": False, "error": f"Signals directory not found: {sig_dir}"}

    files = sorted(sig_dir.glob("*.json"))
    if not files:
        return {"ok": False, "error": f"No .json files found in {sig_dir}"}

    fetched_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    sources: list[dict[str, Any]] = []
    normalized_items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for fpath in files:
        platform_key = fpath.stem
        platform, _ = _infer_platform(platform_key)

        try:
            text = fpath.read_text(encoding="utf-8")
        except Exception as exc:
            errors.append({"platform": platform, "file": str(fpath), "error": str(exc)})
            continue

        payload: Any
        try:
            payload = json.loads(text)
        except Exception:
            try:
                payload = _extract_first_json(text)
            except Exception:
                payload = None

        items = _extract_items(payload)
        items = items[: int(max(0, max_items_per_source))] if max_items_per_source else items

        source_rec: dict[str, Any] = {
            "platform": platform,
            "platform_key": platform_key,
            "file": str(fpath),
            "item_count": len(items),
        }
        sources.append(source_rec)

        n = max(1, len(items))
        for i, it in enumerate(items, start=1):
            title = _pick_title(it)
            hot_raw = _pick_hot_raw(it)
            hot_num = _parse_hot_number(hot_raw)
            url_item = _pick_url(it)
            rank = i
            hot_score = (float(n - rank + 1) / float(n)) * 100.0
            normalized_items.append(
                {
                    "platform": platform,
                    "platform_key": platform_key,
                    "rank": rank,
                    "title": title,
                    "title_norm": _normalize_title(title),
                    "url": url_item,
                    "hot_raw": hot_raw,
                    "hot_number": hot_num,
                    "hot_score": round(hot_score, 2),
                }
            )

    return {
        "ok": True,
        "fetched_at": fetched_at,
        "signals_dir": str(sig_dir),
        "sources": sources,
        "items": normalized_items,
        "errors": errors,
        "note": "hot_score is rank-based within each platform (0-100) for cross-platform comparison.",
    }


# ----------------------------
# Step 1: Collect signals (legacy, kept for compatibility)
# ----------------------------


def social_read_hot_api_list(path: str = "input/api/hot_api_list.txt", max_urls: int = 200) -> list[str]:
    urls = _read_lines(path)
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= int(max_urls):
            break
    return out


def social_collect_hot_signals(
    api_list_path: str = "input/api/hot_api_list.txt",
    timeout_seconds: int = 15,
    max_chars: int = 200_000,
    max_items_per_source: int = 30,
) -> dict[str, Any]:
    """Fetch hot signals from each URL in api_list_path.

    Returns a structured dict suitable for downstream clustering.
    """

    urls = social_read_hot_api_list(api_list_path)
    fetched_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    sources: list[dict[str, Any]] = []
    normalized_items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for url in urls:
        platform, platform_key = _infer_platform(url)
        fr = _fetch_url(
            url,
            timeout_seconds=int(timeout_seconds),
            max_chars=int(max_chars),
            retries=2,
            retry_backoff_seconds=1.0,
        )

        source_rec: dict[str, Any] = {
            "platform": platform,
            "platform_key": platform_key,
            "api_url": url,
            "fetch": {
                "ok": bool(fr.get("ok")),
                "status": fr.get("status"),
                "content_type": fr.get("content_type"),
                "truncated": fr.get("truncated"),
                "error": fr.get("error"),
            },
        }
        sources.append(source_rec)

        if not fr.get("ok"):
            errors.append({"platform": platform, "api_url": url, "error": fr.get("error")})
            continue

        text = str(fr.get("text") or "")
        payload: Any
        try:
            payload = json.loads(text)
        except Exception:
            try:
                payload = _extract_first_json(text)
            except Exception:
                payload = None

        items = _extract_items(payload)
        items = items[: int(max(0, max_items_per_source))] if max_items_per_source else items

        # Compute a comparable score by rank within each source (0-100).
        n = max(1, len(items))
        for i, it in enumerate(items, start=1):
            title = _pick_title(it)
            hot_raw = _pick_hot_raw(it)
            hot_num = _parse_hot_number(hot_raw)
            url_item = _pick_url(it)
            rank = i
            hot_score = (float(n - rank + 1) / float(n)) * 100.0
            normalized_items.append(
                {
                    "platform": platform,
                    "platform_key": platform_key,
                    "rank": rank,
                    "title": title,
                    "title_norm": _normalize_title(title),
                    "url": url_item,
                    "hot_raw": hot_raw,
                    "hot_number": hot_num,
                    "hot_score": round(hot_score, 2),
                }
            )

    return {
        "ok": True,
        "fetched_at": fetched_at,
        "api_list_path": api_list_path,
        "sources": sources,
        "items": normalized_items,
        "errors": errors,
        "note": "hot_score is rank-based within each platform (0-100) for cross-platform comparison.",
    }


# ----------------------------
# Step 2: Clustering fallback
# ----------------------------


@dataclass
class _Cluster:
    id: str
    items: list[dict[str, Any]]


def _fallback_cluster(items: list[dict[str, Any]], *, threshold: float = 0.78, max_clusters: int = 20) -> list[dict[str, Any]]:
    clusters: list[_Cluster] = []
    next_id = 1

    def _add_new(item: dict[str, Any]) -> None:
        nonlocal next_id
        cid = f"H{next_id:02d}"
        next_id += 1
        clusters.append(_Cluster(id=cid, items=[item]))

    for item in items:
        t = str(item.get("title_norm") or "")
        if not t:
            _add_new(item)
            continue
        best_idx = -1
        best_score = 0.0
        for idx, c in enumerate(clusters):
            # Compare with the first item title (stable deterministic representative).
            rep = str((c.items[0] or {}).get("title_norm") or "")
            s = _similar(t, rep)
            if s > best_score:
                best_score = s
                best_idx = idx
        if best_idx >= 0 and best_score >= float(threshold):
            clusters[best_idx].items.append(item)
        else:
            _add_new(item)
        if len(clusters) >= int(max_clusters):
            # Put remaining into a catch-all.
            continue

    # Sort items inside clusters by hot_score desc.
    result: list[dict[str, Any]] = []
    for c in clusters:
        c.items.sort(key=lambda x: float(x.get("hot_score") or 0.0), reverse=True)
        top = c.items[0]
        title = str(top.get("title") or "(unknown)")
        platforms = sorted({str(i.get("platform") or "") for i in c.items if i.get("platform")})
        overall = sum(float(i.get("hot_score") or 0.0) for i in c.items[: min(5, len(c.items))]) / float(
            max(1, min(5, len(c.items)))
        )
        coverage = len({str(i.get("platform_key") or "") for i in c.items if i.get("platform_key")})
        should_chase = "yes" if (overall >= 60.0 and coverage >= 2) else "no"
        result.append(
            {
                "hotspot_id": c.id,
                "title": title,
                "summary": f"跨平台聚合主题（覆盖{coverage}个平台，样本{len(c.items)}条）",
                "platform_coverage_count": coverage,
                "platforms": platforms,
                "overall_heat_score": round(overall, 2),
                "should_chase": should_chase,
                "signals": [
                    {
                        "platform": i.get("platform"),
                        "rank": i.get("rank"),
                        "title": i.get("title"),
                        "url": i.get("url"),
                        "hot_score": i.get("hot_score"),
                        "hot_raw": i.get("hot_raw"),
                    }
                    for i in c.items
                ],
            }
        )

    # Sort clusters by overall_heat_score desc.
    result.sort(key=lambda x: float(x.get("overall_heat_score") or 0.0), reverse=True)
    return result


# ----------------------------
# Topic priority weighting
# ----------------------------


_TOPIC_PRIORITY_RULES: dict[str, list[str]] = {
    # Low priority: politics / country / sensitive public affairs
    "low": [
        "政治",
        "国家",
        "中央",
        "中共中央",
        "政治局",
        "国务院",
        "外交",
        "对台",
        "军售",
        "反制",
        "制裁",
        "会议",
        "通告",
        "新华社",
    ],
    # High priority: tech / economy / business / finance
    "high": [
        "技术",
        "AI",
        "AIGC",
        "大模型",
        "模型",
        "编程",
        "开源",
        "云",
        "数据库",
        "前端",
        "后端",
        "算法",
        "芯片",
        "经济",
        "财经",
        "股",
        "A股",
        "美股",
        "港股",
        "通胀",
        "利率",
        "央行",
        "年终奖",
        "裁员",
        "融资",
        "IPO",
        "并购",
    ],
    # Normal priority: sports / celebrities / entertainment
    "normal": [
        "体育",
        "足球",
        "篮球",
        "NBA",
        "世界杯",
        "奥运",
        "明星",
        "演员",
        "歌手",
        "恋情",
        "结婚",
        "离婚",
        "绯闻",
        "综艺",
        "电影",
        "电视剧",
    ],
}


_TOPIC_PRIORITY_WEIGHTS: dict[str, float] = {
    "high": 1.20,
    "normal": 1.00,
    "low": 0.65,
}


def _topic_priority(title: str, summary: str | None = None) -> tuple[str, float, str]:
    text = f"{title or ''} {summary or ''}".strip()
    if not text:
        return "normal", _TOPIC_PRIORITY_WEIGHTS["normal"], "empty"

    # If multiple buckets match, prefer low (risk) over high, and high over normal.
    for tier in ("low", "high", "normal"):
        kws = _TOPIC_PRIORITY_RULES.get(tier, [])
        hit = next((k for k in kws if k and k in text), None)
        if hit:
            return tier, float(_TOPIC_PRIORITY_WEIGHTS.get(tier, 1.0)), hit
    return "normal", _TOPIC_PRIORITY_WEIGHTS["normal"], "default"


def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _derive_hotspot_score_and_coverage(h: dict[str, Any]) -> tuple[float, int]:
    base = _as_float(h.get("overall_heat_score"), 0.0)
    coverage = int(_as_float(h.get("platform_coverage_count"), 0.0))
    if base > 0 and coverage > 0:
        return base, coverage

    signals = h.get("signals")
    if isinstance(signals, list) and signals:
        scores = [_as_float(s.get("hot_score"), 0.0) for s in signals if isinstance(s, dict)]
        scores = [s for s in scores if s > 0]
        if not base and scores:
            base = sum(scores[: min(5, len(scores))]) / float(max(1, min(5, len(scores))))
        if not coverage:
            platform_keys = {
                str(s.get("platform") or "").strip()
                for s in signals
                if isinstance(s, dict) and str(s.get("platform") or "").strip()
            }
            coverage = len(platform_keys)
    return base, coverage


def _apply_priority_weights(hotspots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for h in hotspots:
        if not isinstance(h, dict):
            continue
        title = str(h.get("title") or "")
        summary = str(h.get("summary") or "") if h.get("summary") is not None else None
        tier, w, hit = _topic_priority(title, summary)

        base_score, coverage = _derive_hotspot_score_and_coverage(h)
        weighted = max(0.0, min(100.0, base_score * float(w)))

        # Store extra metadata for reporting/debug.
        h["priority_tier"] = tier
        h["priority_weight"] = round(float(w), 2)
        h["priority_hit"] = hit
        h["base_heat_score"] = round(float(base_score), 2)
        h["platform_coverage_count"] = int(coverage)
        h["overall_heat_score"] = round(float(weighted), 2)

        # Adjust should_chase with tier-aware thresholds.
        if tier == "low":
            should = "yes" if (weighted >= 80.0 and coverage >= 2) else "no"
        elif tier == "high":
            should = "yes" if (weighted >= 50.0 and coverage >= 1) else "no"
        else:
            should = "yes" if (weighted >= 60.0 and coverage >= 2) else "no"
        h["should_chase"] = str(h.get("should_chase") or should)
        # If LLM said yes but we strongly disagree due to low priority, override.
        if tier == "low" and should == "no":
            h["should_chase"] = "no"

        out.append(h)

    # Sort by weighted score, then by coverage.
    out.sort(
        key=lambda x: (
            _as_float(x.get("overall_heat_score"), 0.0),
            _as_float(x.get("platform_coverage_count"), 0.0),
        ),
        reverse=True,
    )
    return out


def social_cluster_or_fallback(raw_signals_json: str, clusters_json: str | None = None, top_k: int = 10) -> dict[str, Any]:
    """Use LLM clusters if valid JSON; otherwise perform deterministic clustering."""

    raw_obj: Any
    try:
        raw_obj = _extract_first_json(raw_signals_json)
    except Exception:
        try:
            raw_obj = json.loads(raw_signals_json)
        except Exception:
            raw_obj = None

    items = []
    if isinstance(raw_obj, dict) and isinstance(raw_obj.get("items"), list):
        items = [x for x in raw_obj.get("items") if isinstance(x, dict)]

    candidate_obj: Any = None
    if clusters_json and not _is_trivial_mock(clusters_json):
        try:
            candidate_obj = _extract_first_json(clusters_json)
        except Exception:
            candidate_obj = None

    # Accept either a list or an object containing clusters.
    if isinstance(candidate_obj, list):
        clusters = candidate_obj
        mode = "llm"
    elif isinstance(candidate_obj, dict) and isinstance(candidate_obj.get("hotspots"), list):
        clusters = candidate_obj.get("hotspots")
        mode = "llm"
    else:
        clusters = _fallback_cluster(items)
        mode = "fallback"

    # Normalize to a list of dicts.
    if isinstance(clusters, list):
        clusters = [x for x in clusters if isinstance(x, dict)]
    else:
        clusters = []

    # Apply topic priority weights before selecting TopK.
    clusters = _apply_priority_weights(clusters)

    try:
        k = int(top_k)
    except Exception:
        k = 10
    if k > 0:
        clusters = clusters[:k]

    return {
        "ok": True,
        "mode": mode,
        "top_k": k,
        "hotspots": clusters,
    }


# ----------------------------
# Step 3: Insight fallback
# ----------------------------


_EMOTION_RULES: list[tuple[str, list[str]]] = [
    ("愤怒/对立", ["翻车", "骂", "怒", "冲突", "争议", "抵制", "举报"]),
    ("焦虑/不确定", ["裁员", "暴跌", "失业", "危机", "崩", "焦虑", "恐慌", "风险"]),
    ("好奇/围观", ["爆", "热", "围观", "震惊", "瓜", "首次", "发现", "曝光"]),
    ("获益/实用", ["教程", "攻略", "省钱", "福利", "优惠", "方法", "技巧", "清单"]),
    ("愉悦/玩梗", ["笑", "搞笑", "梗", "离谱", "抽象", "哈哈", "整活"]),
]


def _infer_emotion(title: str) -> str:
    t = title or ""
    for emo, kws in _EMOTION_RULES:
        if any(k in t for k in kws):
            return emo
    return "混合/不明确"


def social_insight_or_fallback(clusters_json: str, insights_json: str | None = None) -> dict[str, Any]:
    """Use LLM insights if valid JSON; otherwise generate template insights."""
    clusters_obj: Any
    try:
        clusters_obj = _extract_first_json(clusters_json)
    except Exception:
        clusters_obj = None

    hotspots: list[dict[str, Any]] = []
    if isinstance(clusters_obj, dict) and isinstance(clusters_obj.get("hotspots"), list):
        hotspots = [x for x in clusters_obj.get("hotspots") if isinstance(x, dict)]

    candidate_obj: Any = None
    if insights_json and not _is_trivial_mock(insights_json):
        try:
            candidate_obj = _extract_first_json(insights_json)
        except Exception:
            candidate_obj = None

    if isinstance(candidate_obj, list):
        mode = "llm"
        insights = candidate_obj
    elif isinstance(candidate_obj, dict) and isinstance(candidate_obj.get("insights"), list):
        mode = "llm"
        insights = candidate_obj.get("insights")
    else:
        mode = "fallback"
        insights = []
        for h in hotspots:
            hid = str(h.get("hotspot_id") or "")
            title = str(h.get("title") or "")
            emo = _infer_emotion(title)
            insights.append(
                {
                    "hotspot_id": hid,
                    "title": title,
                    "trigger": "(兜底) 可能由事件/人物/政策/产品更新触发；建议结合来源链接做快速核验。",
                    "core_audience": "(兜底) 关注该领域的泛大众 + 强相关从业者/兴趣人群",
                    "emotion_structure": {
                        "primary": emo,
                        "secondary": "好奇/信息补全",
                        "notes": "(兜底) 通过标题关键词粗略推断。",
                    },
                    "content_affordance": ["解释型", "观点型", "情绪共鸣型"],
                    "risk_notes": ["信息不完整时，谨慎下结论", "避免未经证实的细节传播"],
                }
            )

    return {"ok": True, "mode": mode, "insights": insights}


# ----------------------------
# Step 4: Report rendering fallback
# ----------------------------


def _platform_templates() -> list[dict[str, str]]:
    return [
        {"platform": "Podcast", "format": "双人对谈/圆桌", "structure": "开场钩子 → 事实梳理 → 观点交锋 → 方法建议 → 收尾行动"},
        {"platform": "公众号", "format": "深度解读/观点", "structure": "一句话结论 → 背景 → 三点拆解 → 立场/建议 → 互动引导"},
        {"platform": "Blog", "format": "结构化分析", "structure": "TL;DR → 背景/定义 → 影响与机会 → 操作步骤/清单 → FAQ"},
        {"platform": "小红书", "format": "经验贴/清单", "structure": "痛点共鸣 → 我怎么做 → 关键步骤清单 → 注意事项 → 评论区问题"},
        {"platform": "短视频", "format": "30-60 秒", "structure": "3秒钩子 → 3个要点 → 反常识/结论 → CTA"},
    ]


def _recommend_platforms(emotion_primary: str) -> dict[str, str]:
    # Very simple rule-of-thumb.
    rec: dict[str, str] = {}
    if "获益" in emotion_primary:
        rec["公众号"] = "yes"
        rec["Blog"] = "yes"
        rec["短视频"] = "yes"
        rec["小红书"] = "yes"
        rec["Podcast"] = "no"
    elif "愤怒" in emotion_primary:
        rec["短视频"] = "yes"
        rec["小红书"] = "yes"
        rec["公众号"] = "cautious"
        rec["Blog"] = "cautious"
        rec["Podcast"] = "cautious"
    elif "焦虑" in emotion_primary:
        rec["公众号"] = "yes"
        rec["Blog"] = "yes"
        rec["短视频"] = "cautious"
        rec["小红书"] = "cautious"
        rec["Podcast"] = "yes"
    else:
        rec["短视频"] = "yes"
        rec["小红书"] = "yes"
        rec["公众号"] = "yes"
        rec["Blog"] = "yes"
        rec["Podcast"] = "cautious"
    return rec


def social_render_report_or_fallback(
    raw_signals_json: str,
    clusters_json: str,
    insights_json: str,
    report_markdown: str | None = None,
) -> str:
    """Return LLM report if usable; otherwise render deterministic Markdown.

    Note: Even when LLM output is usable, we still enforce a visible
    "## 当前核心热点列表" section (rendered from clusters_json) so that the final
    report always shows the current core hotspots at-a-glance.
    """

    def _render_core_hotspot_list_md(hotspots: list[dict[str, Any]]) -> str:
        lines: list[str] = ["## 当前核心热点列表"]
        for idx, h in enumerate(hotspots, start=1):
            tier = str(h.get("priority_tier") or "")
            if tier == "high":
                tier_label = "高"
            elif tier == "low":
                tier_label = "低"
            elif tier:
                tier_label = "正常"
            else:
                tier_label = ""
            tier_suffix = f"，优先级 {tier_label}" if tier_label else ""
            lines.append(
                f"{idx}. {h.get('title')}（热度 {h.get('overall_heat_score')}/100，覆盖 {h.get('platform_coverage_count')} 平台，建议追: {h.get('should_chase')}{tier_suffix}）"
            )
        if not hotspots:
            lines.append("(无可用热点；可能 API 拉取失败或聚类失败。)")
        return "\n".join(lines).strip()

    def _inject_core_list(report_md: str, core_list_md: str) -> str:
        report_md = (report_md or "").strip()
        core_list_md = (core_list_md or "").strip()
        if not report_md or not core_list_md:
            return report_md
        if "## 当前核心热点列表" in report_md:
            return report_md

        lines = report_md.splitlines()

        # Prefer inserting before the first horizontal rule (---) if present,
        # which keeps the report's original title/intro intact.
        insert_at: int | None = None
        for i, line in enumerate(lines):
            if line.strip() == "---":
                insert_at = i
                break
        if insert_at is None:
            for i, line in enumerate(lines):
                if line.startswith("## "):
                    insert_at = i
                    break
        if insert_at is None:
            insert_at = len(lines)

        new_lines = lines[:insert_at] + ["", core_list_md, ""] + lines[insert_at:]
        return "\n".join(new_lines).strip()

    clusters_obj: Any
    insights_obj: Any
    try:
        clusters_obj = _extract_first_json(clusters_json)
    except Exception:
        clusters_obj = None
    try:
        insights_obj = _extract_first_json(insights_json)
    except Exception:
        insights_obj = None

    hotspots: list[dict[str, Any]] = []
    if isinstance(clusters_obj, dict) and isinstance(clusters_obj.get("hotspots"), list):
        hotspots = [x for x in clusters_obj.get("hotspots") if isinstance(x, dict)]

    # If LLM report is usable, still enforce a core hotspot list section.
    if report_markdown and not _is_trivial_mock(report_markdown) and len(report_markdown.strip()) >= 200:
        return _inject_core_list(report_markdown, _render_core_hotspot_list_md(hotspots))

    insight_list: list[dict[str, Any]] = []
    if isinstance(insights_obj, dict) and isinstance(insights_obj.get("insights"), list):
        insight_list = [x for x in insights_obj.get("insights") if isinstance(x, dict)]

    insight_by_id: dict[str, dict[str, Any]] = {}
    for ins in insight_list:
        hid = str(ins.get("hotspot_id") or "").strip()
        if hid:
            insight_by_id[hid] = ins

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []
    lines.append("# 热点 × 内容投放建议报告")
    lines.append("")
    lines.append(f"- 生成时间: {now}")
    lines.append("- 输入: input/api/hot_api_list.json（多平台热点 API）")
    lines.append("- 输出目标: 回答‘值不值得追/适合平台/内容形式’（不直接代写成品内容）")
    lines.append("")

    # Core hotspot list.
    lines.append(_render_core_hotspot_list_md(hotspots))
    lines.append("")

    # Per-hotspot details.
    lines.append("## 热点洞察与投放建议")
    templates = _platform_templates()
    for h in hotspots:
        hid = str(h.get("hotspot_id") or "")
        title = str(h.get("title") or "")
        lines.append("")
        lines.append(f"### {hid}：{title}")
        lines.append("")
        lines.append("**1) 热点简述**")
        lines.append(f"- {h.get('summary')}")
        lines.append(f"- 覆盖平台: {', '.join(h.get('platforms') or [])}")
        lines.append("")

        ins = insight_by_id.get(hid, {})
        emo = "混合/不明确"
        if isinstance(ins.get("emotion_structure"), dict):
            emo = str(ins.get("emotion_structure", {}).get("primary") or emo)
        lines.append("**2) 洞察结论（成因与情绪结构）**")
        if ins:
            lines.append(f"- 触发原因: {ins.get('trigger')}")
            lines.append(f"- 核心人群: {ins.get('core_audience')}")
            lines.append(f"- 主情绪: {emo}")
            lines.append(
                f"- 内容属性: {', '.join(ins.get('content_affordance') or []) if isinstance(ins.get('content_affordance'), list) else ins.get('content_affordance')}"
            )
            if ins.get("risk_notes"):
                lines.append(f"- 风险提示: {', '.join(ins.get('risk_notes') or [])}")
        else:
            lines.append("- (缺少洞察数据)")
        lines.append("")

        lines.append("**3) 平台投放建议（选题方向 + 结构）**")
        rec = _recommend_platforms(emo)
        for t in templates:
            p = t["platform"]
            verdict = rec.get(p, "cautious")
            if verdict == "yes":
                head = "适合"
            elif verdict == "no":
                head = "不建议"
            else:
                head = "谨慎"
            lines.append(f"- {p}: {head}")
            if verdict != "no":
                lines.append(f"  - 内容形式: {t['format']}")
                lines.append(f"  - 建议结构: {t['structure']}")
                lines.append("  - 选题角度: 用‘事实澄清 + 立场/方法 + 可执行建议’组织")
        lines.append("")

        lines.append("**4) 信号样本（来自各平台榜单）**")
        signals = h.get("signals")
        if isinstance(signals, list) and signals:
            for s in signals[: min(10, len(signals))]:
                lines.append(
                    f"- {s.get('platform')} #{s.get('rank')}: {s.get('title')}（score {s.get('hot_score')}/100）"
                )
        else:
            lines.append("- (无信号样本)")

    lines.append("")
    lines.append("---")
    lines.append("生成说明：本报告在无 LLM 或 LLM 输出不可解析时，会采用确定性兜底逻辑（基于标题相似度与关键词规则）生成。")
    return "\n".join(lines).strip() + "\n"


# ----------------------------
# Registry hook
# ----------------------------


def register_tools(registry: object) -> None:
    register = getattr(registry, "register_tool", None)
    if not callable(register):
        return

    register("social.fetch_all_to_disk", social_fetch_all_to_disk)
    register("social.load_signals_from_disk", social_load_signals_from_disk)
    register("social.read_hot_api_list", social_read_hot_api_list)
    register("social.collect_hot_signals", social_collect_hot_signals)
    register("social.cluster_or_fallback", social_cluster_or_fallback)
    register("social.insight_or_fallback", social_insight_or_fallback)
    register("social.render_report_or_fallback", social_render_report_or_fallback)
