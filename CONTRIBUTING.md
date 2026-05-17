# Contributing to Prism

Thanks for your interest in improving Prism. This document covers everything you need to get started.

---

## Ways to contribute

- **Bug reports** — open a GitHub issue with steps to reproduce
- **Feature requests** — open an issue describing the use case before writing code
- **Code** — pick up an open issue, comment that you're working on it, then open a PR
- **Documentation** — fix a typo, improve an explanation, add an example dataset

---

## Local development setup

```bash
git clone https://github.com/balasvce2017/PRISM.git
cd PRISM
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Before pushing, run the test suite and linter locally:

```bash
pytest tests/ -v
ruff check core/ tests/ app.py pages/
```

The app runs at http://localhost:8501. All data is stored locally in `prism.db` (SQLite) — it is git-ignored, so your test data never touches the repo.

---

## Project structure

```
prism/
├── app.py              # Home page — project manager
├── pages/
│   ├── 1_Curator.py   # Upload & curate golden traces
│   ├── 2_Annotate.py  # Open coding annotation UI
│   ├── 3_IAA.py       # Inter-annotator agreement dashboard
│   ├── 4_Rubric.py    # Rubric builder & JSON export
│   └── 5_Judge.py     # LLM-as-Judge calibration
├── core/
│   ├── db.py          # SQLite persistence (all CRUD)
│   ├── iaa.py         # Cohen's κ and Krippendorff's α
│   └── judge.py       # Multi-provider LLM judge engine
├── assets/
│   └── logo.svg       # Prism logo
└── requirements.txt
```

---

## Submitting a pull request

1. Fork the repo and create a branch: `git checkout -b your-feature`
2. Make your changes — keep each PR focused on one thing
3. Test manually by running the app and walking through the affected pipeline step
4. Open a PR against `main` with a clear description of **what** changed and **why**

### PR checklist

- [ ] No `.db` files committed
- [ ] No hardcoded API keys or credentials
- [ ] New dependencies added to `requirements.txt`
- [ ] Page titles updated if a new page was added
- [ ] `ruff check core/ tests/ app.py pages/` passes with no errors
- [ ] `pytest tests/ -v` passes with no failures

---

## Code style

- Python 3.9+ compatible (no `X | Y` union syntax — use `Optional[X]` from `typing`)
- Keep each page file self-contained; shared logic goes in `core/`
- No ORM — raw `sqlite3` only, consistent with the existing `core/db.py` pattern
- Streamlit state goes in `st.session_state`; avoid module-level mutable globals

---

## Reporting security issues

Please **do not** open a public issue for security vulnerabilities. Email the maintainer directly instead.

---

## License

By contributing you agree that your changes will be released under the [MIT License](LICENSE).
