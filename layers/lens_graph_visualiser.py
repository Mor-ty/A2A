"""
Lens — Agent 2: conservative deduplication + layered flow graph → interactive HTML (vis-network).
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
from collections import defaultdict
from typing import Any, AsyncGenerator, TYPE_CHECKING

import pandas as pd
from rapidfuzz import fuzz
from a2a.types import FilePart, FileWithBytes, Part, TaskArtifactUpdateEvent, TaskStatusUpdateEvent, TextPart

from layers.lens_similarity import DEFAULT_THRESHOLD as SIM_DEFAULT_THRESHOLD

if TYPE_CHECKING:
    from agentic_os_infra.core.layers.agent_logic_base import AgentLogicBase

logger = logging.getLogger(__name__)

GRAPH_SYSTEM = (
    "You are **Lens Agent 2 — Graph deduplication assistant**.\n"
    "You ONLY suggest merging UI/state phrases that are **unambiguously the same** for test automation "
    "(e.g. 'Login screen' and 'User is on login screen').\n"
    "Never merge an **action** with a **distinct outcome** unless they describe the same screen.\n"
    "When in doubt, **do not** merge.\n"
    "Reply with **valid JSON only** (no markdown fences).\n"
)

FUZZ_AUTO_MERGE = int(os.getenv("LENS_GRAPH_FUZZ_AUTO", "97"))
FUZZ_LLM_VALIDATE = int(os.getenv("LENS_GRAPH_FUZZ_LLM", "86"))
LLM_PAIR_CAP = int(os.getenv("LENS_GRAPH_LLM_MAX_PAIRS", "24"))
MAX_LAYERS = 8


def _trace(phase: str, **fields: object) -> dict:
    return {"kind": "trace", "phase": phase, **fields}


def _chain_agent3_enabled(inputs: dict[str, Any]) -> bool:
    """Chain to Agent 3 over HTTP A2A after graph HTML unless disabled."""
    env = (os.getenv("LENS_CHAIN_AGENT3_VIA_A2A") or "1").strip().lower()
    if env in ("0", "false", "no", "off"):
        opt = inputs.get("lens_chain_agent3")
        if opt is True:
            return True
        if isinstance(opt, str) and opt.strip().lower() in ("1", "true", "yes", "on"):
            return True
        return False
    opt = inputs.get("lens_chain_agent3")
    if opt is False:
        return False
    if isinstance(opt, str) and opt.strip().lower() in ("0", "false", "no", "off"):
        return False
    return True


def _similarity_threshold_from_inputs(inputs: dict[str, Any]) -> float:
    raw = inputs.get("similarity_threshold")
    try:
        v = float(raw) if raw is not None else SIM_DEFAULT_THRESHOLD
    except (TypeError, ValueError):
        v = SIM_DEFAULT_THRESHOLD
    return max(0.0, min(1.0, v))


def _norm(s: str) -> str:
    t = str(s or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"^user\s+", "", t)
    t = re.sub(r"^the\s+", "", t)
    return t


def _workbook_bytes(inputs: dict[str, Any]) -> tuple[bytes, str]:
    raw = inputs.get("decomposition_workbook") or inputs.get("workbook")
    if not raw or not isinstance(raw, dict):
        raise ValueError(
            "Missing decomposition workbook. Upload Agent 1 output (.xlsx) as "
            "`decomposition_workbook` with name, mime_type, bytes (base64)."
        )
    b64 = raw.get("bytes") or raw.get("data")
    name = raw.get("name") or raw.get("file_name") or "decomposition.xlsx"
    if not b64:
        raise ValueError("Workbook missing base64 bytes.")
    return base64.b64decode(b64), str(name)


def _find_col(df: pd.DataFrame, *candidates: str) -> str | None:
    m = {re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_"): c for c in df.columns}
    for cand in candidates:
        k = re.sub(r"[^a-z0-9]+", "_", cand.lower()).strip("_")
        if k in m:
            return m[k]
    return None


def _load_edges(df: pd.DataFrame) -> tuple[list[dict[str, Any]], list[str]]:
    ic = _find_col(df, "initial_state", "init", "initial", "from_state")
    fc = _find_col(df, "final_state", "final", "to_state")
    if not ic or not fc:
        raise ValueError(
            "Decomposition sheet must include initial_state and final_state columns. "
            f"Found: {list(df.columns)}"
        )
    tc_c = _find_col(df, "tc_id", "tcid", "test_case_id")
    step_c = _find_col(df, "step", "step_no", "step_id")

    edges: list[dict[str, Any]] = []
    labels: set[str] = set()
    for _, r in df.iterrows():
        a, b = r.get(ic), r.get(fc)
        if pd.isna(a) or pd.isna(b):
            continue
        sa, sb = str(a).strip(), str(b).strip()
        if not sa or not sb:
            continue
        labels.add(sa)
        labels.add(sb)
        edges.append(
            {
                "src": sa,
                "dst": sb,
                "tc_id": "" if not tc_c or pd.isna(r.get(tc_c)) else str(r.get(tc_c)).strip(),
                "step": "" if not step_c or pd.isna(r.get(step_c)) else str(r.get(step_c)).strip(),
            }
        )
    return edges, sorted(labels)


class _UnionFind:
    def __init__(self, items: list[str]):
        self.p = {x: x for x in items}

    def find(self, x: str) -> str:
        if x not in self.p:
            self.p[x] = x
        if self.p[x] != x:
            self.p[x] = self.find(self.p[x])
        return self.p[x]

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if ra.lower() <= rb.lower():
            self.p[rb] = ra
        else:
            self.p[ra] = rb


def _auto_merge(labels: list[str]) -> dict[str, str]:
    """Conservative fuzzy merge + normalized equality."""
    uf = _UnionFind(labels)
    for i, a in enumerate(labels):
        na = _norm(a)
        for b in labels[i + 1 :]:
            nb = _norm(b)
            if na == nb and na:
                uf.union(a, b)
                continue
            if len(a) < 4 or len(b) < 4:
                continue
            r = fuzz.ratio(a, b)
            ts = fuzz.token_set_ratio(a, b)
            if r >= FUZZ_AUTO_MERGE or ts >= FUZZ_AUTO_MERGE:
                uf.union(a, b)

    rep: dict[str, str] = {}
    for x in labels:
        r = uf.find(x)
        rep[x] = r
    return rep


async def _llm_extra_pairs(
    llm_adapter: Any,
    representatives: list[str],
) -> list[tuple[str, str]]:
    """Ask LLM for a small set of safe synonym pairs; validate with fuzzy floor."""
    if not representatives:
        return []
    chunk = representatives[:80]
    user = (
        "Given these UI/state labels from test automation (one per line), "
        f"return JSON: {{\"equivalent_pairs\":[{{\"a\":\"...\",\"b\":\"...\"}},...]}} "
        f"with at most {LLM_PAIR_CAP} pairs. Only include pairs that are **the same state** "
        "under different wording. Omit uncertain pairs.\n\n"
        + "\n".join(f"- {s}" for s in chunk)
    )
    messages = [
        {"role": "system", "content": GRAPH_SYSTEM},
        {"role": "user", "content": user},
    ]
    resp = await llm_adapter.llm_chat(messages)
    text = resp if isinstance(resp, str) else getattr(resp, "content", "") or ""
    if isinstance(text, list):
        text = json.dumps(text, ensure_ascii=False)
    text = str(text).strip()
    m = re.search(r"\{[\s\S]*\}\s*$", text)
    if not m:
        m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    out: list[tuple[str, str]] = []
    for p in data.get("equivalent_pairs") or []:
        a, b = (p.get("a") or "").strip(), (p.get("b") or "").strip()
        if not a or not b or a == b:
            continue
        if a not in representatives or b not in representatives:
            continue
        if fuzz.token_set_ratio(a, b) < FUZZ_LLM_VALIDATE and fuzz.ratio(a, b) < FUZZ_LLM_VALIDATE:
            continue
        out.append((a, b))
    return out


async def _llm_collect_all_pairs(llm_adapter: Any, reps: list[str]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    chunk_size = 55
    for off in range(0, len(reps), chunk_size):
        chunk = reps[off : off + chunk_size]
        part = await _llm_extra_pairs(llm_adapter, chunk)
        for a, b in part:
            key = tuple(sorted((a, b)))
            if key not in seen:
                seen.add(key)
                out.append((a, b))
    return out


def _apply_pairs(uf: _UnionFind, pairs: list[tuple[str, str]]) -> None:
    for a, b in pairs:
        uf.union(a, b)


def _merged_canonical(rep_map: dict[str, str], raw: str) -> str:
    return rep_map.get(raw, raw)


def _build_merged_graph(
    edges_raw: list[dict[str, Any]],
    rep_map: dict[str, str],
) -> tuple[dict[str, dict[str, Any]], list[tuple[str, str, int]]]:
    """Nodes keyed by canonical label; list of (src_canon, dst_canon, weight)."""
    w: dict[tuple[str, str], int] = defaultdict(int)
    for e in edges_raw:
        s = _merged_canonical(rep_map, e["src"])
        t = _merged_canonical(rep_map, e["dst"])
        if s == t:
            continue
        key = (s, t)
        w[key] += 1
    elist = [(a, b, c) for (a, b), c in w.items()]
    nodes: dict[str, dict[str, Any]] = {}
    for a, b, _ in elist:
        nodes.setdefault(a, {"aliases": set(), "tcs": set()})
        nodes.setdefault(b, {"aliases": set(), "tcs": set()})
    for raw, c in rep_map.items():
        if raw != c:
            nodes.setdefault(c, {"aliases": set(), "tcs": set()})
            nodes[c]["aliases"].add(raw)
    for e in edges_raw:
        c = _merged_canonical(rep_map, e["src"])
        if e.get("tc_id"):
            nodes[c]["tcs"].add(e["tc_id"])
        c2 = _merged_canonical(rep_map, e["dst"])
        if e.get("tc_id"):
            nodes[c2]["tcs"].add(e["tc_id"])
    return nodes, elist


def _assign_layers(
    elist: list[tuple[str, str, int]],
    nodes: dict[str, dict[str, Any]],
) -> dict[str, int]:
    """Longest-path layering from sources (deterministic, no extra LLM)."""
    preds: dict[str, set[str]] = defaultdict(set)
    succs: dict[str, set[str]] = defaultdict(set)
    for a, b, _ in elist:
        succs[a].add(b)
        preds[b].add(a)
    alln = set(nodes.keys())
    for a, b, _ in elist:
        alln.add(a)
        alln.add(b)
    sources = [n for n in alln if not preds.get(n)]
    if not sources:
        sources = sorted(alln)[:1]

    depth: dict[str, int] = {s: 0 for s in sources}
    stack = list(sources)
    while stack:
        u = stack.pop()
        du = depth.get(u, 0)
        for v in succs.get(u, ()):
            nd = du + 1
            if v not in depth or nd > depth[v]:
                depth[v] = nd
            stack.append(v)

    mx = max(depth.values(), default=0)
    layers: dict[str, int] = {}
    if mx == 0:
        for n in alln:
            layers[n] = 0
        return layers
    span = max(mx, 1)
    for n in alln:
        d = depth.get(n, 0)
        layers[n] = min(int(d * MAX_LAYERS / (span + 1)), MAX_LAYERS - 1)
    return layers


def _html_vis(nodes: dict[str, dict[str, Any]], elist: list[tuple[str, str, int]], layers: dict[str, int]) -> str:
    pal = [
        "#4e79a7",
        "#f28e2b",
        "#e15759",
        "#76b7b2",
        "#59a14f",
        "#edc948",
        "#b07aa1",
        "#ff9da7",
    ]
    nid = 0
    id_map: dict[str, int] = {}
    vis_nodes = []
    for label in sorted(nodes.keys()):
        id_map[label] = nid
        ly = layers.get(label, 0)
        meta = nodes[label]
        aliases = sorted(meta.get("aliases") or ())
        tcs = sorted(meta.get("tcs") or ())
        tip = f"<b>{label}</b><br>Layer: {ly + 1}<br>"
        if aliases:
            tip += "<br>Aliases: " + ", ".join(aliases[:12])
            if len(aliases) > 12:
                tip += "…"
        if tcs:
            tip += "<br>TCs: " + ", ".join(tcs[:20])
            if len(tcs) > 20:
                tip += "…"
        vis_nodes.append(
            {
                "id": nid,
                "label": label[:42] + ("…" if len(label) > 42 else ""),
                "title": tip,
                "group": ly,
                "color": pal[ly % len(pal)],
            }
        )
        nid += 1

    vis_edges = []
    for a, b, wt in elist:
        vis_edges.append(
            {
                "from": id_map[a],
                "to": id_map[b],
                "value": max(1, min(wt, 20)),
                "title": f"{wt} step(s)",
                "arrows": "to",
            }
        )

    nodes_json = json.dumps(vis_nodes, ensure_ascii=False)
    edges_json = json.dumps(vis_edges, ensure_ascii=False)
    tpl = """<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>body{margin:0;font-family:system-ui,sans-serif;}#net{width:100%;height:720px;border:1px solid #ccc;}</style>
