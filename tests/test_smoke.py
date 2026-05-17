"""Smoke tests — verify core modules initialise and basic DB operations work."""
import json
import os
import tempfile
import pytest
from pathlib import Path


# ── Point the DB at a temp file so tests never touch the real prism.db ────────
@pytest.fixture(autouse=True)
def tmp_db(monkeypatch, tmp_path):
    monkeypatch.setattr("core.db.DB_PATH", tmp_path / "test.db")
    from core import db
    db.init()
    yield
    # cleanup handled by tmp_path fixture


# ── Imports ───────────────────────────────────────────────────────────────────

def test_imports():
    from core import db, iaa, judge  # noqa: F401


# ── DB: projects ──────────────────────────────────────────────────────────────

def test_create_and_list_project():
    from core import db
    pid = db.create_project("Test Project", "desc")
    projects = db.list_projects()
    assert any(p["id"] == pid for p in projects)


def test_delete_project():
    from core import db
    pid = db.create_project("To Delete")
    db.delete_project(pid)
    assert not any(p["id"] == pid for p in db.list_projects())


# ── DB: traces ────────────────────────────────────────────────────────────────

def test_import_and_retrieve_traces():
    from core import db
    pid = db.create_project("Trace Test")
    rows = [
        {"query": "What is 2+2?", "response": "4"},
        {"query": "Explain gravity.", "response": "A force.", "metadata": {"subject": "physics"}},
    ]
    n = db.import_traces(pid, rows)
    assert n == 2
    traces = db.get_traces(pid)
    assert len(traces) == 2


def test_select_traces():
    from core import db
    pid = db.create_project("Select Test")
    db.import_traces(pid, [{"query": "q", "response": "r"}])
    traces = db.get_traces(pid)
    db.set_selected(traces[0]["id"], True)
    selected = db.get_traces(pid, selected_only=True)
    assert len(selected) == 1


# ── DB: codes & annotations ───────────────────────────────────────────────────

def test_create_and_list_codes():
    from core import db
    pid = db.create_project("Code Test")
    cid = db.create_code(pid, "scope-creep", "Agent edits out-of-scope files", "Grounding")
    codes = db.list_codes(pid)
    assert any(c["id"] == cid for c in codes)


def test_annotate_and_retrieve():
    from core import db
    pid = db.create_project("Annotation Test")
    db.import_traces(pid, [{"query": "q", "response": "r"}])
    trace = db.get_traces(pid)[0]
    aid = db.get_or_create_annotator("Alice")
    cid = db.create_code(pid, "error", "factual error")
    db.add_annotation(trace["id"], aid, cid, note="clear mistake")
    anns = db.get_annotations(trace["id"], aid)
    assert len(anns) == 1
    assert anns[0]["label"] == "error"


def test_remove_annotation():
    from core import db
    pid = db.create_project("Remove Ann Test")
    db.import_traces(pid, [{"query": "q", "response": "r"}])
    trace = db.get_traces(pid)[0]
    aid = db.get_or_create_annotator("Bob")
    cid = db.create_code(pid, "tone-fail", "wrong tone")
    db.add_annotation(trace["id"], aid, cid)
    db.remove_annotation(trace["id"], aid, cid)
    assert db.get_annotations(trace["id"], aid) == []


def test_mark_reviewed():
    from core import db
    pid = db.create_project("Review Test")
    db.import_traces(pid, [{"query": "q", "response": "r"}])
    trace = db.get_traces(pid)[0]
    aid = db.get_or_create_annotator("Carol")
    db.mark_reviewed(trace["id"], aid)
    status = db.get_review_status(pid)
    assert "Carol" in status.get(trace["id"], [])


# ── DB: criteria ──────────────────────────────────────────────────────────────

def test_create_and_list_criteria():
    from core import db
    pid = db.create_project("Criteria Test")
    cid = db.create_criterion(
        pid, "Factual Accuracy", "Does the agent state correct facts?",
        [], {"0": "Wrong", "1": "Partial", "2": "Correct"}, "Check facts"
    )
    criteria = db.list_criteria(pid)
    assert any(c["id"] == cid for c in criteria)


