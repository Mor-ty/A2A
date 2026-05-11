"""
Lens dashboard (Gradio): Agent 1 + Agent 2 via A2A, with optional Agent 1→2 chain.

- Tab 1: decomposition + **HTTP A2A chain** to the graph skill (nested client, child context).
- Tab 2: direct call to the graph skill on an uploaded decomposition workbook.
- Tab 3: cosine similarity matrix (TF–IDF + cosine); Excel and/or Agent 2 HTML.
- Previews: Excel head + graph HTML iframe (small files only) + matrix corner preview.

1. `python __main__.py` (Lens A2A server)
2. MCP / LLM reachable
3. `pip install -r requirements.txt`
4. `python web_chat.py`
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
import pandas as pd
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
    if phase == "a2a_handoff":
        return f"**A2A handoff (Agent 1 → Agent 2):** {data.get('message', '')}\n\n"
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


def _build_decompose_payload(xlsx_path: str, *, chain_agent2: bool = True) -> dict[str, Any]:
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
        },
        "lens_chain_agent2": chain_agent2,
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


def _build_similarity_payload(
    xlsx_path: str | None,
    html_path: str | None,
    threshold: float,
) -> dict[str, Any]:
    import copy

    inputs: dict[str, Any] = {"similarity_threshold": float(threshold)}
    if xlsx_path and Path(str(xlsx_path)).is_file():
        p = Path(str(xlsx_path))
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        inputs["decomposition_workbook"] = {
            "name": p.name,
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "bytes": b64,
        }
    if html_path and Path(str(html_path)).is_file():
        p = Path(str(html_path))
        raw = p.read_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        inputs["graph_html"] = {
            "name": p.name,
            "mime_type": "text/html",
            "bytes": b64,
        }

    data = copy.deepcopy(_load_json(MESSAGE_TEMPLATE_PATH))
    data["description"] = "message"
    data["entityName"] = "Lens"
    data.setdefault("entityConfig", {})
    data["entityConfig"]["skillId"] = "lens_tc_similarity_skill"
    data["entityConfig"]["chatInput"] = "Build n×n cosine similarity matrix from per-TC state chains."
    data["entityConfig"]["inputs"] = inputs
    return data


def _new_session() -> dict[str, Any]:
    return {"context_id": uuid4().hex, "task_id": "", "configured": False}


def _excel_preview_update(xlsx_path: str | None, max_rows: int = 25):
    if not xlsx_path or not Path(xlsx_path).is_file():
        return gr.update(value=pd.DataFrame())
    try:
        df = pd.read_excel(xlsx_path, engine="openpyxl")
        return gr.update(value=df.head(max_rows))
    except Exception:
        return gr.update(value=pd.DataFrame({"_": ["(Excel preview unavailable)"]}))


def _matrix_preview_update(xlsx_path: str | None, max_dim: int = 48):
    if not xlsx_path or not Path(xlsx_path).is_file():
        return gr.update(value=pd.DataFrame())
    try:
        df = pd.read_excel(xlsx_path, sheet_name="similarity_matrix", engine="openpyxl", index_col=0)
        if df.shape[0] > max_dim or df.shape[1] > max_dim:
            df = df.iloc[:max_dim, :max_dim]
        return gr.update(value=df.astype(float).round(4))
    except Exception:
        return gr.update(value=pd.DataFrame({"_": ["(matrix preview unavailable)"]}))


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


def _empty_dashboard_row():
    return (
        gr.update(value=pd.DataFrame()),
        gr.update(
            value="<p><em>No chained graph yet. Enable “Chain Agent 2 via A2A” and run decomposition.</em></p>"
        ),
        gr.update(value=None),
        gr.update(value=None),
    )


async def _run_lens_decompose(
    xlsx_path: str | None,
    chain_agent2: bool,
    session: dict[str, Any],
):
    trace = ""
    paths: dict[str, str] = {}
    edf, hchain, fx, fg = _empty_dashboard_row()

    if not xlsx_path or not Path(xlsx_path).is_file():
        yield (
            trace + "\n*Please upload an `.xlsx` workbook first.*\n",
            edf,
            hchain,
            fx,
            fg,
            session,
        )
        return

    client = await _get_a2a_client()

    if not session.get("configured"):
        trace += "*Running configuration (MCP + LLM handshake)…*\n\n"
        yield trace, edf, hchain, fx, fg, session
        cfg = _build_config_payload()
        async for trace, session["task_id"], _, _ in _stream_message(
            client, cfg, session["context_id"], session.get("task_id") or ""
        ):
            yield trace, edf, hchain, fx, fg, session
        session["configured"] = True
        trace += "\n*Configuration complete. Running decomposition…*\n\n"
        yield trace, edf, hchain, fx, fg, session

    payload = _build_decompose_payload(str(xlsx_path), chain_agent2=bool(chain_agent2))
    summary = ""
    async for trace, session["task_id"], summary, pths in _stream_message(
        client, payload, session["context_id"], session.get("task_id") or ""
    ):
        paths = {**paths, **pths}
        xlsx_p = paths.get("xlsx")
        fx = gr.update(value=xlsx_p) if xlsx_p else gr.update()
        edf = _excel_preview_update(xlsx_p)
        html_p = paths.get("html")
        hchain = gr.update(value=_html_preview_snippet(html_p))
        fg = gr.update(value=html_p) if html_p else gr.update()
        yield trace, edf, hchain, fx, fg, session

    if summary and summary not in trace:
        trace += f"\n---\n{summary}\n"
    xlsx_p = paths.get("xlsx")
    html_p = paths.get("html")
    yield (
        trace,
        _excel_preview_update(xlsx_p),
        gr.update(value=_html_preview_snippet(html_p)),
        gr.update(value=xlsx_p) if xlsx_p else gr.update(),
        gr.update(value=html_p) if html_p else gr.update(),
        session,
    )


async def _run_lens_graph(xlsx_path: str | None, session: dict[str, Any]):
    trace = ""
    paths: dict[str, str] = {}
    upath = str(xlsx_path) if xlsx_path else ""
    df_prev = _excel_preview_update(upath if upath and Path(upath).is_file() else None)

    if not xlsx_path or not Path(xlsx_path).is_file():
        yield (
            trace + "\n*Upload Agent 1 decomposition `.xlsx`.*\n",
            gr.update(value=None),
            gr.update(value="<p>No graph yet.</p>"),
            gr.update(value=pd.DataFrame()),
            session,
        )
        return

    client = await _get_a2a_client()

    if not session.get("configured"):
        trace += "*Running configuration (MCP + LLM handshake)…*\n\n"
        yield trace, gr.update(value=None), gr.update(value="<p>Configuring…</p>"), df_prev, session
        cfg = _build_config_payload()
        async for trace, session["task_id"], _, _ in _stream_message(
            client, cfg, session["context_id"], session.get("task_id") or ""
        ):
            yield trace, gr.update(value=None), gr.update(value="<p>Configuring…</p>"), df_prev, session
        session["configured"] = True
        trace += "\n*Configuration complete. Building graph…*\n\n"
        yield trace, gr.update(value=None), gr.update(value="<p>Building graph…</p>"), df_prev, session

    payload = _build_graph_payload(str(xlsx_path))
    summary = ""
    df_prev = _excel_preview_update(str(xlsx_path))
    async for trace, session["task_id"], summary, pths in _stream_message(
        client, payload, session["context_id"], session.get("task_id") or ""
    ):
        paths = {**paths, **pths}
        preview = _html_preview_snippet(paths.get("html"))
        yield trace, gr.update(value=paths.get("html")), gr.update(value=preview), df_prev, session

    if summary and summary not in trace:
        trace += f"\n---\n{summary}\n"
    preview = _html_preview_snippet(paths.get("html"))
    yield trace, gr.update(value=paths.get("html")), gr.update(value=preview), df_prev, session


async def _run_lens_similarity(
    xlsx_path: str | None,
    html_path: str | None,
    threshold: float,
    session: dict[str, Any],
):
    trace = ""
    paths: dict[str, str] = {}
    empty_mat = gr.update(value=pd.DataFrame())

    has_x = bool(xlsx_path and Path(str(xlsx_path)).is_file())
    has_h = bool(html_path and Path(str(html_path)).is_file())
    if not has_x and not has_h:
        yield (
            trace + "\n*Upload at least one file: decomposition **.xlsx** (recommended) and/or Agent 2 **.html**.*\n",
            gr.update(value=None),
            empty_mat,
            session,
        )
        return

    client = await _get_a2a_client()

    if not session.get("configured"):
        trace += "*Running configuration (MCP + LLM handshake)…*\n\n"
        yield trace, gr.update(value=None), empty_mat, session
        cfg = _build_config_payload()
        async for trace, session["task_id"], _, _ in _stream_message(
            client, cfg, session["context_id"], session.get("task_id") or ""
        ):
            yield trace, gr.update(value=None), empty_mat, session
        session["configured"] = True
        trace += "\n*Configuration complete. Computing similarity matrix…*\n\n"
        yield trace, gr.update(value=None), empty_mat, session

    payload = _build_similarity_payload(
        str(xlsx_path) if has_x else None,
        str(html_path) if has_h else None,
        float(threshold),
    )
    summary = ""
    async for trace, session["task_id"], summary, pths in _stream_message(
        client, payload, session["context_id"], session.get("task_id") or ""
    ):
        paths = {**paths, **pths}
        mat_prev = _matrix_preview_update(paths.get("xlsx"))
        yield trace, gr.update(value=paths.get("xlsx")), mat_prev, session

    if summary and summary not in trace:
        trace += f"\n---\n{summary}\n"
    yield trace, gr.update(value=paths.get("xlsx")), _matrix_preview_update(paths.get("xlsx")), session


def create_demo() -> gr.Blocks:
    with gr.Blocks(title="Lens") as demo:
        gr.Markdown(
            "## Lens — automation dashboard\n"
            "A2A runtime: **`python __main__.py`** (port **9996** by default). "
            "Agent 1 can **chain** to Agent 2 over the same HTTP A2A endpoint (nested JSON-RPC client + child `context_id`). "
            "Override base URL with **`LENS_A2A_BASE_URL`** if the dashboard talks to a remote Lens."
        )
        gr.Markdown(
            "### Registered agents\n"
            "| # | Skill | Role |\n"
            "| --- | --- | --- |\n"
            "| 1 | `lens_tc_decompose_skill` | Raw TC Excel → step table |\n"
            "| 2 | `lens_graph_visualiser_skill` | Decomposed Excel → deduped layered **HTML** graph |\n"
            "| 3 | `lens_tc_similarity_skill` | Per-TC state chains → **n×n** cosine matrix (TF–IDF) |\n"
        )

        session_state = gr.State(_new_session())

        with gr.Tabs():
            with gr.Tab("Agent 1 — TC Decomposer"):
                gr.Markdown(
                    "Upload raw test cases (needs a **description** column such as **TC_Description**). "
                    "When **Chain Agent 2 via A2A** is on, the server calls `lens_graph_visualiser_skill` "
                    "with the decomposition bytes over A2A after the Excel artifact is produced."
                )
                chain1 = gr.Checkbox(
                    value=True,
                    label="Chain Agent 2 via A2A after decomposition",
                )
                x1 = gr.File(label="Test cases (.xlsx)", file_types=[".xlsx"])
                t1 = gr.Markdown(value="*Upload, then run.*")
                gr.Markdown("#### Decomposed workbook — row preview")
                d1 = gr.Dataframe(label="First rows (Agent 1 output)", interactive=False)
                gr.Markdown("#### Chained Agent 2 — graph preview (same A2A server)")
                h1_chain = gr.HTML(value="<p><em>Graph appears here when the chain completes.</em></p>")
                f1 = gr.File(label="Download decomposed workbook (.xlsx)")
                f1_graph = gr.File(label="Download chained graph HTML (Agent 2)")
                b1 = gr.Button("Run decomposition", variant="primary")

                async def run1(path, chain, sess):
                    async for row in _run_lens_decompose(path, chain, sess):
                        yield row

                b1.click(
                    run1,
                    inputs=[x1, chain1, session_state],
                    outputs=[t1, d1, h1_chain, f1, f1_graph, session_state],
                )

            with gr.Tab("Agent 2 — Graph visualiser"):
                gr.Markdown(
                    "Upload **Agent 1** output (`initial_state` / `final_state` columns). "
                    "This tab uses a **direct** A2A call to `lens_graph_visualiser_skill` (same session as Tab 1)."
                )
                x2 = gr.File(label="Decomposition workbook (.xlsx)", file_types=[".xlsx"])
                t2 = gr.Markdown(value="*Upload, then generate graph.*")
                gr.Markdown("#### Input workbook — preview")
                d2 = gr.Dataframe(label="Decomposition rows (head)", interactive=False)
                h2 = gr.HTML(value="<p>Graph preview (iframe) below when ready.</p>")
                f2 = gr.File(label="Download graph HTML")
                b2 = gr.Button("Generate graph", variant="primary")

                async def run2(path, sess):
                    async for row in _run_lens_graph(path, sess):
                        yield row

                b2.click(
                    run2,
                    inputs=[x2, session_state],
                    outputs=[t2, f2, h2, d2, session_state],
                )

            with gr.Tab("Agent 3 — TC similarity"):
                gr.Markdown(
                    "**Cosine similarity** between test cases from **connected states**.\n\n"
                    "- **Recommended:** upload the same **decomposition `.xlsx`** you use for Agent 2 (tc_id + steps).\n"
                    "- **Optional:** upload Agent 2’s **`lens_flow_graph.html`** (states are recovered from node tooltips); "
                    "you can attach **both** — Excel defines chains; HTML can add TCs found only in the graph.\n"
                    "- **Threshold:** pairs with similarity **≥** this value are listed in sheet `pairs_ge_threshold` "
                    "(default **0.8**). The full **n×n** matrix is on sheet `similarity_matrix` (diagonal **1**)."
                )
                x3 = gr.File(
                    label="Decomposition workbook (.xlsx, optional if HTML only)",
                    file_types=[".xlsx"],
                )
                h3_in = gr.File(
                    label="Agent 2 graph HTML (.html, optional if Excel only)",
                    file_types=[".html"],
                )
                thr3 = gr.Slider(
                    minimum=0.0,
                    maximum=1.0,
                    value=0.8,
                    step=0.05,
                    label="Pair-report threshold (cosine)",
                )
                t3 = gr.Markdown(value="*Upload at least one file, then run.*")
                gr.Markdown("#### Matrix preview (top-left corner if large)")
                m3 = gr.Dataframe(label="similarity_matrix (subset)", interactive=False)
                f3 = gr.File(label="Download similarity workbook (.xlsx)")
                b3 = gr.Button("Compute similarity matrix", variant="primary")

                async def run3(px, ph, thr, sess):
                    async for row in _run_lens_similarity(px, ph, thr, sess):
                        yield row

                b3.click(
                    run3,
                    inputs=[x3, h3_in, thr3, session_state],
                    outputs=[t3, f3, m3, session_state],
                )

        def reset_all():
            empty_df = gr.update(value=pd.DataFrame())
            return (
                _new_session(),
                "*New session.*",
                empty_df,
                gr.update(value="<p>Chained graph preview cleared.</p>"),
                gr.update(value=None),
                gr.update(value=None),
                "*New session.*",
                gr.update(value=None),
                gr.update(value="<p>Preview cleared.</p>"),
                empty_df,
                "*New session.*",
                gr.update(value=None),
                gr.update(value=None),
                gr.update(value=0.8),
                empty_df,
                gr.update(value=None),
            )

        gr.Button("New session (shared)").click(
            reset_all,
            outputs=[
                session_state,
                t1,
                d1,
                h1_chain,
                f1,
                f1_graph,
                t2,
                f2,
                h2,
                d2,
                t3,
                x3,
                h3_in,
                thr3,
                m3,
                f3,
            ],
        )

    return demo


if __name__ == "__main__":
    port = int(os.getenv("LENS_WEB_PORT", os.getenv("CALCULATOR_WEB_PORT", "7860")))
    host = os.getenv("LENS_WEB_HOST", os.getenv("CALCULATOR_WEB_HOST", "127.0.0.1"))
    create_demo().queue(default_concurrency_limit=4).launch(server_name=host, server_port=port, share=False)
