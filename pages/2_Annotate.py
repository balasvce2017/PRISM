"""Step 2: Open Coding Annotation UI."""
import streamlit as st
from core import db

st.set_page_config(page_title="Annotate · Prism", page_icon="✏️", layout="wide")
from pathlib import Path; LOGO = str(Path(__file__).parent.parent / 'assets' / 'logo.svg'); st.logo(LOGO)
db.init()

st.title("✏️ Step 2 — Open Coding")
st.caption("Assign failure codes to agent traces. Create new codes on the fly.")

project_id = st.session_state.get("project_id")
if not project_id:
    st.warning("Select a project on the Home page first.")
    st.stop()

traces = db.get_traces(project_id, selected_only=True)
if not traces:
    traces = db.get_traces(project_id)
if not traces:
    st.info("No traces found. Upload traces in the Curator first.")
    st.stop()

# ── Sidebar: annotator + navigation ──────────────────────────────────────────
with st.sidebar:
    st.header("Annotator")
    annotator_name = st.text_input("Your name", value=st.session_state.get("annotator_name", ""))
    if annotator_name:
        st.session_state["annotator_name"] = annotator_name
        annotator_id = db.get_or_create_annotator(annotator_name)
        st.session_state["annotator_id"] = annotator_id

    st.divider()
    st.header("Navigation")

    review_status = db.get_review_status(project_id)
    idx = st.session_state.get("trace_idx", 0)
    idx = max(0, min(idx, len(traces) - 1))

    if st.button("⬅ Prev", disabled=idx == 0):
        st.session_state["trace_idx"] = idx - 1
        st.rerun()
    st.write(f"Trace **{idx + 1}** / {len(traces)}")
    if st.button("Next ➡", disabled=idx == len(traces) - 1):
        st.session_state["trace_idx"] = idx + 1
        st.rerun()

    st.divider()

    # Progress bar
    annotator_id_sidebar = st.session_state.get("annotator_id")
    if annotator_id_sidebar:
        reviewed = sum(1 for t in traces if annotator_name in review_status.get(t["id"], []))
        st.progress(reviewed / len(traces), text=f"{reviewed}/{len(traces)} reviewed")

    st.divider()
    st.header("Jump to trace")
    jump = st.number_input("Trace #", min_value=1, max_value=len(traces), value=idx + 1, step=1)
    if st.button("Go"):
        st.session_state["trace_idx"] = jump - 1
        st.rerun()

if not st.session_state.get("annotator_name"):
    st.info("Enter your name in the sidebar to start annotating.")
    st.stop()

annotator_id   = st.session_state["annotator_id"]
annotator_name = st.session_state["annotator_name"]
trace          = traces[idx]
trace_id       = trace["id"]

# ── Main: trace display + coding ─────────────────────────────────────────────
left, right = st.columns([3, 2], gap="large")

with left:
    reviewed_by = review_status.get(trace_id, [])
    badge = "✅ Reviewed by you" if annotator_name in reviewed_by else "⬜ Not yet reviewed"
    st.caption(badge + f"  ·  Trace `{trace_id[:8]}…`")

    st.subheader("Query")
    st.info(trace["query"])

    st.subheader("Agent Response")
    st.warning(trace["response"])

with right:
    st.subheader("Codes assigned")
    existing = db.get_annotations(trace_id, annotator_id)
    existing_code_ids = {a["code_id"] for a in existing}

    if existing:
        for ann in existing:
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"🏷 **{ann['label']}** · _{ann['category']}_")
            if ann.get("note"):
                c1.caption(ann["note"])
            if c2.button("✕", key=f"rm_{ann['code_id']}"):
                db.remove_annotation(trace_id, annotator_id, ann["code_id"])
                st.rerun()
    else:
        st.caption("No codes assigned yet.")

    st.divider()

    # Assign existing codes
    all_codes = db.list_codes(project_id)
    if all_codes:
        st.subheader("Assign a code")
        by_cat: dict[str, list] = {}
        for c in all_codes:
            by_cat.setdefault(c["category"], []).append(c)

        for cat, codes in by_cat.items():
            st.caption(f"**{cat}**")
            for code in codes:
                disabled = code["id"] in existing_code_ids
                label = f"{'✓ ' if disabled else ''}{code['label']}"
                if st.button(label, key=f"add_{code['id']}", disabled=disabled,
                             help=code["definition"] or None):
                    db.add_annotation(trace_id, annotator_id, code["id"])
                    st.rerun()

    st.divider()

    # Create new code inline
    with st.expander("➕ Create new code"):
        with st.form("new_code_form"):
            new_label = st.text_input("Code label", placeholder="e.g. scope-creep")
            new_def   = st.text_area("Definition", height=60,
                                     placeholder="When does this failure occur?")
            new_cat   = st.text_input("Category", value="General")
            add_and_annotate = st.form_submit_button("Create & assign", type="primary")
        if add_and_annotate and new_label.strip():
            cid = db.create_code(project_id, new_label.strip(), new_def.strip(), new_cat.strip())
            db.add_annotation(trace_id, annotator_id, cid)
            st.rerun()

    st.divider()
    # Note field
    with st.expander("📝 Add a note (optional)"):
        note_code = st.selectbox("Code to annotate", options=[a["label"] for a in existing],
                                 key="note_code_sel") if existing else None
        note_text = st.text_area("Note", height=60)
        if st.button("Save note") and note_code and note_text:
            cid = next(a["code_id"] for a in existing if a["label"] == note_code)
            db.add_annotation(trace_id, annotator_id, cid, note=note_text)
            st.rerun()

# ── Mark as done ─────────────────────────────────────────────────────────────
st.divider()
col_done, col_skip = st.columns([1, 4])
if col_done.button("✅ Mark done & next", type="primary"):
    db.mark_reviewed(trace_id, annotator_id)
    st.session_state["trace_idx"] = min(idx + 1, len(traces) - 1)
    st.rerun()

# ── Codebook manager ─────────────────────────────────────────────────────────
st.divider()
with st.expander("📚 Manage Codebook"):
    codes = db.list_codes(project_id)
    if not codes:
        st.caption("No codes yet.")
    else:
        for code in codes:
            c1, c2, c3 = st.columns([3, 3, 1])
            new_lbl = c1.text_input("Label", value=code["label"], key=f"lbl_{code['id']}")
            new_cat = c2.text_input("Category", value=code["category"], key=f"cat_{code['id']}")
            if c3.button("✕", key=f"delc_{code['id']}", help="Delete code"):
                db.delete_code(code["id"])
                st.rerun()
            if new_lbl != code["label"]:
                db.update_code(code["id"], label=new_lbl)
            if new_cat != code["category"]:
                db.update_code(code["id"], category=new_cat)
