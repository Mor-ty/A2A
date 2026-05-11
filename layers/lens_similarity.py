"""
Lens — Agent 3: test-case similarity from connected states (decomposition Excel and/or Agent 2 graph HTML).

Vectorisation: TF–IDF (sparse embeddings) with row L2-normalisation; pairwise scores are cosine similarities.
Diagonal is forced to 1.0. Pairs with score ≥ threshold (default 0.8) are listed in a second sheet.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
from typing import Any, AsyncGenerator, TYPE_CHECKING

import numpy as np
import pandas as pd
from a2a.types import FilePart, FileWithBytes, Part, TaskArtifactUpdateEvent, TaskStatusUpdateEvent, TextPart
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

if TYPE_CHECKING:
    from agentic_os_infra.core.layers.agent_logic_base import AgentLogicBase

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = float(os.getenv("LENS_SIM_THRESHOLD", "0.8"))


def _trace(phase: str, **fields: object) -> dict:
    return {"kind": "trace", "phase": phase, **fields}


def _norm_col(c: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_")


def _find_col(df: pd.DataFrame, *candidates: str) -> str | None:
    m = {_norm_col(c): c for c in df.columns}
    for cand in candidates:
        k = _norm_col(cand)
        if k in m:
            return m[k]
    return None


def _decode_file(raw: Any, key: str) -> tuple[bytes, str] | None:
    if not raw or not isinstance(raw, dict):
        return None
    b64 = raw.get("bytes") or raw.get("data")
    name = raw.get("name") or raw.get("file_name") or key
    if not b64:
        return None
    return base64.b64decode(b64), str(name)


def _tc_docs_from_excel(df: pd.DataFrame) -> tuple[dict[str, str], str]:
    """One text document per test case: ordered initial→final chain."""
    ic = _find_col(df, "initial_state", "init", "initial", "from_state")
    fc = _find_col(df, "final_state", "final", "to_state")
    if not ic or not fc:
        raise ValueError(
            "Decomposition sheet must include initial_state and final_state columns. "
            f"Found: {list(df.columns)}"
        )
    tc_c = _find_col(df, "tc_id", "tcid", "test_case_id")
    step_c = _find_col(df, "step", "step_no", "step_id")
    if not tc_c:
        raise ValueError("Need tc_id (or tcid) column to group rows per test case.")

    tmp: dict[str, list[tuple[float, str]]] = {}
    for _, r in df.iterrows():
        tid = str(r.get(tc_c) or "").strip()
        if not tid or tid.lower() == "nan":
            continue
        a, b = r.get(ic), r.get(fc)
        if pd.isna(a) or pd.isna(b):
            continue
        sa, sb = str(a).strip(), str(b).strip()
        if not sa or not sb:
            continue
        step_val: float = 0.0
        if step_c and not pd.isna(r.get(step_c)):
            try:
                step_val = float(str(r.get(step_c)).strip())
            except ValueError:
                step_val = 0.0
        frag = f"{sa} → {sb}"
        tmp.setdefault(tid, []).append((step_val, frag))

    docs: dict[str, str] = {}
    for tid, pairs in tmp.items():
        pairs.sort(key=lambda x: (x[0], x[1]))
        chain = " | ".join(p[1] for p in pairs)
        if chain:
            docs[tid] = chain
    if len(docs) < 2:
        raise ValueError("Need at least two distinct test case ids with state rows for a similarity matrix.")
    return docs, "excel"


def _extract_first_json_array(html: str, prefix: str) -> list[dict[str, Any]] | None:
    """Find `prefix` + '(' then parse balanced JSON array."""
    i = html.find(prefix)
    if i < 0:
        return None
    j = html.find("(", i)
    if j < 0:
        return None
    start = j + 1
    while start < len(html) and html[start] in " \t\n\r":
        start += 1
    if start >= len(html) or html[start] != "[":
        return None
    depth = 0
    for k in range(start, len(html)):
        ch = html[k]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start : k + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _tcs_from_vis_title(title: str) -> list[str]:
    if not title:
        return []
    # Strip simple HTML tags
    t = re.sub(r"<[^>]+>", " ", title)
    m = re.search(r"TCs:\s*([^\n<]+)", t, re.IGNORECASE)
    if not m:
        return []
    raw = m.group(1).replace("…", "").strip()
    parts = re.split(r"[,;\s]+", raw)
    return [p.strip() for p in parts if p.strip() and p.strip().lower() != "nan"]


def _tc_docs_from_lens_html(html_text: str) -> tuple[dict[str, str], str]:
    """Recover per-TC state bags from Lens Agent 2 vis-network HTML (node titles list TCs)."""
    nodes = _extract_first_json_array(html_text, "new vis.DataSet")
    if not nodes:
        raise ValueError(
            "Could not parse vis-network nodes from HTML. "
            "Upload the decomposition `.xlsx` instead, or a graph HTML produced by Lens Agent 2."
        )
    tc_to_labels: dict[str, set[str]] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        label = str(n.get("label") or "").strip()
        title = str(n.get("title") or "")
        if not label:
            continue
        for tid in _tcs_from_vis_title(title):
            tc_to_labels.setdefault(tid, set()).add(label)
    docs = {tid: " | ".join(sorted(labels)) for tid, labels in tc_to_labels.items() if labels}
    if len(docs) < 2:
        raise ValueError(
            "Fewer than two test cases with recoverable state labels from graph HTML. "
            "Use the decomposition Excel (same file as Agent 2 input) for reliable similarity."
        )
    return docs, "html"


def _cosine_similarity_matrix(documents: list[str]) -> np.ndarray:
    vec = TfidfVectorizer(
        min_df=1,
        sublinear_tf=True,
        ngram_range=(1, 2),
        token_pattern=r"(?u)\b\w+\b",  # allow single-letter tokens (default requires len≥2)
    )
    X = vec.fit_transform(documents)
    Xn = normalize(X, norm="l2", axis=1)
    sim = (Xn @ Xn.T).toarray().astype(np.float64)
    np.fill_diagonal(sim, 1.0)
    # numerical symmetry
    sim = (sim + sim.T) / 2.0
    np.fill_diagonal(sim, 1.0)
    return sim


def _pairs_above_threshold(ids: list[str], sim: np.ndarray, threshold: float) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    n = len(ids)
    for i in range(n):
        for j in range(i + 1, n):
            v = float(sim[i, j])
            if v >= threshold:
                rows.append({"tc_id_a": ids[i], "tc_id_b": ids[j], "cosine_similarity": round(v, 6)})
    return pd.DataFrame(rows)


async def run_lens_tc_similarity(
    agent: "AgentLogicBase",
    input_data: dict[str, Any],
) -> AsyncGenerator[TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:
    yield agent.status_response(content="Lens Agent 3 — loading inputs for similarity")

    inputs = input_data.get("entityConfig", {}).get("inputs", {})
    thr_raw = inputs.get("similarity_threshold")
    try:
        threshold = float(thr_raw) if thr_raw is not None else DEFAULT_THRESHOLD
    except (TypeError, ValueError):
        threshold = DEFAULT_THRESHOLD
    threshold = max(0.0, min(1.0, threshold))

    wb = _decode_file(inputs.get("decomposition_workbook"), "workbook.xlsx")
    html_in = _decode_file(inputs.get("graph_html"), "graph.html")

    if not wb and not html_in:
        yield agent.status_response(
            content=_trace(
                "lens_error",
                message="Provide `decomposition_workbook` (.xlsx) and/or `graph_html` (Agent 2 HTML).",
            )
        )
        yield agent.artifact_response(
            content="Missing input: upload decomposition Excel (same as Agent 2 input) and/or Lens graph HTML.",
            last_chunk=True,
        )
        return

    docs: dict[str, str] = {}
    source = ""

    if wb:
        try:
            df = pd.read_excel(io.BytesIO(wb[0]), engine="openpyxl")
            d_excel, source = _tc_docs_from_excel(df)
            docs = d_excel
        except Exception as e:
            logger.exception("Excel parse failed")
            yield agent.status_response(content=_trace("lens_error", message=str(e)))
            yield agent.artifact_response(content=f"**Error reading Excel:** {e}", last_chunk=True)
            return

    if html_in:
        try:
            text = html_in[0].decode("utf-8", errors="replace")
            d_html, src2 = _tc_docs_from_lens_html(text)
            if docs:
                # Prefer Excel-derived docs; merge any TC only in HTML
                for k, v in d_html.items():
                    docs.setdefault(k, v)
                source = f"{source}+html" if source else src2
            else:
                docs = d_html
                source = src2
        except Exception as e:
            logger.warning("HTML parse skipped or failed: %s", e)
            if not docs:
                yield agent.status_response(content=_trace("lens_error", message=str(e)))
                yield agent.artifact_response(content=f"**Error reading graph HTML:** {e}", last_chunk=True)
                return

    if len(docs) < 2:
        yield agent.artifact_response(
            content="Need at least two test cases with non-empty state text.", last_chunk=True
        )
        return

    ids = sorted(docs.keys(), key=lambda x: (len(str(x)), str(x)))
    texts = [docs[i] for i in ids]
    n = len(ids)
    pairs_ct = n * (n - 1) // 2

    yield agent.status_response(
        content=_trace(
            "lens_progress",
            message=(
                f"Building TF–IDF vectors for **{n}** test cases ({pairs_ct} unique pairs, diagonal=1). "
                f"Source: **{source or 'excel'}**. Threshold **{threshold:.2f}** for pair listing."
            ),
        )
    )

    try:
        sim = _cosine_similarity_matrix(texts)
    except ValueError as e:
        yield agent.status_response(content=_trace("lens_error", message=str(e)))
        yield agent.artifact_response(
            content=f"**Similarity failed:** {e}\nTry richer state labels or ensure each test case has non-empty text.",
            last_chunk=True,
        )
        return

    mat_df = pd.DataFrame(sim, index=ids, columns=ids)
    pairs_df = _pairs_above_threshold(ids, sim, threshold)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        mat_df.to_excel(writer, sheet_name="similarity_matrix")
        pairs_df.to_excel(writer, sheet_name="pairs_ge_threshold", index=False)
    out_bytes = buf.getvalue()
    b64_out = base64.b64encode(out_bytes).decode("ascii")

    summary = (
        f"**Lens Agent 3 — similarity matrix**\n\n"
        f"- Test cases (**n**): **{n}** (pairwise upper triangle: **{pairs_ct}** scores)\n"
        f"- Vectorisation: **TF–IDF** (sparse), similarity = **cosine** of row vectors\n"
        f"- Diagonal: **1.0** (self-similarity)\n"
        f"- Threshold for `pairs_ge_threshold` sheet: **≥ {threshold:.2f}** → **{len(pairs_df)}** pair(s)\n"
        f"- Input source: `{source or 'excel'}`\n\n"
        "Sheets: `similarity_matrix` (n×n), `pairs_ge_threshold` (tc_id_a, tc_id_b, cosine_similarity)."
    )

    parts = [
        Part(root=TextPart(text=summary)),
        Part(
            root=FilePart(
                file=FileWithBytes(
                    bytes=b64_out,
                    mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    name="lens_tc_similarity_matrix.xlsx",
                )
            )
        ),
    ]
    yield agent.artifact_response_by_parts(parts=parts, last_chunk=True)
