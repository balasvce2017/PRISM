"""Inter-annotator agreement metrics."""
from typing import Optional
import numpy as np
from sklearn.metrics import cohen_kappa_score
import krippendorff


def compute_pairwise_kappa(annotations: list[dict], project_codes: list[dict]) -> dict:
    """
    Compute pairwise Cohen's κ between every pair of annotators.

    For each code, builds a binary (0/1) vector per annotator over all traces
    that both annotators have reviewed. Returns per-code and macro-averaged κ.
    """
    # Build lookup: {(trace_id, annotator_id): set of code_ids}
    lookup: dict[tuple, set] = {}
    for ann in annotations:
        key = (ann["trace_id"], ann["annotator_id"])
        lookup.setdefault(key, set()).add(ann["code_id"])

    annotator_ids = list({ann["annotator_id"] for ann in annotations})
    annotator_names = {ann["annotator_id"]: ann["annotator_name"] for ann in annotations}
    trace_ids = list({ann["trace_id"] for ann in annotations})
    code_ids  = [c["id"] for c in project_codes]

    results = {}
    for i in range(len(annotator_ids)):
        for j in range(i + 1, len(annotator_ids)):
            a1, a2 = annotator_ids[i], annotator_ids[j]
            n1, n2 = annotator_names[a1], annotator_names[a2]

            # traces reviewed by both
            common = [t for t in trace_ids
                      if (t, a1) in lookup or (t, a2) in lookup]
            if len(common) < 2:
                continue

            kappas = []
            for cid in code_ids:
                y1 = [1 if cid in lookup.get((t, a1), set()) else 0 for t in common]
                y2 = [1 if cid in lookup.get((t, a2), set()) else 0 for t in common]
                if len(set(y1)) < 2 and len(set(y2)) < 2:
                    continue  # no variance — skip
                try:
                    kappas.append(cohen_kappa_score(y1, y2))
                except Exception:
                    pass

            pair_key = f"{n1} ↔ {n2}"
            results[pair_key] = {
                "annotators": (n1, n2),
                "n_traces":   len(common),
                "macro_kappa": float(np.mean(kappas)) if kappas else None,
                "n_codes_evaluated": len(kappas),
            }

    return results


def compute_per_code_kappa(annotations: list[dict], project_codes: list[dict]) -> list[dict]:
    """Per-code κ averaged over all annotator pairs."""
    lookup: dict[tuple, set] = {}
    for ann in annotations:
        key = (ann["trace_id"], ann["annotator_id"])
        lookup.setdefault(key, set()).add(ann["code_id"])

    annotator_ids = list({ann["annotator_id"] for ann in annotations})
    trace_ids     = list({ann["trace_id"]     for ann in annotations})

    rows = []
    for code in project_codes:
        cid   = code["id"]
        label = code["label"]
        pair_kappas = []
        for i in range(len(annotator_ids)):
            for j in range(i + 1, len(annotator_ids)):
                a1, a2 = annotator_ids[i], annotator_ids[j]
                common = [t for t in trace_ids
                          if (t, a1) in lookup or (t, a2) in lookup]
                if len(common) < 2:
                    continue
                y1 = [1 if cid in lookup.get((t, a1), set()) else 0 for t in common]
                y2 = [1 if cid in lookup.get((t, a2), set()) else 0 for t in common]
                if len(set(y1)) < 2 and len(set(y2)) < 2:
                    continue
                try:
                    pair_kappas.append(cohen_kappa_score(y1, y2))
                except Exception:
                    pass
        usage = sum(1 for ann in annotations if ann["code_id"] == cid)
        rows.append({
            "code":     label,
            "category": code.get("category", "General"),
            "usage":    usage,
            "kappa":    float(np.mean(pair_kappas)) if pair_kappas else None,
            "n_pairs":  len(pair_kappas),
        })
    return sorted(rows, key=lambda r: r["kappa"] if r["kappa"] is not None else 99)


def compute_krippendorff_alpha(annotations: list[dict], trace_ids: list[str]) -> Optional[float]:
    """
    Nominal Krippendorff's α across all annotators.
    Unit of analysis: trace. Value: number of distinct codes assigned.
    """
    annotator_ids = list({ann["annotator_id"] for ann in annotations})
    if len(annotator_ids) < 2:
        return None

    lookup: dict[tuple, set] = {}
    for ann in annotations:
        lookup.setdefault((ann["trace_id"], ann["annotator_id"]), set()).add(ann["code_id"])

    # reliability data matrix: rows=annotators, cols=traces
    matrix = []
    for aid in annotator_ids:
        row = [len(lookup.get((t, aid), set())) for t in trace_ids]
        matrix.append(row)

    try:
        return float(krippendorff.alpha(reliability_data=matrix, level_of_measurement="interval"))
    except Exception:
        return None
