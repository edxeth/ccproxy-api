"""mitmproxy addon that extracts model names from Codex SSE streams.

Run with ``mitmdump -s scripts/mitm_codex_sse_logger.py`` while CCProxy is
configured to forward HTTP(S) traffic through mitmproxy. Each matching SSE flow
prints the upstream URL, event type, and the model reported by OpenAI so that
you can verify the actual backend model being used.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from mitmproxy import ctx, http


CODEX_SSE_CONTENT_TYPE = "text/event-stream"


def _iter_sse_payloads(body: str) -> Iterable[tuple[str, dict]]:
    """Yield ``(event_type, payload_dict)`` tuples from an SSE body.

    The streaming Codex endpoints send JSON objects prefixed with ``data:``
    lines. mitmproxy captures the entire body once the stream finishes, so we
    can split on newline boundaries and decode the JSON content.
    """

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:") :].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:  # pragma: no cover - diagnostic only
            ctx.log.warn("failed to decode SSE chunk", error=str(exc), chunk=payload)
            continue
        event_type = parsed.get("type", "unknown")
        yield event_type, parsed


def _extract_model(payload: dict) -> str | None:
    """Return the model name present in a Codex SSE payload."""

    model = payload.get("model")
    if model:
        return model
    response = payload.get("response")
    if isinstance(response, dict):
        return response.get("model")
    return None


def _looks_like_codex(flow: http.HTTPFlow) -> bool:
    url = flow.request.pretty_url
    return "chatgpt.com" in url and "/backend-api/codex" in url


def response(flow: http.HTTPFlow) -> None:
    """Inspect SSE responses and log any model names we find."""

    if not flow.response:
        return

    ctx.log.info(
        "codex_response flow=%s status=%s headers=%s",
        flow.id,
        flow.response.status_code,
        dict(flow.response.headers),
    )

    if not _looks_like_codex(flow):
        return

    body = flow.response.get_text(strict=False)
    try:
        from pathlib import Path

        Path("/tmp/mitm_last_body.txt").write_text(body)
    except Exception:
        pass
    for event_type, payload in _iter_sse_payloads(body):
        model = _extract_model(payload)
        reasoning_effort = None
        response = payload.get("response")
        if isinstance(response, dict):
            reasoning = response.get("reasoning") or response.get("metadata", {}).get(
                "reasoning"
            )
            if isinstance(reasoning, dict):
                reasoning_effort = reasoning.get("effort") or reasoning.get(
                    "effort_level"
                )

        if model:
            ctx.log.info(
                "codex_sse_model flow=%s event=%s model=%s reasoning=%s url=%s",
                flow.id,
                event_type,
                model,
                reasoning_effort,
                flow.request.pretty_url,
            )


def request(flow: http.HTTPFlow) -> None:
    """Log outgoing Codex request bodies for debugging."""

    if not _looks_like_codex(flow):
        return

    if flow.request.method != "POST":
        return

    try:
        body = flow.request.get_text()
        payload = json.loads(body)
    except Exception:
        return

    ctx.log.info(
        "codex_request flow=%s prompt_cache_key=%s include=%s keys=%s",
        flow.id,
        payload.get("prompt_cache_key"),
        payload.get("include"),
        list(payload.keys()),
    )
