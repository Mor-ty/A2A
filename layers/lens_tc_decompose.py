"""
Lens — Agent 1: decompose automation test cases from Excel into initial/final state steps.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
from typing import Any, AsyncGenerator, TYPE_CHECKING

import pandas as pd
from a2a.types import FilePart, FileWithBytes, Part, TaskArtifactUpdateEvent, TaskStatusUpdateEvent, TextPart

if TYPE_CHECKING:
    from agentic_os_infra.core.layers.agent_logic_base import AgentLogicBase

logger = logging.getLogger(__name__)

DESC_CANDIDATES = (
    "tc_description",
    "tc desc",
    "test case description",
    "description",
    "tc_desc",
    "scenario",
)

ID_CANDIDATES = ("tc_id", "tcid", "test case id", "testcaseid", "id")
ASSET_CANDIDATES = ("asset_id", "assetid", "asset id")
APP_CANDIDATES = ("app_id", "appid", "application id", "app id")
NAME_CANDIDATES = ("tc_name", "test case name", "name", "title")


def _chain_agent2_enabled(inputs: dict[str, Any]) -> bool:
    """Chain to Agent 2 over HTTP A2A unless disabled via env or request inputs."""
    env = (os.getenv("LENS_CHAIN_AGENT2_VIA_A2A") or "1").strip().lower()
    if env in ("0", "false", "no", "off"):
        opt = inputs.get("lens_chain_agent2")
        if opt is True:
            return True
        if isinstance(opt, str) and opt.strip().lower() in ("1", "true", "yes", "on"):
            return True
        return False
    opt = inputs.get("lens_chain_agent2")
    if opt is False:
        return False
    if isinstance(opt, str) and opt.strip().lower() in ("0", "false", "no", "off"):
        return False
    return True


def _trace(phase: str, **fields: object) -> dict:
    return {"kind": "trace", "phase": phase, **fields}


def _norm_col(c: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_")


def _find_column(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    norm_map = {_norm_col(c): c for c in df.columns}
    for cand in candidates:
        key = _norm_col(cand)
        if key in norm_map:
            return norm_map[key]
    return None


def _workbook_bytes_from_inputs(inputs: dict[str, Any]) -> tuple[bytes, str]:
    raw = inputs.get("workbook") or inputs.get("workbook_file") or inputs.get("excel_file")
    if not raw:
        raise ValueError("No workbook uploaded. Expected inputs.workbook with name, mime_type, and bytes (base64).")
    if isinstance(raw, dict):
        b64 = raw.get("bytes") or raw.get("data")
        name = raw.get("name") or raw.get("file_name") or "upload.xlsx"
        if not b64:
            raise ValueError("Workbook dict missing base64 bytes.")
        if isinstance(b64, str):
            return base64.b64decode(b64), str(name)
        raise ValueError("Workbook bytes must be base64-encoded string.")
    raise ValueError("Unsupported workbook payload type.")


def _rows_from_dataframe(df: pd.DataFrame) -> list[dict[str, Any]]:
    desc_c = _find_column(df, DESC_CANDIDATES)
    if not desc_c:
        raise ValueError(
            "Could not find a test-case description column. "
            f"Expected one of: {DESC_CANDIDATES}. Columns present: {list(df.columns)}"
        )
    id_c = _find_column(df, ID_CANDIDATES)
    asset_c = _find_column(df, ASSET_CANDIDATES)
    app_c = _find_column(df, APP_CANDIDATES)
    name_c = _find_column(df, NAME_CANDIDATES)

    rows: list[dict[str, Any]] = []
    for offset, (_, r) in enumerate(df.iterrows()):
        text = r.get(desc_c)
        if text is None or (isinstance(text, float) and pd.isna(text)):
            continue
        text_s = str(text).strip()
        if not text_s:
            continue
        row: dict[str, Any] = {"row_index": offset + 2, "tc_description": text_s}  # row 1 = header
        if id_c:
            v = r.get(id_c)
            row["tc_id"] = "" if pd.isna(v) else str(v).strip()
        if asset_c:
            v = r.get(asset_c)
            row["asset_id"] = "" if pd.isna(v) else str(v).strip()
        if app_c:
            v = r.get(app_c)
            row["app_id"] = "" if pd.isna(v) else str(v).strip()
        if name_c:
            v = r.get(name_c)
            row["tc_name"] = "" if pd.isna(v) else str(v).strip()
        rows.append(row)
    return rows


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", t, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return t


def _parse_llm_json(text: str) -> dict[str, Any]:
    raw = _strip_json_fence(text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
        raise


def _build_user_prompt(batch: list[dict[str, Any]]) -> str:
    return (
        "Decompose EACH test case below into ordered UI/state steps.\n"
        "Rules:\n"
        "- For each test case output a list `steps`: each step has integer `step` (1-based), "
        "`initial_state` (short label), `final_state` (short label).\n"
        "- Step 1 `initial_state` is the starting point before the first action in the description.\n"
        "- For step k>1, `initial_state` should align with the end state of the prior step (same screen/context where reasonable).\n"
        "- Keep labels concise (2–8 words) suitable for automation.\n"
        "- Cover the full TC_description without inventing unrelated flows.\n\n"
        "Return ONLY valid JSON of this shape (no markdown outside JSON):\n"
        '{"test_cases":['
        '{"tc_id":"...","asset_id":"...","app_id":"...","tc_name":"...","row_index":2,'
        '"steps":[{"step":1,"initial_state":"...","final_state":"..."}]}'
        "]}\n\n"
        "Test cases JSON:\n"
        + json.dumps(batch, ensure_ascii=False)
    )


async def run_lens_tc_decompose(
    agent: "AgentLogicBase",
    input_data: dict[str, Any],
) -> AsyncGenerator[TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:
    yield agent.status_response(content="Lens — loading workbook")

    inputs = input_data.get("entityConfig", {}).get("inputs", {})
    try:
        file_bytes, filename = _workbook_bytes_from_inputs(inputs)
    except ValueError as e:
        yield agent.status_response(content=_trace("lens_error", message=str(e)))
        yield agent.artifact_response(content=f"**Error:** {e}", last_chunk=True)
        return

    try:
        df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
    except Exception as e:
        logger.exception("Excel read failed")
        yield agent.status_response(content=_trace("lens_error", message=str(e)))
        yield agent.artifact_response(content=f"**Error reading Excel:** {e}", last_chunk=True)
        return

    rows = _rows_from_dataframe(df)
    if not rows:
        yield agent.artifact_response(
            content="No test cases found (empty description column or sheet).", last_chunk=True
        )
        return

    yield agent.status_response(
        content=_trace("lens_progress", message=f"Found {len(rows)} test case(s) in `{filename}`. Decomposing…")
    )

    batch_size = max(1, int(os.getenv("LENS_TCS_PER_LLM_BATCH", "6")))
    system = (
        agent.llm_adapter.system_prompt
        or "You are Lens, an expert test-automation analyst. You output strict JSON only."
    )

    all_flat: list[dict[str, Any]] = []
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        yield agent.status_response(
            content=_trace(
                "lens_batch",
                batch_start=start + 1,
                batch_end=min(start + batch_size, len(rows)),
                total=len(rows),
            )
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": _build_user_prompt(batch)},
        ]
        response = await agent.llm_adapter.llm_chat(messages)
        text = response if isinstance(response, str) else getattr(response, "content", "") or ""
        if isinstance(text, list):
            text = json.dumps(text, ensure_ascii=False)
        try:
            parsed = _parse_llm_json(str(text))
        except Exception as e:
            logger.warning("JSON parse failed, retrying with repair hint: %s", e)
            repair = await agent.llm_adapter.llm_chat(
                messages
                + [{"role": "assistant", "content": str(text)}]
                + [
                    {
                        "role": "user",
                        "content": "Your previous reply was not valid JSON. "
                        "Reply with ONLY one JSON object matching the requested schema.",
                    }
                ]
            )
            t2 = repair if isinstance(repair, str) else getattr(repair, "content", "") or ""
            if isinstance(t2, list):
                t2 = json.dumps(t2, ensure_ascii=False)
            parsed = _parse_llm_json(str(t2))

        tcs = parsed.get("test_cases") or []
        for i, batch_row in enumerate(batch):
            tc = tcs[i] if i < len(tcs) else {}
            meta = {
                "tc_id": batch_row.get("tc_id") or tc.get("tc_id", ""),
                "asset_id": batch_row.get("asset_id") or tc.get("asset_id", ""),
                "app_id": batch_row.get("app_id") or tc.get("app_id", ""),
                "tc_name": batch_row.get("tc_name") or tc.get("tc_name", ""),
                "row_index": batch_row.get("row_index") or tc.get("row_index", ""),
                "tc_description": batch_row.get("tc_description", ""),
            }
            for step in tc.get("steps") or []:
                all_flat.append(
                    {
                        **meta,
                        "step": step.get("step"),
                        "initial_state": step.get("initial_state", ""),
                        "final_state": step.get("final_state", ""),
                    }
                )

    out_df = pd.DataFrame(all_flat)
    if out_df.empty:
        yield agent.artifact_response(
            content="Model returned no steps. Try again or reduce batch size.", last_chunk=True
        )
        return

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        out_df.to_excel(writer, sheet_name="decomposed_steps", index=False)
    xlsx_bytes = buf.getvalue()
    b64_out = base64.b64encode(xlsx_bytes).decode("ascii")

    summary = (
        f"**Lens — decomposition complete**\n\n"
        f"- Source file: `{filename}`\n"
        f"- Input test cases: **{len(rows)}**\n"
        f"- Output rows (step table): **{len(out_df)}**\n\n"
        "Download the Excel artifact attached in the A2A response (Gradio shows it as a file when available)."
    )

    file_part = FileWithBytes(
        bytes=b64_out,
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        name="lens_decomposed_steps.xlsx",
    )
    parts = [
        Part(root=TextPart(text=summary)),
        Part(root=FilePart(file=file_part)),
    ]
    yield agent.artifact_response_by_parts(parts=parts, last_chunk=True)

    if not _chain_agent2_enabled(inputs):
        from layers.lens_graph_visualiser import _chain_agent3_enabled, _similarity_threshold_from_inputs

        if _chain_agent3_enabled(inputs):
            thr = _similarity_threshold_from_inputs(inputs)
            yield agent.status_response(
                content=_trace(
                    "a2a_handoff_agent3",
                    message=(
                        "Agent 2 skipped; forwarding **Agent 1 decomposition workbook** to **Agent 3** "
                        f"(`lens_tc_similarity_skill`, threshold **{thr:.2f}**) over **HTTP A2A**."
                    ),
                )
            )
            try:
                from layers.lens_a2a_chain import invoke_agent3_similarity_skill_a2a

                t3, sim_only, cluster_only, s_summ, err3 = await invoke_agent3_similarity_skill_a2a(
                    input_data=input_data,
                    decomposition_xlsx_bytes=xlsx_bytes,
                    decomposition_filename="lens_decomposed_steps.xlsx",
                    similarity_threshold=thr,
                )
            except Exception as e:
                logger.exception("A2A handoff to Agent 3 failed")
                yield agent.status_response(
                    content=_trace("lens_error", message=f"A2A Agent 3 handoff failed: {e}")
                )
                return

            if err3:
                yield agent.status_response(content=_trace("lens_error", message=f"A2A Agent 3: {err3}"))
                if t3.strip():
                    cap = 12_000
                    tail = "…\n\n_(trace truncated)_" if len(t3) > cap else ""
                    yield agent.status_response(content=f"### Agent 3 A2A trace (partial)\n\n{t3[:cap]}{tail}")
                return

            if t3.strip():
                cap = 10_000
                tail = "…\n\n_(trace truncated)_" if len(t3) > cap else ""
                yield agent.status_response(content=f"### Agent 3 A2A trace\n\n{t3[:cap]}{tail}")

            if sim_only:
                b64z = base64.b64encode(sim_only).decode("ascii")
                yield agent.artifact_response_by_parts(
                    parts=[
                        Part(root=TextPart(text=f"**Agent 3 (via A2A)**\n\n{s_summ}")),
                        Part(
                            root=FilePart(
                                file=FileWithBytes(
                                    bytes=b64z,
                                    mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    name="lens_tc_similarity_matrix.xlsx",
                                )
                            )
                        ),
                    ],
                    last_chunk=True,
                )

            if cluster_only:
                b64c = base64.b64encode(cluster_only).decode("ascii")
                yield agent.artifact_response_by_parts(
                    parts=[
                        Part(root=TextPart(text="**Agent 4 (via A2A)** — clusters from similarity matrix.")),
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
        return

    yield agent.status_response(
        content=_trace(
            "a2a_handoff",
            message=(
                "Forwarding `lens_decomposed_steps.xlsx` to **Agent 2** "
                "(`lens_graph_visualiser_skill`) over **HTTP A2A** (same Lens URL, new child `context_id`)."
            ),
        )
    )
    try:
        from layers.lens_a2a_chain import invoke_agent2_graph_skill_a2a

        trace_md, html_b, sim_xlsx_b, cluster_xlsx_b, g_summ, err = await invoke_agent2_graph_skill_a2a(
            input_data=input_data,
            decomposition_excel_bytes=xlsx_bytes,
            filename="lens_decomposed_steps.xlsx",
        )
    except Exception as e:
        logger.exception("A2A handoff to Agent 2 failed")
        yield agent.status_response(
            content=_trace("lens_error", message=f"A2A Agent 2 handoff failed: {e}")
        )
        return

    if err:
        yield agent.status_response(content=_trace("lens_error", message=f"A2A Agent 2: {err}"))
        if trace_md.strip():
            cap = 12_000
            tail = "…\n\n_(trace truncated)_" if len(trace_md) > cap else ""
            yield agent.status_response(content=f"### Agent 2 A2A trace (partial)\n\n{trace_md[:cap]}{tail}")
        return

    if trace_md.strip():
        cap = 10_000
        tail = "…\n\n_(trace truncated)_" if len(trace_md) > cap else ""
        yield agent.status_response(content=f"### Agent 2 A2A trace\n\n{trace_md[:cap]}{tail}")

    if html_b:
        b64h = base64.b64encode(html_b).decode("ascii")
        parts2 = [
            Part(root=TextPart(text=f"**Agent 2 (via A2A)**\n\n{g_summ}")),
            Part(
                root=FilePart(
                    file=FileWithBytes(
                        bytes=b64h,
                        mime_type="text/html",
                        name="lens_flow_graph.html",
                    )
                )
            ),
        ]
        yield agent.artifact_response_by_parts(parts=parts2, last_chunk=True)

    if sim_xlsx_b:
        b64s = base64.b64encode(sim_xlsx_b).decode("ascii")
        parts3 = [
            Part(
                root=TextPart(
                    text=(
                        "**Agent 3 (via A2A, after Agent 2)** — similarity matrix from **Agent 1** "
                        "decomposition workbook (TF–IDF / cosine)."
                    )
                )
            ),
            Part(
                root=FilePart(
                    file=FileWithBytes(
                        bytes=b64s,
                        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        name="lens_tc_similarity_matrix.xlsx",
                    )
                )
            ),
        ]
        yield agent.artifact_response_by_parts(parts=parts3, last_chunk=True)

    if cluster_xlsx_b:
        b64c = base64.b64encode(cluster_xlsx_b).decode("ascii")
        yield agent.artifact_response_by_parts(
            parts=[
                Part(root=TextPart(text="**Agent 4 (via A2A)** — clusters from chained similarity matrix.")),
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
