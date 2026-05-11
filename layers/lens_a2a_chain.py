"""
Lens — nested A2A JSON-RPC (HTTP) to the same Lens deployment.

- Agent 1 → Agent 2 (graph): configuration + graph skill.
- Agent 2 → Agent 3 (similarity): decomposition workbook → optional Agent 4 (clusters).

Uses a dedicated httpx.AsyncClient per nested chain so inner requests can yield on the event loop.
"""

from __future__ import annotations

import base64
import copy
import logging
import os
from typing import Any
from uuid import uuid4

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

from agent_card import public_agent_card

logger = logging.getLogger(__name__)


def _resolve_agent_url() -> str:
    u = (os.getenv("LENS_A2A_BASE_URL") or public_agent_card.url or "").strip()
    if not u.endswith("/"):
        u += "/"
    return u


def _status_to_md(event: TaskStatusUpdateEvent) -> str:
    msg = event.status.message
    if not msg or not msg.parts:
        return ""
    root = msg.parts[0].root
    if isinstance(root, TextPart):
        t = (root.text or "").strip()
        st = getattr(event.status.state, "value", None) or getattr(event.status.state, "name", None)
        st = st or str(event.status.state)
        return f"*{st}:* {t}\n" if t else ""
    if isinstance(root, DataPart) and isinstance(root.data, dict):
        d = root.data
        if d.get("kind") == "trace":
            return f"`trace/{d.get('phase')}` {d}\n"
        return f"`data` {d}\n"
    return ""


def _artifact_extract(event: TaskArtifactUpdateEvent) -> tuple[str, dict[str, bytes]]:
    summary = ""
    files: dict[str, bytes] = {}
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
            name = (getattr(root.file, "name", None) or "").lower()
            if name.endswith(".html"):
                files["html"] = raw
            elif name.endswith(".xlsx"):
                nl = name.lower()
                if "cluster" in nl:
                    files["xlsx_cluster"] = raw
                elif "similarity" in nl:
                    files["xlsx_similarity"] = raw
                else:
                    files["xlsx"] = raw
    return summary, files


async def _stream_once(
    client: A2AClient,
    payload: dict[str, Any],
    context_id: str,
    task_id: str,
) -> tuple[str, str, str, dict[str, bytes]]:
    """Returns (trace_md, task_id_out, last_summary, merged_file_bytes)."""

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

    trace_acc = ""
    current_task_id = task_id
    last_summary = ""
    merged: dict[str, bytes] = {}

    async for response in client.send_message_streaming(request):
        root = response.root
        if isinstance(root, JSONRPCErrorResponse):
            trace_acc += f"\n**A2A error:** `{root.error}`\n"
            return trace_acc, current_task_id, last_summary, merged

        if not getattr(root, "result", None):
            continue

        event = root.result

        if isinstance(event, Task):
            current_task_id = event.id or current_task_id
            trace_acc += f"*Child task:* `{current_task_id}`\n"
            continue

        if isinstance(event, TaskStatusUpdateEvent):
            trace_acc += _status_to_md(event)
            continue

        if isinstance(event, TaskArtifactUpdateEvent):
            summ, parts = _artifact_extract(event)
            if summ:
                last_summary = summ
            merged.update(parts)

    return trace_acc, current_task_id, last_summary, merged


def _config_payload(entity_id: str, entity_name: str, blueprints: list) -> dict[str, Any]:
    return {
        "id": "lens-a2a-chain",
        "remoteContextId": "",
        "taskId": "",
        "persistDataId": "",
        "entityId": entity_id,
        "type": "Agent",
        "entityName": entity_name,
        "entityUrl": _resolve_agent_url().rstrip("/"),
        "entityConfig": {
            "skillId": "lens_tc_decompose_skill",
            "chatInput": "A2A child session: configuration handshake for graph skill.",
            "inputs": {},
        },
        "experienceBlueprints": copy.deepcopy(blueprints),
        "description": "Configuration",
    }


