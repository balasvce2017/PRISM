"""Prism — Home / Project Manager"""
from pathlib import Path
import streamlit as st
from core import db

LOGO = str(Path(__file__).parent / "assets" / "logo.svg")

st.set_page_config(page_title="Prism", page_icon=LOGO, layout="wide")
st.logo(LOGO)
db.init()

# ── Hero ──────────────────────────────────────────────────────────────────────
st.image(LOGO, width=420)
st.caption("Grounded Evaluation for AI Agents — Open Coding · IAA · Rubric · LLM Judge")
st.divider()

# ── Sidebar: active project picker ───────────────────────────────────────────
with st.sidebar:
    st.header("Active Project")
    projects = db.list_projects()
    if projects:
        names = {p["name"]: p["id"] for p in projects}
        chosen = st.selectbox("Select project", list(names.keys()))
        st.session_state["project_id"]   = names[chosen]
        st.session_state["project_name"] = chosen
    else:
        st.info("No projects yet — create one below.")
        st.session_state.pop("project_id", None)

    st.divider()
    st.caption("Navigate using the pages in the left sidebar ↑")

# ── Main: create / manage projects ───────────────────────────────────────────
col1, col2 = st.columns([1, 1], gap="large")

with col1:
    st.subheader("Create a new project")
    with st.form("new_project"):
        pname = st.text_input("Project name", placeholder="e.g. SAT Math Tutor Eval")
        pdesc = st.text_area("Description (optional)", height=80)
        if st.form_submit_button("Create", type="primary"):
            if pname.strip():
                db.create_project(pname.strip(), pdesc.strip())
                st.success(f"Created project **{pname}** — select it in the sidebar.")
                st.rerun()
            else:
                st.error("Project name is required.")

with col2:
    st.subheader("Existing projects")
    projects = db.list_projects()
    if not projects:
        st.info("No projects yet.")
    else:
        for p in projects:
            with st.expander(f"**{p['name']}**  `{p['id'][:8]}…`"):
                st.write(p["desc"] or "_No description_")
                st.caption(f"Created {p['created_at'][:10]}")
                if st.button("Delete", key=f"del_{p['id']}", type="secondary"):
                    db.delete_project(p["id"])
                    st.rerun()

# ── Pipeline overview ─────────────────────────────────────────────────────────
st.divider()
st.subheader("Pipeline")
cols = st.columns(5)
steps = [
    ("1 · Curator",  "Upload agent traces and curate the golden set"),
    ("2 · Annotate", "Open coding — assign failure codes to traces"),
    ("3 · IAA",      "Inter-annotator agreement (κ, Krippendorff α)"),
    ("4 · Rubric",   "Build evaluation rubric from empirical codes"),
    ("5 · Judge",    "Calibrate an LLM judge against human annotations"),
]
for col, (title, desc) in zip(cols, steps):
    with col:
        st.markdown(f"**{title}**")
        st.caption(desc)