</head><body>
<div id="net"></div>
<script>
const nodes = new vis.DataSet(___NODES___);
const edges = new vis.DataSet(___EDGES___);
const container = document.getElementById("net");
const data = { nodes, edges };
const options = {
  layout: { improvedLayout: true },
  physics: { enabled: true, stabilization: { iterations: 120 } },
  nodes: { shape: "box", margin: 10, font: { size: 13 } },
  edges: { smooth: true, scaling: { min: 1, max: 8 } },
  groups: { useDefaultGroups: false }
};
new vis.Network(container, data, options);
</script>
</body></html>"""
    return tpl.replace("___NODES___", nodes_json).replace("___EDGES___", edges_json)


async def run_lens_graph_visualiser(
    agent: "AgentLogicBase",
    input_data: dict[str, Any],
) -> AsyncGenerator[TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:
    yield agent.status_response(content="Lens Agent 2 — loading decomposition workbook")

    inputs = input_data.get("entityConfig", {}).get("inputs", {})
    try:
        raw_bytes, fname = _workbook_bytes(inputs)
    except ValueError as e:
        yield agent.status_response(content=_trace("lens_error", message=str(e)))
        yield agent.artifact_response(content=f"**Error:** {e}", last_chunk=True)
        return

    try:
        df = pd.read_excel(io.BytesIO(raw_bytes), engine="openpyxl")
    except Exception as e:
        logger.exception("Excel read failed")
        yield agent.status_response(content=_trace("lens_error", message=str(e)))
        yield agent.artifact_response(content=f"**Error reading Excel:** {e}", last_chunk=True)
        return

    try:
        edges_raw, labels = _load_edges(df)
    except ValueError as e:
        yield agent.artifact_response(content=f"**Error:** {e}", last_chunk=True)
        return

    if not edges_raw:
        yield agent.artifact_response(content="No edges found (empty states).", last_chunk=True)
        return

    yield agent.status_response(
        content=_trace(
            "lens_progress",
            message=f"Loaded **{len(edges_raw)}** edges, **{len(labels)}** unique labels from `{fname}`.",
        )
    )

    rep_map = _auto_merge(labels)
    reps = sorted({rep_map[l] for l in labels})
    yield agent.status_response(
        content=_trace("lens_progress", message="Running conservative LLM synonym pass (validated pairs only)…")
    )
    try:
        pairs = await _llm_collect_all_pairs(agent.llm_adapter, reps)
    except Exception as e:
        logger.warning("LLM synonym pass skipped: %s", e)
        pairs = []
    uf2 = _UnionFind(labels)
    for x in labels:
        uf2.union(x, rep_map[x])
    _apply_pairs(uf2, pairs)
    rep_map2 = {x: uf2.find(x) for x in labels}

    nodes, elist = _build_merged_graph(edges_raw, rep_map2)
    layers = _assign_layers(elist, nodes)
    html = _html_vis(nodes, elist, layers)

    merged_ct = len({rep_map2[l] for l in labels})
    summary = (
        f"**Lens Agent 2 — graph ready**\n\n"
        f"- Source: `{fname}`\n"
        f"- Raw labels: **{len(labels)}** → merged nodes: **{merged_ct}**\n"
        f"- Edges (after merge): **{len(elist)}**\n"
        f"- Layers: **{max(layers.values(), default=0) + 1}** (depth-based, max {MAX_LAYERS})\n"
        f"- LLM synonym pairs applied (validated): **{len(pairs)}**\n\n"
        "Open the HTML artifact for an interactive **vis-network** view (zoom, drag, tooltips)."
    )

    b64_html = base64.b64encode(html.encode("utf-8")).decode("ascii")
    parts = [
        Part(root=TextPart(text=summary)),
        Part(
            root=FilePart(
                file=FileWithBytes(
                    bytes=b64_html,
                    mime_type="text/html",
                    name="lens_flow_graph.html",
                )
            )
        ),
    ]
    yield agent.artifact_response_by_parts(parts=parts, last_chunk=True)

    if not _chain_agent3_enabled(inputs):
        return

    thr = _similarity_threshold_from_inputs(inputs)
    yield agent.status_response(
        content=_trace(
            "a2a_handoff_agent3",
            message=(
                "Forwarding **Agent 1 decomposition workbook** (`decomposition_workbook`, same bytes as graph input) "
                f"to **Agent 3** (`lens_tc_similarity_skill`, threshold **{thr:.2f}**) over **HTTP A2A** "
                "(new child `context_id`). Graph HTML is not required for similarity."
            ),
        )
    )
    try:
        from layers.lens_a2a_chain import invoke_agent3_similarity_skill_a2a

        trace_md, sim_b, cluster_b, s_summ, err = await invoke_agent3_similarity_skill_a2a(
            input_data=input_data,
            decomposition_xlsx_bytes=raw_bytes,
            decomposition_filename=fname,
            similarity_threshold=thr,
        )
    except Exception as e:
        logger.exception("A2A handoff to Agent 3 failed")
        yield agent.status_response(
            content=_trace("lens_error", message=f"A2A Agent 3 handoff failed: {e}")
        )
        return

    if err:
        yield agent.status_response(content=_trace("lens_error", message=f"A2A Agent 3: {err}"))
        if trace_md.strip():
            cap = 12_000
            tail = "…\n\n_(trace truncated)_" if len(trace_md) > cap else ""
            yield agent.status_response(content=f"### Agent 3 A2A trace (partial)\n\n{trace_md[:cap]}{tail}")
        return

    if trace_md.strip():
        cap = 10_000
        tail = "…\n\n_(trace truncated)_" if len(trace_md) > cap else ""
        yield agent.status_response(content=f"### Agent 3 A2A trace\n\n{trace_md[:cap]}{tail}")

    if sim_b:
        b64s = base64.b64encode(sim_b).decode("ascii")
        parts3 = [
            Part(
                root=TextPart(
                    text=(
                        f"**Agent 3 (via A2A)** — similarity from **Agent 1** decomposition workbook "
                        f"(same input as this graph run).\n\n{s_summ}"
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

    if cluster_b:
        b64c = base64.b64encode(cluster_b).decode("ascii")
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
