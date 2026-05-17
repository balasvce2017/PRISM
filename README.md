# Prism — Grounded Evaluation for AI Agents

An open-source Streamlit app for domain experts to build **evidence-based evaluation systems** for AI agents — no ML expertise required.

Based on the methodology from [Why Grounded Theory for Reliable AI Agents](https://balachanderkeelapudi.substack.com/p/why-grounded-theory-for-reliable).

---

## Pipeline

```
Upload traces → Curate golden set → Open Coding → IAA → Rubric → LLM Judge calibration
     1               1                  2           3      4             5
```

| Step | What you do |
|------|-------------|
| **1 · Curator** | Upload agent I/O traces (JSONL/CSV), select your golden evaluation set |
| **2 · Annotate** | Assign failure codes to traces (open coding). Multiple annotators supported. |
| **3 · IAA** | Measure inter-annotator agreement (Cohen's κ, Krippendorff's α). Flag low-agreement codes. |
| **4 · Rubric** | Group codes into evaluation criteria with observable, scoreable scales. Export to JSON. |
| **5 · Judge** | Run an LLM-as-Judge on your golden traces and measure calibration vs human annotations. |

---

## Quick start

```bash
git clone https://github.com/YOUR_ORG/prism
cd prism
pip install -r requirements.txt
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

### Input format

**JSONL** (one object per line):
```jsonl
{"query": "What is x²?", "response": "The derivative is 2x.", "subject": "calculus"}
{"query": "Solve 3x+5=20", "response": "x = 5"}
```

**CSV**: must have `query` and `response` columns. All other columns become metadata.

---

## Calibration target

Deploy the LLM judge when **κ ≥ 0.70** per criterion against human annotators.

| κ range | Interpretation |
|---------|----------------|
| ≥ 0.80  | Excellent — ready for production |
| 0.70–0.79 | Good — acceptable for most use cases |
| 0.60–0.69 | Fair — revisit rubric definition |
| < 0.60  | Poor — return to open coding |

---

## Data

All data is stored locally in `prism.db` (SQLite). No data is sent anywhere except to the Anthropic API when you run the judge (Step 5). Your API key is never persisted.

---

## Contributing

PRs welcome. See `CONTRIBUTING.md` (coming soon).

## License

MIT
