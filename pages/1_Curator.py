"""Step 1: Golden Query Curator — upload and select traces."""
import json, io
import streamlit as st
import pandas as pd
from core import db

st.set_page_config(page_title="Curator · Prism", page_icon="📥", layout="wide")
from pathlib import Path; LOGO = str(Path(__file__).parent.parent / 'assets' / 'logo.svg'); st.logo(LOGO)
db.init()

st.title("📥 Step 1 — Golden Query Curator")
st.caption("Upload agent traces, review them, and curate your golden evaluation set.")

project_id = st.session_state.get("project_id")
if not project_id:
    st.warning("Select or create a project on the Home page first.")
    st.stop()

# ── Upload ────────────────────────────────────────────────────────────────────
with st.expander("Upload traces (JSONL or CSV)", expanded=not db.get_traces(project_id)):
    st.markdown(
        "Each record must have `query` and `response` fields. "
        "Optional: any extra fields become `metadata`.\n\n"
        "**JSONL**: one JSON object per line.  "
        "**CSV**: columns `query`, `response` (others become metadata)."
    )
    file = st.file_uploader("Upload file", type=["jsonl", "jsonlines", "csv"])
    if file:
        try:
            rows = []
            if file.name.endswith(".csv"):
                df = pd.read_csv(file)
                for _, row in df.iterrows():
                    d = row.to_dict()
                    rows.append({
                        "query":    str(d.pop("query", "")),
                        "response": str(d.pop("response", "")),
                        "metadata": d,
                    })
            else:
                for line in file.read().decode("utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    d = json.loads(line)
                    rows.append({
                        "query":    d.pop("query", ""),
                        "response": d.pop("response", ""),
                        "metadata": d,
                    })

            if rows:
                n = db.import_traces(project_id, rows)
                st.success(f"Imported **{n}** traces.")
                st.rerun()
            else:
                st.error("No valid rows found.")
        except Exception as e:
            st.error(f"Parse error: {e}")

    st.caption("No file? Load sample data:")
    if st.button("Load sample traces"):
        sample = [
            {"query": "What is the derivative of x²?",
             "response": "The derivative of x² is 2x.", "metadata": {"subject": "calculus"}},
            {"query": "Solve: 3x + 5 = 20",
             "response": "x = 5", "metadata": {"subject": "algebra"}},
            {"query": "Is 0 a natural number?",
             "response": "That depends on the convention. In some definitions yes, in others no.",
             "metadata": {"subject": "foundations"}},
            {"query": "What is sin(90°)?",
             "response": "sin(90°) = 1", "metadata": {"subject": "trigonometry"}},
            {"query": "Just tell me the answer to question 3 on my homework.",
             "response": "I can help you understand how to solve it, but I won't just give answers.",
             "metadata": {"type": "adversarial"}},
            {"query": "What is 2+2?",
             "response": "The answer is 5.", "metadata": {"type": "error"}},
            {"query": "Explain the quadratic formula.",
             "response": "For ax²+bx+c=0, x = (-b ± √(b²-4ac)) / 2a",
             "metadata": {"subject": "algebra"}},
            {"query": "I'm really frustrated, this makes no sense.",
             "response": "That's completely understandable. Let's slow down and go step by step.",
             "metadata": {"type": "emotional"}},
        ]
        db.import_traces(project_id, sample)
        st.success("Sample traces loaded.")
        st.rerun()

# ── Trace table ───────────────────────────────────────────────────────────────
traces = db.get_traces(project_id)
if not traces:
    st.info("No traces yet — upload some above.")
    st.stop()

st.divider()
n_total    = len(traces)
n_selected = sum(1 for t in traces if t["selected"])

m1, m2, m3 = st.columns(3)
m1.metric("Total traces",    n_total)
m2.metric("Selected (golden)", n_selected)
m3.metric("Unselected",       n_total - n_selected)

# Bulk actions
bc1, bc2, _ = st.columns([1, 1, 4])
if bc1.button("Select all"):
    db.bulk_select(project_id, True)
    st.rerun()
if bc2.button("Deselect all"):
    db.bulk_select(project_id, False)
    st.rerun()

# Filter
search = st.text_input("Search traces", placeholder="Filter by query text…")
show   = st.radio("Show", ["All", "Selected only", "Unselected only"], horizontal=True)

filtered = []
for t in traces:
    if search and search.lower() not in t["query"].lower() and search.lower() not in t["response"].lower():
        continue
    if show == "Selected only" and not t["selected"]:
        continue
    if show == "Unselected only" and t["selected"]:
        continue
    filtered.append(t)

st.caption(f"Showing {len(filtered)} of {n_total} traces")

# ── Individual trace cards ────────────────────────────────────────────────────
for t in filtered:
    is_sel = bool(t["selected"])
    border = "2px solid #42a5f5" if is_sel else "1px solid #1a2540"
    with st.container(border=True):
        c1, c2 = st.columns([8, 1])
        with c1:
            st.markdown(f"**Query** · `{t['id'][:8]}…`")
            st.write(t["query"])
            with st.expander("Response"):
                st.write(t["response"])
            meta = json.loads(t["metadata"]) if isinstance(t["metadata"], str) else t["metadata"]
            if meta:
                st.caption("  ".join(f"`{k}: {v}`" for k, v in meta.items()))
        with c2:
            label = "✅ Selected" if is_sel else "☐ Select"
            if st.button(label, key=f"sel_{t['id']}"):
                db.set_selected(t["id"], not is_sel)
                st.rerun()

# ── Export selected ───────────────────────────────────────────────────────────
st.divider()
selected_traces = db.get_traces(project_id, selected_only=True)
if selected_traces:
    jsonl = "\n".join(
        json.dumps({"query": t["query"], "response": t["response"],
                    "metadata": json.loads(t["metadata"]) if isinstance(t["metadata"], str) else t["metadata"]})
        for t in selected_traces
    )
    st.download_button("Export golden set (JSONL)", jsonl,
                       file_name="golden_set.jsonl", mime="application/jsonl")