def _graph_payload(
    entity_id: str,
    entity_name: str,
    blueprints: list,
    xlsx_bytes: bytes,
    fname: str,
    passthrough_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    b64 = base64.b64encode(xlsx_bytes).decode("ascii")
    graph_inputs: dict[str, Any] = {
        "decomposition_workbook": {
            "name": fname,
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "bytes": b64,
        }
    }
    if passthrough_inputs:
        for key in ("lens_chain_agent3", "similarity_threshold", "lens_chain_agent4", "cluster_threshold"):
            if key in passthrough_inputs and passthrough_inputs[key] is not None:
                graph_inputs[key] = passthrough_inputs[key]

    return {
        "id": "lens-a2a-chain",
        "remoteContextId": "",
        "taskId": "",
        "persistDataId": "",
        "entityId": entity_id,
        "type": "Agent",
        "entityName": entity_name,
        "entityUrl": _resolve_agent_url().rstrip("/"),
        "entityConfig": {
            "skillId": "lens_graph_visualiser_skill",
            "chatInput": "A2A: build graph from Agent 1 decomposition artifact (bytes).",
            "inputs": graph_inputs,
        },
        "experienceBlueprints": copy.deepcopy(blueprints),
        "description": "message",
    }


def _similarity_payload(
    entity_id: str,
    entity_name: str,
    blueprints: list,
    *,
    xlsx_bytes: bytes,
    xlsx_fname: str,
    threshold: float,
    html_bytes: bytes | None = None,
    html_fname: str = "lens_flow_graph.html",
    passthrough_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Automated chain uses **decomposition_workbook only** (Agent 1 artifact). HTML is optional (manual Tab 3)."""
    inputs: dict[str, Any] = {
        "similarity_threshold": float(threshold),
        "decomposition_workbook": {
            "name": xlsx_fname,
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "bytes": base64.b64encode(xlsx_bytes).decode("ascii"),
        },
    }
    if html_bytes is not None:
        inputs["graph_html"] = {
            "name": html_fname,
            "mime_type": "text/html",
            "bytes": base64.b64encode(html_bytes).decode("ascii"),
        }

    if passthrough_inputs:
        for key in ("lens_chain_agent4", "cluster_threshold"):
            if key in passthrough_inputs and passthrough_inputs[key] is not None:
                inputs[key] = passthrough_inputs[key]

    chat_in = (
        "A2A: cosine similarity from Agent 1 decomposition workbook (state chains)."
        if html_bytes is None
        else "A2A: cosine similarity from decomposition workbook ± optional graph HTML."
    )

    return {
        "id": "lens-a2a-chain-agent3",
        "remoteContextId": "",
        "taskId": "",
        "persistDataId": "",
        "entityId": entity_id,
        "type": "Agent",
        "entityName": entity_name,
        "entityUrl": _resolve_agent_url().rstrip("/"),
        "entityConfig": {
            "skillId": "lens_tc_similarity_skill",
            "chatInput": chat_in,
            "inputs": inputs,
        },
        "experienceBlueprints": copy.deepcopy(blueprints),
        "description": "message",
    }


async def invoke_agent4_cluster_skill_a2a(
    *,
    input_data: dict[str, Any],
    similarity_matrix_bytes: bytes,
    matrix_filename: str,
    cluster_threshold: float,
) -> tuple[str, bytes | None, str, str | None]:
    """Configuration + `lens_tc_cluster_skill` via A2A."""
    blueprints = input_data.get("experienceBlueprints") or []
    if not blueprints:
        return "", None, "", "Missing experienceBlueprints for Agent 4 A2A child call."

    entity_id = str(input_data.get("entityId") or "f93b7028-2838-4e44-9e58-975ad6d65b21")
    entity_name = str(input_data.get("entityName") or public_agent_card.name)
    base = _resolve_agent_url()
    card = public_agent_card.model_copy(update={"url": base})

    b64m = base64.b64encode(similarity_matrix_bytes).decode("ascii")
    payload = {
        "id": "lens-a2a-chain-agent4",
        "remoteContextId": "",
        "taskId": "",
        "persistDataId": "",
        "entityId": entity_id,
        "type": "Agent",
        "entityName": entity_name,
        "entityUrl": base.rstrip("/"),
        "entityConfig": {
            "skillId": "lens_tc_cluster_skill",
            "chatInput": "A2A: disjoint-set clusters from similarity matrix (sim > τ).",
            "inputs": {
                "similarity_matrix_workbook": {
                    "name": matrix_filename,
                    "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "bytes": b64m,
                },
                "cluster_threshold": float(cluster_threshold),
            },
        },
        "experienceBlueprints": copy.deepcopy(blueprints),
        "description": "message",
    }

    trace_all = ""
    child_ctx = str(uuid4())

    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, read=600.0)) as hx:
        client = A2AClient(httpx_client=hx, agent_card=card)

        cfg = _config_payload(entity_id, entity_name, blueprints)
        t1, tid, summ1, _f1 = await _stream_once(client, cfg, child_ctx, "")
        trace_all += t1
        if "**A2A error:**" in t1:
            return trace_all, None, "", "Agent 4 child configuration A2A call failed."

        t2, _tid2, summ2, files2 = await _stream_once(client, payload, child_ctx, tid or "")
        trace_all += "\n### Cluster skill / Agent 4 (A2A)\n\n" + t2
        if "**A2A error:**" in t2:
            return trace_all, None, summ2 or summ1, "Cluster skill A2A call failed (JSON-RPC error in stream)."

        cluster_out = files2.get("xlsx_cluster") or files2.get("xlsx")
        if cluster_out is None:
            return trace_all, None, summ2 or summ1, "Cluster skill returned no Excel artifact."

        return trace_all, cluster_out, summ2 or summ1, None


async def invoke_agent3_similarity_skill_a2a(
    *,
    input_data: dict[str, Any],
    decomposition_xlsx_bytes: bytes,
    decomposition_filename: str,
    similarity_threshold: float,
    graph_html_bytes: bytes | None = None,
    html_filename: str = "lens_flow_graph.html",
) -> tuple[str, bytes | None, bytes | None, str, str | None]:
    """
    Run configuration + similarity skill (Agent 3) via A2A (fresh child context_id).

    Primary input: **Agent 1 decomposition workbook** bytes. Graph HTML is optional.

    Returns: (trace_markdown, similarity_xlsx_or_none, cluster_xlsx_or_none, summary_text, error_message_or_none)
    """
    blueprints = input_data.get("experienceBlueprints") or []
    if not blueprints:
        return "", None, None, "", "Missing experienceBlueprints for Agent 3 A2A child call."

    entity_id = str(input_data.get("entityId") or "f93b7028-2838-4e44-9e58-975ad6d65b21")
    entity_name = str(input_data.get("entityName") or public_agent_card.name)

    base = _resolve_agent_url()
    card = public_agent_card.model_copy(update={"url": base})

    trace_all = ""
    child_ctx = str(uuid4())

    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, read=600.0)) as hx:
        client = A2AClient(httpx_client=hx, agent_card=card)

        cfg = _config_payload(entity_id, entity_name, blueprints)
        t1, tid, summ1, _f1 = await _stream_once(client, cfg, child_ctx, "")
        trace_all += t1
        if "**A2A error:**" in t1:
            return trace_all, None, None, "", "Agent 3 child configuration A2A call failed."

        pin = (input_data.get("entityConfig") or {}).get("inputs") or {}
        pt = {k: pin[k] for k in ("lens_chain_agent4", "cluster_threshold") if k in pin}

        sim = _similarity_payload(
            entity_id,
            entity_name,
            blueprints,
            xlsx_bytes=decomposition_xlsx_bytes,
            xlsx_fname=decomposition_filename,
            threshold=similarity_threshold,
            html_bytes=graph_html_bytes,
            html_fname=html_filename,
            passthrough_inputs=pt or None,
        )
        t2, _tid2, summ2, files2 = await _stream_once(client, sim, child_ctx, tid or "")
        trace_all += "\n### Similarity skill / Agent 3 (A2A)\n\n" + t2
        if "**A2A error:**" in t2:
            return trace_all, None, None, summ2 or summ1, "Similarity skill A2A call failed (JSON-RPC error in stream)."

        sim_out = files2.get("xlsx_similarity") or files2.get("xlsx")
        cluster_out = files2.get("xlsx_cluster")
        if sim_out is None:
            return trace_all, None, cluster_out, summ2 or summ1, "Similarity skill returned no Excel artifact."

        return trace_all, sim_out, cluster_out, summ2 or summ1, None


async def invoke_agent2_graph_skill_a2a(
    *,
    input_data: dict[str, Any],
    decomposition_excel_bytes: bytes,
    filename: str,
) -> tuple[str, bytes | None, bytes | None, bytes | None, str, str | None]:
    """
    Run configuration + graph skill against Lens using A2A (separate child context_id).

    Nested Agent 3/4 may append similarity and cluster workbooks (distinct xlsx keys).

    Returns: (trace_md, html, similarity_xlsx, cluster_xlsx, graph_summary, error)
    """
    blueprints = input_data.get("experienceBlueprints") or []
    if not blueprints:
        return "", None, None, None, "", "Missing experienceBlueprints for A2A child call."

    entity_id = str(input_data.get("entityId") or "f93b7028-2838-4e44-9e58-975ad6d65b21")
    entity_name = str(input_data.get("entityName") or public_agent_card.name)

    parent_inputs = (input_data.get("entityConfig") or {}).get("inputs") or {}
    passthrough: dict[str, Any] = {}
    for key in ("lens_chain_agent3", "similarity_threshold", "lens_chain_agent4", "cluster_threshold"):
        if key in parent_inputs:
            passthrough[key] = parent_inputs[key]

    base = _resolve_agent_url()
    card = public_agent_card.model_copy(update={"url": base})

    trace_all = ""
    child_ctx = str(uuid4())

    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, read=600.0)) as hx:
        client = A2AClient(httpx_client=hx, agent_card=card)

        cfg = _config_payload(entity_id, entity_name, blueprints)
        t1, tid, summ1, _files1 = await _stream_once(client, cfg, child_ctx, "")
        trace_all += t1
        if "**A2A error:**" in t1:
            return trace_all, None, None, None, "", "Child configuration A2A call failed."

        graph = _graph_payload(
            entity_id,
            entity_name,
            blueprints,
            decomposition_excel_bytes,
            filename,
            passthrough_inputs=passthrough or None,
        )
        t2, _tid2, summ2, files2 = await _stream_once(client, graph, child_ctx, tid or "")
        trace_all += "\n### Graph skill (A2A)\n\n" + t2
        if "**A2A error:**" in t2:
            return trace_all, None, None, None, summ2 or summ1, "Graph skill A2A call failed (JSON-RPC error in stream)."

        html = files2.get("html")
        if html is None:
            return trace_all, None, None, None, summ2 or summ1, "Graph skill returned no HTML artifact."

        sim_xlsx = files2.get("xlsx_similarity") or files2.get("xlsx")
        cluster_xlsx = files2.get("xlsx_cluster")
        return trace_all, html, sim_xlsx, cluster_xlsx, summ2 or summ1, None
