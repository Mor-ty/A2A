"""
Lens dashboard (Gradio): Agent 1 (decompose) + Agent 2 (graph) via A2A.

1. python __main__.py
2. MCP reachable
3. pip install -r requirements.txt
4. python web_chat.py
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path
from typing import Any, AsyncIterator
from uuid import uuid4

import gradio as gr
import httpx
from a2a.client import A2AClient
from a2a.types import (
    DataPart,
    FilePart,
    JSONRPCErrorResponse,
    MessageSendParams,
    SendStreamingMessageRequest,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
    TextPart,
)
from dotenv import load_dotenv

from agent_card import public_agent_card

load_dotenv()

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "input-config.json"
MESSAGE_TEMPLATE_PATH = ROOT / "input-message.json"

_httpx_client: httpx.AsyncClient | None = None
_a2a_client: A2AClient | None = None


async def _get_a2a_client() -> A2AClient:
    global _httpx_client, _a2a_client
    if _a2a_client is None:
        timeout = httpx.Timeout(600.0, read=600.0)
        _httpx_client = httpx.AsyncClient(timeout=timeout)
        _a2a_client = A2AClient(httpx_client=_httpx_client, agent_card=public_agent_card)
    return _a2a_client


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _format_trace_data(data: dict[str, Any]) -> str:
    if data.get("kind") != "trace":
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n\n"

    phase = data.get("phase", "")
    if phase == "thinking":
        return f"**Thinking**\n\n{data.get('text') or ''}\n\n"
    if phase == "assistant_text":
        return f"**Model text**\n\n{data.get('text') or ''}\n\n"
    if phase == "tool_call":
        return (
            f"**Tool call:** `{data.get('tool', '')}`"
            f"({json.dumps(data.get('arguments', {}), ensure_ascii=False)})\n\n"
        )
    if phase == "tool_result":
        return f"**Tool result:** `{data.get('tool', '')}` → **{data.get('result', '')}**\n\n"
    if phase == "lens_batch":
        return (
            f"**Lens batch:** rows **{data.get('batch_start')}–{data.get('batch_end')}** "
            f"of **{data.get('total')}**\n\n"
        )
    if phase == "lens_progress":
        return f"**Lens:** {data.get('message', '')}\n\n"
    if phase == "lens_error":
        return f"**Lens error:** {data.get('message', '')}\n\n"
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n\n"


def _status_event_to_markdown(event: TaskStatusUpdateEvent) -> str:
    msg = event.status.message
    if not msg or not msg.parts:
        return ""
    root = msg.parts[0].root
    if isinstance(root, TextPart):
        t = root.text or ""
        return f"*{event.status.state.name}:* {t}\n\n" if t.strip() else ""
    if isinstance(root, DataPart):
        d = root.data
        if isinstance(d, dict):
            return _format_trace_data(d)
        return f"*{event.status.state.name}:* `{d}`\n\n"
    return ""


def _artifact_parts_to_paths(event: TaskArtifactUpdateEvent) -> tuple[str, dict[str, str]]:
    summary = ""
    paths: dict[str, str] = {}
    for p in event.artifact.parts:
        root = p.root
        if isinstance(root, TextPart) and root.text:
            summary = root.text
        if isinstance(root, FilePart) and root.file:
            fb = getattr(root.file, "bytes", None)
            if not fb:
                continue
            try:
                raw = base64.b64decode(fb)
            except Exception:
                continue
            name = getattr(root.file, "name", None) or "artifact.bin"
            suf = Path(str(name)).suffix.lower()
            if suf == ".html":
                fd, path = tempfile.mkstemp(suffix=".html", prefix="lens_graph_")
                os.close(fd)
                Path(path).write_bytes(raw)
                paths["html"] = path
            elif suf in (".xlsx", ".xls"):
                fd, path = tempfile.mkstemp(suffix=".xlsx", prefix="lens_")
                os.close(fd)
                Path(path).write_bytes(raw)
                paths["xlsx"] = path
    return summary, paths


async def _stream_message(
    client: A2AClient,
    payload: dict[str, Any],
    context_id: str,
    task_id: str,
) -> AsyncIterator[tuple[str, str, str, dict[str, str]]]:
    """Yields (trace_md, task_id, text_summary, artifact_paths)."""

    body = {
        "message": {
            "role": "user",
            "parts": [{"kind": "data", "data": payload}],
            "message_id": uuid4().hex,
            "metadata": {"execution_id": "", "experience_id": "", "session_id": ""},
            **({"task_id": task_id} if task_id else {}),
            **({"context_id": context_id} if context_id else {}),
        }
    }
    request = SendStreamingMessageRequest(id=str(uuid4()), params=MessageSendParams(**body))

    current_task_id = task_id
    trace_acc = ""
    last_summary = ""
    last_paths: dict[str, str] = {}

    async for response in client.send_message_streaming(request):
        root = response.root
        if isinstance(root, JSONRPCErrorResponse):
            trace_acc += f"\n**Error:** `{root.error}`\n"
            yield trace_acc, current_task_id, last_summary, last_paths
            return

        if not getattr(root, "result", None):
            continue

        event = root.result

        if isinstance(event, Task):
            current_task_id = event.id or current_task_id
            trace_acc += f"*Task:* `{current_task_id}`\n\n"
            yield trace_acc, current_task_id, last_summary, last_paths
            continue

        if isinstance(event, TaskStatusUpdateEvent):
            chunk = _status_event_to_markdown(event)
            if chunk:
                trace_acc += chunk
                yield trace_acc, current_task_id, last_summary, last_paths
            continue

        if isinstance(event, TaskArtifactUpdateEvent):
            summ, pths = _artifact_parts_to_paths(event)
            if summ:
                last_summary = summ
            last_paths = {**last_paths, **pths}
            if getattr(event, "last_chunk", False):
                if last_summary:
                    trace_acc += f"---\n**Artifact (summary)**\n\n{last_summary}\n"
                if last_paths:
                    trace_acc += f"\n**Artifact files:** {', '.join(last_paths.keys())}\n"
                yield trace_acc, current_task_id, last_summary, last_paths

    yield trace_acc, current_task_id, last_summary, last_paths


def _build_config_payload() -> dict[str, Any]:
    import copy

    return copy.deepcopy(_load_json(CONFIG_PATH))


def _build_decompose_payload(xlsx_path: str) -> dict[str, Any]:
    import copy

    p = Path(xlsx_path)
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    data = copy.deepcopy(_load_json(MESSAGE_TEMPLATE_PATH))
    data["description"] = "message"
    data["entityName"] = "Lens"
    data.setdefault("entityConfig", {})
    data["entityConfig"]["skillId"] = "lens_tc_decompose_skill"
    data["entityConfig"]["chatInput"] = "Decompose uploaded automation test cases workbook."
    data["entityConfig"]["inputs"] = {
        "workbook": {
            "name": p.name,
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "bytes": b64,
        }
    }
    return data


def _build_graph_payload(xlsx_path: str) -> dict[str, Any]:
    import copy

    p = Path(xlsx_path)
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    data = copy.deepcopy(_load_json(MESSAGE_TEMPLATE_PATH))
    data["description"] = "message"
    data["entityName"] = "Lens"
    data.setdefault("entityConfig", {})
    data["entityConfig"]["skillId"] = "lens_graph_visualiser_skill"
    data["entityConfig"]["chatInput"] = "Build deduplicated flow graph from decomposition workbook."
    data["entityConfig"]["inputs"] = {
        "decomposition_workbook": {
            "name": p.name,
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "bytes": b64,
        }
    }
    return data


def _new_session() -> dict[str, Any]:
    return {"context_id": uuid4().hex, "task_id": "", "configured": False}


def _html_preview_snippet(html_path: str | None) -> str:
    if not html_path or not Path(html_path).is_file():
        return "<p><em>No graph HTML yet. Use download below or run again.</em></p>"
    raw = Path(html_path).read_bytes()
    if len(raw) > 1_200_000:
        return (
            "<p><strong>Graph HTML is large.</strong> Download the file and open it in Chrome/Edge "
            "for full interactivity.</p>"
        )
    b64 = base64.b64encode(raw).decode("ascii")
    return (
        f'<iframe title="Lens graph" style="width:100%;height:720px;border:1px solid #ccc" '
        f'src="data:text/html;base64,{b64}"></iframe>'
    )


async def _run_lens_decompose(xlsx_path: str | None, session: dict[str, Any]):
    trace = ""
    paths: dict[str, str] = {}

    if not xlsx_path or not Path(xlsx_path).is_file():
        yield trace + "\n*Please upload an `.xlsx` workbook first.*\n", gr.update(value=None), session
        return

    client = await _get_a2a_client()

    if not session.get("configured"):
        trace += "*Running configuration (MCP + LLM handshake)…*\n\n"
        yield trace, gr.update(value=None), session
        cfg = _build_config_payload()
        async for trace, session["task_id"], _, _ in _stream_message(
            client, cfg, session["context_id"], session.get("task_id") or ""
        ):
            yield trace, gr.update(value=None), session
        session["configured"] = True
        trace += "\n*Configuration complete. Running decomposition…*\n\n"
        yield trace, gr.update(value=None), session

    payload = _build_decompose_payload(str(xlsx_path))
    summary = ""
    async for trace, session["task_id"], summary, pths in _stream_message(
        client, payload, session["context_id"], session.get("task_id") or ""
    ):
        paths = {**paths, **pths}
        upd = gr.update(value=paths.get("xlsx")) if paths.get("xlsx") else gr.update()
        yield trace, upd, session

    if summary and summary not in trace:
        trace += f"\n---\n{summary}\n"
    yield trace, gr.update(value=paths.get("xlsx")), session


async def _run_lens_graph(xlsx_path: str | None, session: dict[str, Any]):
    trace = ""
    paths: dict[str, str] = {}

    if not xlsx_path or not Path(xlsx_path).is_file():
        yield (
            trace + "\n*Upload Agent 1 decomposition `.xlsx`.*\n",
            gr.update(value=None),
            gr.update(value="<p>No graph yet.</p>"),
            session,
        )
        return

    client = await _get_a2a_client()

    if not session.get("configured"):
        trace += "*Running configuration (MCP + LLM handshake)…*\n\n"
        yield trace, gr.update(value=None), gr.update(value="<p>Configuring…</p>"), session
        cfg = _build_config_payload()
        async for trace, session["task_id"], _, _ in _stream_message(
            client, cfg, session["context_id"], session.get("task_id") or ""
        ):
            yield trace, gr.update(value=None), gr.update(value="<p>Configuring…</p>"), session
        session["configured"] = True
        trace += "\n*Configuration complete. Building graph…*\n\n"
        yield trace, gr.update(value=None), gr.update(value="<p>Building graph…</p>"), session

    payload = _build_graph_payload(str(xlsx_path))
    summary = ""
    async for trace, session["task_id"], summary, pths in _stream_message(
        client, payload, session["context_id"], session.get("task_id") or ""
    ):
        paths = {**paths, **pths}
        preview = _html_preview_snippet(paths.get("html"))
        yield trace, gr.update(value=paths.get("html")), gr.update(value=preview), session

    if summary and summary not in trace:
        trace += f"\n---\n{summary}\n"
    preview = _html_preview_snippet(paths.get("html"))
    yield trace, gr.update(value=paths.get("html")), gr.update(value=preview), session


def create_demo() -> gr.Blocks:
    with gr.Blocks(title="Lens") as demo:
        gr.Markdown(
            "## Lens — automation dashboard\n"
            "A2A runtime: **`python __main__.py`** (port 9996)."
        )
        gr.Markdown(
            "### Registered agents\n"
            "| # | Skill | Role |\n"
            "| --- | --- | --- |\n"
            "| 1 | `lens_tc_decompose_skill` | Raw TC Excel → step table |\n"
            "| 2 | `lens_graph_visualiser_skill` | Decomposed Excel → deduped layered **HTML** graph |\n"
        )

        session_state = gr.State(_new_session())

        with gr.Tabs():
            with gr.Tab("Agent 1 — TC Decomposer"):
                gr.Markdown("Upload raw test cases (needs **TC_Description** column).")
                x1 = gr.File(label="Test cases (.xlsx)", file_types=[".xlsx"])
                t1 = gr.Markdown(value="*Upload, then run.*")
                f1 = gr.File(label="Decomposed workbook (.xlsx)")
                b1 = gr.Button("Run decomposition", variant="primary")

                async def run1(path, sess):
                    async for a, b, c in _run_lens_decompose(path, sess):
                        yield a, b, c

                b1.click(run1, inputs=[x1, session_state], outputs=[t1, f1, session_state])

            with gr.Tab("Agent 2 — Graph visualiser"):
                gr.Markdown("Upload **Agent 1** output (`initial_state` / `final_state` columns).")
                x2 = gr.File(label="Decomposition workbook (.xlsx)", file_types=[".xlsx"])
                t2 = gr.Markdown(value="*Upload, then generate graph.*")
                h2 = gr.HTML(value="<p>Graph preview (iframe) below when ready.</p>")
                f2 = gr.File(label="Download graph HTML")
                b2 = gr.Button("Generate graph", variant="primary")

                async def run2(path, sess):
                    async for a, b, c, d in _run_lens_graph(path, sess):
                        yield a, b, c, d

                b2.click(run2, inputs=[x2, session_state], outputs=[t2, f2, session_state, h2])

        def reset_all():
            return (
                _new_session(),
                "*New session.*",
                gr.update(value=None),
                "*New session.*",
                gr.update(value=None),
                "<p>Preview cleared.</p>",
            )

        gr.Button("New session (shared)").click(
            reset_all,
            outputs=[session_state, t1, f1, t2, f2, h2],
        )

    return demo


if __name__ == "__main__":
    port = int(os.getenv("LENS_WEB_PORT", os.getenv("CALCULATOR_WEB_PORT", "7860")))
    host = os.getenv("LENS_WEB_HOST", os.getenv("CALCULATOR_WEB_HOST", "127.0.0.1"))
    create_demo().queue(default_concurrency_limit=4).launch(server_name=host, server_port=port, share=False)
