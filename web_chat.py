"""
Live calculator chat UI (Gradio) against the local A2A agent.

Prerequisites
-------------
1. Start the agent server:  python __main__.py
2. MCP must be reachable for the configuration step (see .env / MCP_NAME), same as client.py.
3. Install deps:  pip install -r requirements.txt

Run:  python web_chat.py
Open the printed URL (default http://127.0.0.1:7860).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, AsyncIterator
from uuid import uuid4

import gradio as gr
import httpx
from a2a.client import A2AClient
from a2a.types import (
    DataPart,
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
        timeout = httpx.Timeout(300.0, read=300.0)
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
        text = data.get("text") or ""
        return f"**Thinking**\n\n{text}\n\n"
    if phase == "assistant_text":
        text = data.get("text") or ""
        return f"**Model text (pre-tool)**\n\n{text}\n\n"
    if phase == "tool_call":
        tool = data.get("tool", "")
        args = data.get("arguments", {})
        return f"**Tool call:** `{tool}`({json.dumps(args, ensure_ascii=False)})\n\n"
    if phase == "tool_result":
        tool = data.get("tool", "")
        res = data.get("result", "")
        return f"**Tool result:** `{tool}` → **{res}**\n\n"
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n\n"


def _status_event_to_markdown(event: TaskStatusUpdateEvent) -> str:
    msg = event.status.message
    if not msg or not msg.parts:
        return ""
    root = msg.parts[0].root
    if isinstance(root, TextPart):
        t = root.text or ""
        if not t.strip():
            return ""
        return f"*{event.status.state.name}:* {t}\n\n"
    if isinstance(root, DataPart):
        d = root.data
        if isinstance(d, dict):
            return _format_trace_data(d)
        return f"*{event.status.state.name}:* `{d}`\n\n"
    return ""


def _artifact_text(event: TaskArtifactUpdateEvent) -> str | None:
    if not event.artifact.parts:
        return None
    root = event.artifact.parts[0].root
    if isinstance(root, TextPart):
        return root.text
    if isinstance(root, DataPart) and isinstance(root.data, dict):
        return json.dumps(root.data, indent=2, ensure_ascii=False)
    return str(root)


async def _stream_message(
    client: A2AClient,
    payload: dict[str, Any],
    context_id: str,
    task_id: str,
) -> AsyncIterator[tuple[str, str, str]]:
    """Yields (trace_markdown, task_id, last_artifact_text)."""

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
    last_text = ""

    async for response in client.send_message_streaming(request):
        root = response.root
        if isinstance(root, JSONRPCErrorResponse):
            trace_acc += f"\n**Error:** `{root.error}`\n"
            yield trace_acc, current_task_id, last_text
            return

        if not getattr(root, "result", None):
            continue

        event = root.result

        if isinstance(event, Task):
            current_task_id = event.id or current_task_id
            trace_acc += f"*Task:* `{current_task_id}`\n\n"
            yield trace_acc, current_task_id, last_text
            continue

        if isinstance(event, TaskStatusUpdateEvent):
            chunk = _status_event_to_markdown(event)
            if chunk:
                trace_acc += chunk
                yield trace_acc, current_task_id, last_text
            continue

        if isinstance(event, TaskArtifactUpdateEvent):
            text = _artifact_text(event)
            if text is not None:
                last_text = text
            if getattr(event, "last_chunk", False) and last_text:
                trace_acc += f"---\n**Final answer (artifact)**\n\n{last_text}\n"
                yield trace_acc, current_task_id, last_text

    yield trace_acc, current_task_id, last_text


def _build_message_payload(user_query: str, blueprint_template: dict[str, Any]) -> dict[str, Any]:
    import copy

    data = copy.deepcopy(blueprint_template)
    data["description"] = "message"
    data.setdefault("entityConfig", {})
    data["entityConfig"]["skillId"] = "calculator_skill"
    data["entityConfig"].setdefault("inputs", {})
    data["entityConfig"]["inputs"]["user_query"] = user_query
    return data


def _build_config_payload() -> dict[str, Any]:
    import copy

    data = copy.deepcopy(_load_json(CONFIG_PATH))
    data["description"] = "Configuration"
    return data


def _new_session() -> dict[str, Any]:
    return {
        "context_id": uuid4().hex,
        "task_id": "",
        "configured": False,
    }


async def _run_chat_turn(
    user_message: str,
    history: list,
    session: dict[str, Any],
):
    history = list(history or [])
    trace = ""

    if not user_message or not str(user_message).strip():
        yield history, trace, session
        return

    client = await _get_a2a_client()
    blueprint_template = _load_json(MESSAGE_TEMPLATE_PATH)

    if not session.get("configured"):
        trace += "*Running configuration (MCP + LLM handshake)…*\n\n"
        yield history, trace, session

        config_payload = _build_config_payload()
        async for trace, session["task_id"], _ in _stream_message(
            client, config_payload, session["context_id"], session.get("task_id") or ""
        ):
            yield history, trace, session

        session["configured"] = True
        trace += "\n*Configuration complete. Sending your question…*\n\n"
        yield history, trace, session

    msg_payload = _build_message_payload(user_message.strip(), blueprint_template)
    final_answer = ""

    async for trace, session["task_id"], final_answer in _stream_message(
        client, msg_payload, session["context_id"], session.get("task_id") or ""
    ):
        yield history, trace, session

    reply = (final_answer or "").strip() or "(No answer text — see trace above.)"
    history.append([user_message, reply])
    yield history, trace, session


def create_demo() -> gr.Blocks:
    with gr.Blocks(title="Calculator A2A Chat") as demo:
        gr.Markdown(
            "## Calculator agent (live)\n"
            "Ask arithmetic questions. **Thinking**, **tool calls**, and **tool results** "
            "appear in the trace panel. Start **`python __main__.py`** on port 9996 first."
        )
        session_state = gr.State(_new_session())

        chat = gr.Chatbot(label="Conversation", height=380)
        trace = gr.Markdown(label="Agent trace (thinking & tools)", value="*Ready.*")

        with gr.Row():
            msg = gr.Textbox(
                label="Your question",
                placeholder="e.g. What is (19 + 7) × 3?",
                scale=4,
            )
            submit = gr.Button("Send", variant="primary")
            reset = gr.Button("New session")

        async def on_submit(user_text, hist, sess):
            async for h, t, s in _run_chat_turn(user_text, hist, sess):
                yield h, t, s

        sub = submit.click(on_submit, inputs=[msg, chat, session_state], outputs=[chat, trace, session_state])
        sub.then(lambda: "", outputs=[msg])
        ent = msg.submit(on_submit, inputs=[msg, chat, session_state], outputs=[chat, trace, session_state])
        ent.then(lambda: "", outputs=[msg])

        reset.click(
            lambda: ([], "*New session — send a question.*", _new_session()),
            outputs=[chat, trace, session_state],
        )

    return demo


if __name__ == "__main__":
    port = int(os.getenv("CALCULATOR_WEB_PORT", "7860"))
    create_demo().queue(default_concurrency_limit=10).launch(
        server_name=os.getenv("CALCULATOR_WEB_HOST", "127.0.0.1"),
        server_port=port,
        share=False,
    )