def test_update_and_delete_criterion():
    from core import db
    pid = db.create_project("Crit Update Test")
    cid = db.create_criterion(pid, "Old Name")
    db.update_criterion(cid, name="New Name")
    criteria = db.list_criteria(pid)
    assert any(c["name"] == "New Name" for c in criteria)
    db.delete_criterion(cid)
    assert not any(c["id"] == cid for c in db.list_criteria(pid))


# ── IAA ───────────────────────────────────────────────────────────────────────

def test_iaa_pairwise_kappa_two_annotators():
    from core import db, iaa

    pid = db.create_project("IAA Test")
    db.import_traces(pid, [
        {"query": f"q{i}", "response": f"r{i}"} for i in range(6)
    ])
    traces = db.get_traces(pid)
    aid1 = db.get_or_create_annotator("Ann1")
    aid2 = db.get_or_create_annotator("Ann2")
    cid  = db.create_code(pid, "error", "factual error")

    # Both annotators flag the first 3 traces with the same code
    for tr in traces[:3]:
        db.add_annotation(tr["id"], aid1, cid)
        db.add_annotation(tr["id"], aid2, cid)

    annotations = db.get_all_annotations_for_project(pid)
    codes = db.list_codes(pid)
    result = iaa.compute_pairwise_kappa(annotations, codes)
    # Should produce one pair entry
    assert len(result) == 1
    pair = list(result.values())[0]
    assert pair["n_traces"] >= 3


def test_iaa_per_code_kappa():
    from core import db, iaa
    pid = db.create_project("Per Code Kappa Test")
    db.import_traces(pid, [{"query": f"q{i}", "response": f"r{i}"} for i in range(4)])
    traces = db.get_traces(pid)
    aid1 = db.get_or_create_annotator("X1")
    aid2 = db.get_or_create_annotator("X2")
    cid  = db.create_code(pid, "scope", "scope error")
    for tr in traces:
        db.add_annotation(tr["id"], aid1, cid)
        db.add_annotation(tr["id"], aid2, cid)
    annotations = db.get_all_annotations_for_project(pid)
    codes = db.list_codes(pid)
    rows = iaa.compute_per_code_kappa(annotations, codes)
    assert len(rows) == 1
    assert rows[0]["code"] == "scope"


# ── Judge: prompt builder ─────────────────────────────────────────────────────

def test_build_prompt():
    from core.judge import build_prompt
    criterion = {
        "name": "Accuracy",
        "definition": "Is the answer correct?",
        "scale": {"0": "Wrong", "1": "Partial", "2": "Correct"},
        "signal": "Check against source",
    }
    prompt = build_prompt("What is 2+2?", "The answer is 4.", criterion)
    assert "Accuracy" in prompt
    assert "What is 2+2?" in prompt
    assert "The answer is 4." in prompt
    assert "Wrong" in prompt
    assert "Correct" in prompt


def test_parse_judge_output():
    from core.judge import _parse
    assert _parse('{"score": 2, "explanation": "fully correct"}') == {
        "score": 2, "explanation": "fully correct"
    }
    # Handles JSON wrapped in prose
    assert _parse('Here is my answer: {"score": 0, "explanation": "wrong"}')["score"] == 0


def test_provider_model_id():
    from core.judge import provider_model_id
    assert provider_model_id("Anthropic", "claude-sonnet-4-6") == "Anthropic/claude-sonnet-4-6"
    assert provider_model_id("Amazon Bedrock", "anthropic.claude-sonnet-4-5") == \
           "Amazon Bedrock/anthropic.claude-sonnet-4-5"


def test_calibration_kappa_perfect_agreement():
    from core.judge import calibration_kappa
    k = calibration_kappa([0, 1, 2, 0, 1], [0, 1, 2, 0, 1])
    assert k == pytest.approx(1.0)


def test_calibration_kappa_too_few_samples():
    from core.judge import calibration_kappa
    assert calibration_kappa([1], [1]) is None
