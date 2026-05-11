"""
Shared similarity → clustering metrics (union-find) and effectiveness scores for Lens Agent 3 / UI.
"""

from __future__ import annotations

import io
from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd


class _UnionFind:
    def __init__(self, n: int):
        self.p = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        if self.p[x] != x:
            self.p[x] = self.find(self.p[x])
        return self.p[x]

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.p[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def clusters_from_matrix(
    ids: list[str],
    sim: np.ndarray,
    threshold: float,
    *,
    strict_gt: bool = True,
) -> tuple[np.ndarray, int]:
    """
    Disjoint-set clustering: union (i,j) iff sim(i,j) > threshold (default strict).

    Returns (labels shape (n,) with component root ids per index, number_of_distinct_clusters).
    """
    n = len(ids)
    if sim.shape != (n, n):
        raise ValueError(f"Expected sim shape ({n},{n}), got {sim.shape}")

    uf = _UnionFind(n)
    cmp_op = np.greater if strict_gt else np.greater_equal

    for i in range(n):
        for j in range(i + 1, n):
            if cmp_op(sim[i, j], threshold):
                uf.union(i, j)

    roots = np.array([uf.find(i) for i in range(n)], dtype=np.int64)
    cluster_count = len(set(roots.tolist()))
    return roots, cluster_count


def effectiveness_metrics(
    ids: list[str],
    sim: np.ndarray,
    threshold: float,
    *,
    strict_gt: bool = True,
) -> dict[str, Any]:
    """
    Effectiveness / structure metrics after similarity (aligned with strict > clustering).

    - redundancy_index: (n - K) / max(n-1, 1) — how much the suite collapses under τ-merge.
    - strict_pair_density: fraction of off-diagonal pairs with sim > τ.
    - cohesion_index: mean pairwise similarity inside multi-member clusters (empty if all singletons).
    """
    n = len(ids)
    roots, k = clusters_from_matrix(ids, sim, threshold, strict_gt=strict_gt)
    pair_total = n * (n - 1) // 2

    cmp_op = np.greater if strict_gt else np.greater_equal
    pairs_strict = 0
    for i in range(n):
        for j in range(i + 1, n):
            if cmp_op(sim[i, j], threshold):
                pairs_strict += 1

    strict_density = float(pairs_strict / pair_total) if pair_total else 0.0
    redundancy_index = float((n - k) / max(n - 1, 1)) if n > 1 else 0.0

    # Group indices by cluster root
    by_root: dict[int, list[int]] = defaultdict(list)
    for idx, r in enumerate(roots.tolist()):
        by_root[r].append(idx)

    cohesion_vals: list[float] = []
    for members in by_root.values():
        if len(members) < 2:
            continue
        acc: list[float] = []
        for ii in range(len(members)):
            for jj in range(ii + 1, len(members)):
                a, b = members[ii], members[jj]
                acc.append(float(sim[a, b]))
        if acc:
            cohesion_vals.append(float(np.mean(acc)))

    cohesion_index = float(np.mean(cohesion_vals)) if cohesion_vals else None

    return {
        "n_test_cases": n,
        "cluster_count": k,
        "threshold": float(threshold),
        "strict_inequality": strict_gt,
        "pairs_above_strict": pairs_strict,
        "pair_total_offdiag": pair_total,
        "strict_pair_density": round(strict_density, 6),
        "redundancy_index": round(redundancy_index, 6),
        "cohesion_index": None if cohesion_index is None else round(cohesion_index, 6),
    }


def effectiveness_markdown(m: dict[str, Any]) -> str:
    """Human-readable block for trace / Gradio."""
    coh = m.get("cohesion_index")
    coh_s = f"{coh:.4f}" if coh is not None else "— (all singleton clusters)"
    rel = (
        f"| Metric | Value |\n"
        f"| --- | --- |\n"
        f"| Test cases **n** | **{m['n_test_cases']}** |\n"
        f"| Clusters **K** (union if sim {'>' if m.get('strict_inequality') else '≥'} τ) | **{m['cluster_count']}** |\n"
        f"| τ | **{m['threshold']:.2f}** |\n"
        f"| Pairs with sim {'>' if m.get('strict_inequality') else '≥'} τ | **{m['pairs_above_strict']}** / {m['pair_total_offdiag']} |\n"
        f"| **Strict pair density** | **{m['strict_pair_density']:.4f}** |\n"
        f"| **Redundancy index** `(n−K)/(n−1)` | **{m['redundancy_index']:.4f}** |\n"
        f"| **Intra-cluster cohesion** (mean pairwise sim in clusters with ≥2 TCs) | **{coh_s}** |\n"
    )
    return "### Effectiveness (post–similarity)\n\n" + rel


def matrix_from_similarity_workbook(buf: bytes) -> tuple[list[str], np.ndarray]:
    df = pd.read_excel(io.BytesIO(buf), sheet_name="similarity_matrix", engine="openpyxl", index_col=0)
    ids = [str(x) for x in df.index.tolist()]
    cols = [str(x) for x in df.columns.tolist()]
    if ids != cols:
        df = df.reindex(index=ids, columns=ids)
    mat = df.astype(np.float64).values
    return ids, mat

