"""
Lens — Agent 4: cluster test cases from Agent 3 similarity matrix (disjoint sets).

Union(i,j) when sim(i,j) > cluster_threshold (strict). Output per-TC cluster id + summary.
"""

from __future__ import annotations

import base64
import io
import logging
import os
from collections import defaultdict
from typing import Any, AsyncGenerator, TYPE_CHECKING

import pandas as pd
from a2a.types import FilePart, FileWithBytes, Part, TaskArtifactUpdateEvent, TaskStatusUpdateEvent, TextPart

from layers.lens_similarity_metrics import clusters_from_matrix, effectiveness_metrics, matrix_from_similarity_workbook

if TYPE_CHECKING:
    from agentic_os_infra.core.layers.agent_logic_base import AgentLogicBase

logger = logging.getLogger(__name__)

DEFAULT_CLUSTER_THRESHOLD = float(os.getenv("LENS_CLUSTER_THRESHOLD", os.getenv("LENS_SIM_THRESHOLD", "0.8")))


def _trace(phase: str, **fields: object) -> dict:
    return {"kind": "trace", "phase": phase, **fields}


def _decode_matrix_file(raw: Any) -> tuple[bytes, str]:
    if not raw or not isinstance(raw, dict):
        raise ValueError(
            "Missing similarity matrix workbook. Expected `similarity_matrix_workbook` "
            "with name, mime_type, bytes (base64) from Agent 3."
        )
    b64 = raw.get("bytes") or raw.get("data")
    name = raw.get("name") or raw.get("file_name") or "similarity_matrix.xlsx"
    if not b64:
        raise ValueError("Similarity workbook missing base64 bytes.")
    return base64.b64decode(b64), str(name)


def _chain_agent4_enabled(inputs: dict[str, Any]) -> bool:
    env = (os.getenv("LENS_CHAIN_AGENT4_VIA_A2A") or "1").strip().lower()
    if env in ("0", "false", "no", "off"):
        opt = inputs.get("lens_chain_agent4")
        if opt is True:
            return True
        if isinstance(opt, str) and opt.strip().lower() in ("1", "true", "yes", "on"):
            return True
        return False
    opt = inputs.get("lens_chain_agent4")
    if opt is False:
        return False
    if isinstance(opt, str) and opt.strip().lower() in ("0", "false", "no", "off"):
        return False
    return True


def _cluster_threshold_from_inputs(inputs: dict[str, Any], fallback: float) -> float:
    raw = inputs.get("cluster_threshold")
    try:
        v = float(raw) if raw is not None else float(fallback)
    except (TypeError, ValueError):
        v = float(fallback)
    return max(0.0, min(1.0, v))


