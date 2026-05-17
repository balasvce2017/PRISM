"""Step 5: LLM-as-Judge calibration against human annotations."""
import os, time
import streamlit as st
import pandas as pd
import plotly.express as px
from core import db
from core.judge import (
    PROVIDERS, make_provider, provider_model_id, calibration_kappa,
    AnthropicProvider, OpenAIProvider, BedrockProvider, AzureOpenAIProvider,
)

st.set_page_config(page_title="Judge · Prism", page_icon="⚖️", layout="wide")
from pathlib import Path; LOGO = str(Path(__file__).parent.parent / 'assets' / 'logo.svg'); st.logo(LOGO)
db.init()

st.title("⚖️ Step 5 — LLM-as-Judge Calibration")
st.caption(
    "Score traces with an LLM judge and measure calibration against human annotations. "
    "Target: **κ ≥ 0.70** per criterion before deploying at scale."
)

project_id = st.session_state.get("project_id")
if not project_id:
    st.warning("Select a project on the Home page first.")
    st.stop()

criteria = db.list_criteria(project_id)
if not criteria:
    st.info("Build at least one rubric criterion in Step 4 first.")
    st.stop()

golden_traces = db.get_traces(project_id, selected_only=True) or db.get_traces(project_id)
if not golden_traces:
    st.info("No traces available.")
    st.stop()

# ── Sidebar: provider config ──────────────────────────────────────────────────
with st.sidebar:
    st.header("Model provider")

    provider_name = st.selectbox("Provider", PROVIDERS)
    cfg = {}

    # ── Anthropic ──────────────────────────────────────────────────────────────
    if provider_name == "Anthropic":
        cfg["api_key"] = st.text_input(
            "API key", type="password",
            value=os.environ.get("ANTHROPIC_API_KEY", ""),
            help="Get one at console.anthropic.com",
        )
        cfg["model"] = st.selectbox("Model", AnthropicProvider.MODELS)

    # ── OpenAI ─────────────────────────────────────────────────────────────────
    elif provider_name == "OpenAI":
        cfg["api_key"] = st.text_input(
            "API key", type="password",
            value=os.environ.get("OPENAI_API_KEY", ""),
            help="Get one at platform.openai.com",
        )
        cfg["model"] = st.selectbox("Model", OpenAIProvider.MODELS)

    # ── Amazon Bedrock ─────────────────────────────────────────────────────────
    elif provider_name == "Amazon Bedrock":
        st.caption("Uses AWS Converse API — works for all Bedrock model families.")
        cfg["aws_access_key"] = st.text_input(
            "AWS Access Key ID", type="password",
            value=os.environ.get("AWS_ACCESS_KEY_ID", ""),
        )
        cfg["aws_secret_key"] = st.text_input(
            "AWS Secret Access Key", type="password",
            value=os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
        )
        cfg["aws_session_token"] = st.text_input(
            "Session token (optional)", type="password",
            value=os.environ.get("AWS_SESSION_TOKEN", ""),
            help="Required when using temporary credentials (STS, SSO, assumed roles).",
        )
        cfg["aws_region"] = st.selectbox("Region", [
            "us-east-1", "us-west-2", "eu-west-1",
            "eu-central-1", "ap-northeast-1", "ap-southeast-1",
        ], index=0)
        cfg["model"] = st.selectbox("Model", BedrockProvider.MODELS)
        st.caption("Make sure the model is enabled in your Bedrock console.")

    # ── Azure OpenAI ───────────────────────────────────────────────────────────
    elif provider_name == "Azure OpenAI":
        cfg["api_key"] = st.text_input(
            "Azure API key", type="password",
            value=os.environ.get("AZURE_OPENAI_API_KEY", ""),
        )
        cfg["endpoint"] = st.text_input(
            "Endpoint", placeholder="https://YOUR-RESOURCE.openai.azure.com",
            value=os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
        )
        cfg["deployment"] = st.text_input(
            "Deployment name", placeholder="gpt-4o-prod",
            help="The name of your Azure deployment, not the model family name.",
        )
        cfg["api_version"] = st.text_input("API version", value="2024-02-01")
        cfg["model"] = cfg.get("deployment", "custom-deployment")

    st.divider()

    # ── Eval scope ─────────────────────────────────────────────────────────────
    st.header("Evaluation scope")
    selected_crit_names = st.multiselect(
        "Criteria", options=[c["name"] for c in criteria],
        default=[c["name"] for c in criteria],
    )
    trace_limit = st.slider(
        "Max traces to score", 1, len(golden_traces),
        min(10, len(golden_traces)),
    )
    st.caption("Scores are persisted and reused — re-run only adds missing ones.")


# ── Credential validation helper ──────────────────────────────────────────────
def credentials_ok(name: str, cfg: dict) -> tuple[bool, str]:
    if name == "Anthropic":
        return bool(cfg.get("api_key")), "Anthropic API key required."
    if name == "OpenAI":
        return bool(cfg.get("api_key")), "OpenAI API key required."
    if name == "Amazon Bedrock":
        missing = [k for k in ("aws_access_key", "aws_secret_key", "aws_region") if not cfg.get(k)]
        return not missing, f"Missing: {', '.join(missing)}"
    if name == "Azure OpenAI":
        missing = [k for k in ("api_key", "endpoint", "deployment") if not cfg.get(k)]
        return not missing, f"Missing: {', '.join(missing)}"
    return False, "Unknown provider."


ok, err_msg = credentials_ok(provider_name, cfg)
model_id = provider_model_id(provider_name, cfg.get("model", ""))

