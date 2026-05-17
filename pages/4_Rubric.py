"""Step 4: Rubric Builder — from empirical codes to evaluation criteria."""
import json
import streamlit as st
import pandas as pd
from core import db

st.set_page_config(page_title="Rubric · Prism", page_icon="📋", layout="wide")
from pathlib import Path; LOGO = str(Path(__file__).parent.parent / 'assets' / 'logo.svg'); st.logo(LOGO)
db.init()

st.title("📋 Step 4 — Rubric Builder")
st.caption("Turn your empirical failure codes into observable, scoreable evaluation criteria.")

project_id = st.session_state.get("project_id")
if not project_id:
    st.warning("Select a project on the Home page first.")
    st.stop()

codes    = db.list_codes(project_id)
criteria = db.list_criteria(project_id)

if not codes:
    st.info("No codes yet. Annotate some traces in Step 2 first.")
    st.stop()

# ── Code summary ──────────────────────────────────────────────────────────────
st.subheader("Codebook summary")
ann_all = db.get_all_annotations_for_project(project_id)
code_counts = {}
for ann in ann_all:
    code_counts[ann["code_id"]] = code_counts.get(ann["code_id"], 0) + 1

df_codes = pd.DataFrame([{
    "Label":    c["label"],
    "Category": c["category"],
    "Uses":     code_counts.get(c["id"], 0),
    "id":       c["id"],
} for c in codes]).sort_values(["Category", "Uses"], ascending=[True, False])

st.dataframe(
    df_codes[["Category", "Label", "Uses"]],
    use_container_width=True, hide_index=True,
)

# ── Create criterion from codes ───────────────────────────────────────────────
st.divider()
st.subheader("Create an evaluation criterion")
st.caption("Group one or more codes into a single scoreable criterion.")

with st.form("new_criterion"):
    name = st.text_input("Criterion name", placeholder="e.g. Grounding Quality")
    defn = st.text_area("Definition — what does this criterion measure?", height=80)
    src  = st.multiselect(
        "Source codes (the empirical basis for this criterion)",
        options=[c["label"] for c in codes],
        help="Select the open codes that this criterion captures.",
    )
    signal = st.text_input(
        "Observable signal",
        placeholder="e.g. Check whether cited facts appear verbatim in the problem statement",
    )

    st.write("**Scoring scale** (0 = worst, can add more levels):")
    c0, c1, c2 = st.columns(3)
    s0 = c0.text_input("Score 0",  value="Does not meet")
    s1 = c1.text_input("Score 1", value="Partially meets")
    s2 = c2.text_input("Score 2",  value="Fully meets")

    if st.form_submit_button("Create criterion", type="primary"):
        if not name.strip():
            st.error("Criterion name is required.")
        else:
            src_ids = [c["id"] for c in codes if c["label"] in src]
            db.create_criterion(
                project_id, name.strip(), defn.strip(), src_ids,
                {"0": s0, "1": s1, "2": s2}, signal.strip()
            )
            st.success(f"Created criterion **{name}**.")
            st.rerun()

# ── Existing criteria ─────────────────────────────────────────────────────────
st.divider()
st.subheader(f"Criteria ({len(criteria)})")

code_map = {c["id"]: c["label"] for c in codes}

if not criteria:
    st.info("No criteria yet — create one above.")
else:
    for cr in criteria:
        with st.expander(f"**{cr['name']}**"):
            col_l, col_r = st.columns([3, 2])

            with col_l:
                new_name = st.text_input("Name",  value=cr["name"],       key=f"n_{cr['id']}")
                new_defn = st.text_area("Definition", value=cr["definition"], key=f"d_{cr['id']}", height=80)
                new_sig  = st.text_input("Observable signal", value=cr["signal"] or "", key=f"s_{cr['id']}")

                src_labels = [code_map.get(cid, cid) for cid in cr["src_codes"]]
                new_src = st.multiselect(
                    "Source codes", options=[c["label"] for c in codes],
                    default=src_labels, key=f"sc_{cr['id']}"
                )

            with col_r:
                st.write("**Scale**")
                new_scale = {}
                for k, v in sorted(cr["scale"].items(), key=lambda x: int(x[0])):
                    new_scale[k] = st.text_input(f"Score {k}", value=v, key=f"sc_{cr['id']}_{k}")

            bc1, bc2 = st.columns([1, 1])
            if bc1.button("Save changes", key=f"save_{cr['id']}"):
                new_src_ids = [c["id"] for c in codes if c["label"] in new_src]
                db.update_criterion(cr["id"],
                    name=new_name, definition=new_defn, signal=new_sig,
                    src_codes=new_src_ids, scale=new_scale)
                st.success("Saved.")
                st.rerun()

            if bc2.button("Delete", key=f"del_{cr['id']}", type="secondary"):
                db.delete_criterion(cr["id"])
                st.rerun()

# ── Export rubric ─────────────────────────────────────────────────────────────
st.divider()
criteria = db.list_criteria(project_id)
if criteria:
    rubric = []
    for cr in criteria:
        rubric.append({
            "criterion":        cr["name"],
            "definition":       cr["definition"],
            "source_codes":     [code_map.get(cid, cid) for cid in cr["src_codes"]],
            "scale":            cr["scale"],
            "observable_signal": cr["signal"],
        })
    rubric_json = json.dumps(rubric, indent=2)
    st.download_button(
        "Export rubric (JSON)", rubric_json,
        file_name="rubric.json", mime="application/json",
    )
    with st.expander("Preview rubric JSON"):
        st.code(rubric_json, language="json")
