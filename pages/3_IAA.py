"""Step 3: Inter-Annotator Agreement dashboard."""
import streamlit as st
import pandas as pd
import plotly.express as px
from core import db, iaa

st.set_page_config(page_title="IAA · Prism", page_icon="📊", layout="wide")
from pathlib import Path  # noqa: E402
LOGO = str(Path(__file__).parent.parent / "assets" / "logo.svg")
st.logo(LOGO)
db.init()

st.title("📊 Step 3 — Inter-Annotator Agreement")
st.caption("Cohen's κ (pairwise) and Krippendorff's α across your annotated traces.")

project_id = st.session_state.get("project_id")
if not project_id:
    st.warning("Select a project on the Home page first.")
    st.stop()

annotations  = db.get_all_annotations_for_project(project_id)
project_codes = db.list_codes(project_id)
annotators   = db.list_annotators()

if len(annotators) < 2:
    st.info("IAA requires at least **2 annotators**. Keep coding — invite a colleague!")
    st.stop()
if not annotations:
    st.info("No annotations yet. Complete some coding in Step 2 first.")
    st.stop()

# ── Summary metrics ───────────────────────────────────────────────────────────
pairwise = iaa.compute_pairwise_kappa(annotations, project_codes)
per_code = iaa.compute_per_code_kappa(annotations, project_codes)

reviewed = db.get_review_status(project_id)
reviewed_traces = [tid for tid, names in reviewed.items() if len(names) >= 2]
alpha = iaa.compute_krippendorff_alpha(annotations, reviewed_traces) if reviewed_traces else None

# Overall macro kappa
all_kappas = [v["macro_kappa"] for v in pairwise.values() if v["macro_kappa"] is not None]
macro_k = sum(all_kappas) / len(all_kappas) if all_kappas else None


def kappa_label(k):
    if k is None:
        return "—", "off"
    if k >= 0.8:
        return f"{k:.2f}  ✅ Excellent", "normal"
    if k >= 0.7:
        return f"{k:.2f}  🟡 Good", "normal"
    if k >= 0.6:
        return f"{k:.2f}  🟠 Fair", "off"
    return f"{k:.2f}  🔴 Poor", "off"


m1, m2, m3, m4 = st.columns(4)
lbl, delta = kappa_label(macro_k)
m1.metric("Macro κ (all pairs)", lbl)
m2.metric("Krippendorff α", f"{alpha:.2f}" if alpha else "—")
m3.metric("Annotators",      len(annotators))
m4.metric("Jointly reviewed traces", len(reviewed_traces))

st.caption(
    "**Interpretation:** κ < 0.6 = poor · 0.6–0.7 = fair · 0.7–0.8 = good · ≥ 0.8 = excellent. "
    "Aim for κ > 0.7 before deploying an LLM judge."
)

# ── Pairwise κ table ──────────────────────────────────────────────────────────
st.divider()
st.subheader("Pairwise Agreement")

if pairwise:
    rows = []
    for pair, v in pairwise.items():
        k = v["macro_kappa"]
        rows.append({
            "Annotator pair":    pair,
            "Jointly reviewed":  v["n_traces"],
            "Codes evaluated":   v["n_codes_evaluated"],
            "Macro κ":           round(k, 3) if k is not None else None,
            "Status":            ("✅ Ready" if k and k >= 0.7 else
                                  "🟡 Review rubric" if k and k >= 0.6 else "🔴 Low agreement"),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("No pairs with sufficient jointly-reviewed traces yet.")

# ── Per-code κ ────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Per-Code Agreement")

if per_code:
    df = pd.DataFrame(per_code)
    df["kappa_display"] = df["kappa"].apply(lambda k: round(k, 3) if k is not None else None)
    st.dataframe(
        df[["code", "category", "usage", "kappa_display", "n_pairs"]].rename(columns={
            "code": "Code", "category": "Category",
            "usage": "Annotations", "kappa_display": "κ", "n_pairs": "Pairs evaluated",
        }),
        use_container_width=True, hide_index=True,
    )

    # Bar chart
    valid = df[df["kappa"].notna()].sort_values("kappa")
    if not valid.empty:
        fig = px.bar(
            valid, x="kappa", y="code", orientation="h",
            color="kappa",
            color_continuous_scale=["#ef5350", "#ffd54f", "#69f0ae"],
            range_color=[-0.2, 1.0],
            labels={"kappa": "Cohen's κ", "code": "Code"},
            title="Per-Code κ  (target ≥ 0.70)",
        )
        fig.add_vline(x=0.7, line_dash="dash", line_color="#ffd54f",
                      annotation_text="0.70 target", annotation_position="top right")
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font_color="#d0d8f0", coloraxis_showscale=False,
                          height=max(300, len(valid) * 32))
        st.plotly_chart(fig, use_container_width=True)

# ── Disagreement explorer ─────────────────────────────────────────────────────
st.divider()
with st.expander("🔍 Disagreement Explorer — find traces where annotators differ"):
    traces = db.get_traces(project_id)
    trace_map = {t["id"]: t for t in traces}
    all_ann   = annotations

    # For each trace compute annotator code sets and Jaccard distance
    trace_annotators: dict[str, dict] = {}
    for ann in all_ann:
        trace_annotators.setdefault(ann["trace_id"], {})\
                        .setdefault(ann["annotator_name"], set())\
                        .add(ann["code_label"])

    disagree_rows = []
    for tid, ann_map in trace_annotators.items():
        if len(ann_map) < 2:
            continue
        names = list(ann_map.keys())
        all_codes_here = set.union(*ann_map.values())
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                s1, s2 = ann_map[names[i]], ann_map[names[j]]
                union  = s1 | s2
                inter  = s1 & s2
                jaccard = len(inter) / len(union) if union else 1.0
                if jaccard < 1.0:
                    t = trace_map.get(tid, {})
                    disagree_rows.append({
                        "Trace": t.get("query", "")[:60] + "…",
                        "Pair": f"{names[i]} ↔ {names[j]}",
                        f"{names[i]} codes": ", ".join(sorted(s1)) or "—",
                        f"{names[j]} codes": ", ".join(sorted(s2)) or "—",
                        "Agreement": round(jaccard, 2),
                    })

    if disagree_rows:
        st.dataframe(
            pd.DataFrame(disagree_rows).sort_values("Agreement"),
            use_container_width=True, hide_index=True,
        )
    else:
        st.success("All jointly-annotated traces have full agreement!")