st.info(
    f"Provider: **{provider_name}**  ·  "
    f"Model: `{cfg.get('model', '—')}`  ·  "
    f"Traces: {min(trace_limit, len(golden_traces))}  ·  "
    f"Criteria: {len(selected_crit_names)}"
)

# ── Run judge ─────────────────────────────────────────────────────────────────
selected_criteria = [c for c in criteria if c["name"] in selected_crit_names]
traces_to_score   = golden_traces[:trace_limit]

if st.button("▶ Run judge scoring", type="primary", disabled=not ok):
    try:
        provider = make_provider(provider_name, cfg)
    except Exception as e:
        st.error(f"Could not initialise provider: {e}")
        st.stop()

    total = len(traces_to_score) * len(selected_criteria)
    bar   = st.progress(0, text="Starting…")
    done  = errors = 0

    for cr in selected_criteria:
        for tr in traces_to_score:
            bar.progress(done / total, text=f"Scoring {done + 1}/{total}…")
            try:
                result = provider.score_trace(tr["query"], tr["response"], cr)
                db.save_judge_score(tr["id"], cr["id"], result["score"],
                                    result["explanation"], model_id)
            except Exception as e:
                errors += 1
                st.warning(f"Trace `{tr['id'][:8]}` — {e}")
            done += 1
            time.sleep(0.25)

    bar.progress(1.0, text="Done.")
    if errors:
        st.warning(f"Completed with {errors} errors.")
    else:
        st.success(f"Scored {done}/{total} trace-criterion pairs.")
    st.rerun()

if not ok:
    st.warning(f"Credentials incomplete: {err_msg}")

# ── Results ───────────────────────────────────────────────────────────────────
st.divider()

# Model filter: show scores for the current provider/model or let user pick
all_scores = db.get_judge_scores(project_id)
available_models = sorted({s["model"] for s in all_scores}) if all_scores else []

if not available_models:
    st.info("No judge scores yet — run scoring above.")
    st.stop()

view_model = st.selectbox("View scores from", available_models,
                          index=available_models.index(model_id) if model_id in available_models else 0)

judge_scores = db.get_judge_scores(project_id, view_model)
ann_all      = db.get_all_annotations_for_project(project_id)
annotators   = db.list_annotators()
codes        = db.list_codes(project_id)
code_map     = {c["id"]: c for c in codes}

# ── Calibration ───────────────────────────────────────────────────────────────
st.subheader("Calibration report")

trace_ann_map: dict = {}
for ann in ann_all:
    trace_ann_map.setdefault((ann["trace_id"], ann["annotator_id"]), set()).add(ann["code_id"])


def human_score_for(trace_id, criterion, annotator_id):
    src = set(criterion["src_codes"])
    if not src:
        return None
    assigned = trace_ann_map.get((trace_id, annotator_id), set())
    hits = src & assigned
    if not hits:           return 2
    if len(hits) == len(src): return 0
    return 1


calib_rows = []
for js in judge_scores:
    crit = next((c for c in criteria if c["id"] == js["criterion_id"]), None)
    if not crit:
        continue
    for ann in annotators:
        h = human_score_for(js["trace_id"], crit, ann["id"])
        if h is None:
            continue
        calib_rows.append({
            "trace_id":    js["trace_id"],
            "criterion":   crit["name"],
            "annotator":   ann["name"],
            "human_score": h,
            "judge_score": js["score"],
            "explanation": js["explanation"],
        })

if not calib_rows:
    st.info(
        "No overlap between judge-scored traces and human annotations yet. "
        "Make sure annotators have reviewed the same traces that were scored."
    )
    st.stop()

df = pd.DataFrame(calib_rows)

kappa_rows = []
for crit_name, grp in df.groupby("criterion"):
    for ann_name, sub in grp.groupby("annotator"):
        k = calibration_kappa(sub["human_score"].tolist(), sub["judge_score"].tolist())
        kappa_rows.append({
            "Criterion":      crit_name,
            "vs Annotator":   ann_name,
            "N pairs":        len(sub),
            "κ":              round(k, 3) if k is not None else None,
            "Status": ("✅ Calibrated" if k and k >= 0.7 else
                       "🟡 Acceptable" if k and k >= 0.6 else "🔴 Recalibrate"),
        })

st.dataframe(pd.DataFrame(kappa_rows), use_container_width=True, hide_index=True)

df_k = pd.DataFrame(kappa_rows).dropna(subset=["κ"])
if not df_k.empty:
    fig = px.bar(
        df_k, x="κ", y="Criterion", color="κ", orientation="h",
        color_continuous_scale=["#ef5350", "#ffd54f", "#69f0ae"],
        range_color=[-0.2, 1.0],
        title=f"Judge κ vs Human  [{view_model}]",
    )
    fig.add_vline(x=0.7, line_dash="dash", line_color="#ffd54f",
                  annotation_text="0.70 target")
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font_color="#d0d8f0", coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

with st.expander("🔍 Browse individual scores"):
    st.dataframe(
        df[["criterion", "annotator", "human_score", "judge_score", "explanation"]],
        use_container_width=True, hide_index=True,
    )

with st.expander("📈 Score distributions"):
    fig2 = px.histogram(
        df.melt(id_vars=["criterion"], value_vars=["human_score", "judge_score"],
                var_name="Source", value_name="Score"),
        x="Score", color="Source", facet_col="criterion",
        barmode="group", nbins=5,
        color_discrete_map={"human_score": "#2196f3", "judge_score": "#ffd54f"},
        title="Human vs Judge score distributions",
    )
    fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                       font_color="#d0d8f0")
    st.plotly_chart(fig2, use_container_width=True)