async def run_lens_tc_cluster(
    agent: "AgentLogicBase",
    input_data: dict[str, Any],
) -> AsyncGenerator[TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:
    yield agent.status_response(content="Lens Agent 4 — loading similarity matrix workbook")

    inputs = input_data.get("entityConfig", {}).get("inputs", {})
    try:
        raw_bytes, fname = _decode_matrix_file(inputs.get("similarity_matrix_workbook"))
    except ValueError as e:
        yield agent.status_response(content=_trace("lens_error", message=str(e)))
        yield agent.artifact_response(content=f"**Error:** {e}", last_chunk=True)
        return

    thr = _cluster_threshold_from_inputs(inputs, DEFAULT_CLUSTER_THRESHOLD)

    try:
        ids, sim = matrix_from_similarity_workbook(raw_bytes)
    except Exception as e:
        logger.exception("Matrix read failed")
        yield agent.status_response(content=_trace("lens_error", message=str(e)))
        yield agent.artifact_response(content=f"**Error reading matrix:** {e}", last_chunk=True)
        return

    n = len(ids)
    if n < 2:
        yield agent.artifact_response(content="Need at least two test cases in the matrix.", last_chunk=True)
        return

    roots, k = clusters_from_matrix(ids, sim, thr, strict_gt=True)
    eff = effectiveness_metrics(ids, sim, thr, strict_gt=True)

    root_to_label: dict[int, int] = {}
    next_lab = 1
    labels: list[int] = []
    for r in roots.tolist():
        if r not in root_to_label:
            root_to_label[r] = next_lab
            next_lab += 1
        labels.append(root_to_label[r])

    sizes: dict[int, int] = defaultdict(int)
    for lab in labels:
        sizes[lab] += 1

    rows = [
        {"tc_id": ids[i], "cluster_id": labels[i], "cluster_size": sizes[labels[i]]}
        for i in range(n)
    ]
    assign_df = pd.DataFrame(rows)

    summ_rows: list[dict[str, Any]] = []
    by_label: dict[int, list[str]] = defaultdict(list)
    for i in range(n):
        by_label[labels[i]].append(ids[i])
    for cid in sorted(by_label.keys()):
        members = sorted(by_label[cid])
        summ_rows.append(
            {
                "cluster_id": cid,
                "size": len(members),
                "members": ", ".join(members),
            }
        )
    summary_df = pd.DataFrame(summ_rows)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        assign_df.to_excel(writer, sheet_name="cluster_assignments", index=False)
        summary_df.to_excel(writer, sheet_name="cluster_summary", index=False)
    out_bytes = buf.getvalue()
    b64_out = base64.b64encode(out_bytes).decode("ascii")

    summary_md = (
        f"**Lens Agent 4 — clustering complete**\n\n"
        f"- Source: `{fname}`\n"
        f"- **n** = **{n}** test cases → **{k}** cluster(s) (union if **sim > {thr:.2f}**)\n"
        f"- Sheets: `cluster_assignments`, `cluster_summary`\n\n"
        f"**Effectiveness snapshot**\n\n"
        f"- Redundancy index `(n−K)/(n−1)`: **{eff['redundancy_index']}**\n"
        f"- Strict pair density (sim > τ): **{eff['strict_pair_density']}**\n"
        f"- Intra-cluster cohesion: **{eff.get('cohesion_index') or '—'}**\n"
    )

    parts = [
        Part(root=TextPart(text=summary_md)),
        Part(
            root=FilePart(
                file=FileWithBytes(
                    bytes=b64_out,
                    mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    name="lens_tc_clusters.xlsx",
                )
            )
        ),
    ]
    yield agent.artifact_response_by_parts(parts=parts, last_chunk=True)


async def maybe_chain_agent4_after_similarity(
    agent: "AgentLogicBase",
    input_data: dict[str, Any],
    *,
    similarity_inputs: dict[str, Any],
    similarity_xlsx_bytes: bytes,
    similarity_threshold: float,
) -> AsyncGenerator[TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:
    """If enabled on parent similarity request, call Agent 4 over HTTP A2A."""
    if not _chain_agent4_enabled(similarity_inputs):
        return

    thr_cluster = _cluster_threshold_from_inputs(similarity_inputs, similarity_threshold)

    yield agent.status_response(
        content=_trace(
            "a2a_handoff_agent4",
            message=(
                "Forwarding **lens_tc_similarity_matrix.xlsx** to **Agent 4** (`lens_tc_cluster_skill`, "
                f"merge if **sim > {thr_cluster:.2f}**) over **HTTP A2A**."
            ),
        )
    )
    try:
        from layers.lens_a2a_chain import invoke_agent4_cluster_skill_a2a

        trace_md, cluster_b, c_summ, err = await invoke_agent4_cluster_skill_a2a(
            input_data=input_data,
            similarity_matrix_bytes=similarity_xlsx_bytes,
            matrix_filename="lens_tc_similarity_matrix.xlsx",
            cluster_threshold=thr_cluster,
        )
    except Exception as e:
        logger.exception("A2A handoff to Agent 4 failed")
        yield agent.status_response(content=_trace("lens_error", message=f"A2A Agent 4 handoff failed: {e}"))
        return

    if err:
        yield agent.status_response(content=_trace("lens_error", message=f"A2A Agent 4: {err}"))
        if trace_md.strip():
            cap = 12_000
            tail = "…\n\n_(trace truncated)_" if len(trace_md) > cap else ""
            yield agent.status_response(content=f"### Agent 4 A2A trace (partial)\n\n{trace_md[:cap]}{tail}")
        return

    if trace_md.strip():
        cap = 10_000
        tail = "…\n\n_(trace truncated)_" if len(trace_md) > cap else ""
        yield agent.status_response(content=f"### Agent 4 A2A trace\n\n{trace_md[:cap]}{tail}")

    if cluster_b:
        b64c = base64.b64encode(cluster_b).decode("ascii")
        yield agent.artifact_response_by_parts(
            parts=[
                Part(root=TextPart(text=f"**Agent 4 (via A2A)**\n\n{c_summ}")),
                Part(
                    root=FilePart(
                        file=FileWithBytes(
                            bytes=b64c,
                            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            name="lens_tc_clusters.xlsx",
                        )
                    )
                ),
            ],
            last_chunk=True,
        )
