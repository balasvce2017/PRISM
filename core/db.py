"""SQLite persistence layer for Prism."""
import sqlite3, uuid, json
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent.parent / "prism.db"


@contextmanager
def conn():
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id         TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            desc       TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS traces (
            id         TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            query      TEXT NOT NULL,
            response   TEXT NOT NULL,
            metadata   TEXT DEFAULT '{}',
            selected   INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS annotators (
            id   TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS codes (
            id         TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            label      TEXT NOT NULL,
            definition TEXT DEFAULT '',
            category   TEXT DEFAULT 'General',
            color      TEXT DEFAULT '#2196f3',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS annotations (
            id           TEXT PRIMARY KEY,
            trace_id     TEXT NOT NULL,
            annotator_id TEXT NOT NULL,
            code_id      TEXT NOT NULL,
            note         TEXT DEFAULT '',
            created_at   TEXT DEFAULT (datetime('now')),
            UNIQUE(trace_id, annotator_id, code_id)
        );
        CREATE TABLE IF NOT EXISTS reviews (
            trace_id     TEXT NOT NULL,
            annotator_id TEXT NOT NULL,
            done_at      TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (trace_id, annotator_id)
        );
        CREATE TABLE IF NOT EXISTS criteria (
            id         TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            name       TEXT NOT NULL,
            definition TEXT DEFAULT '',
            src_codes  TEXT DEFAULT '[]',
            scale      TEXT DEFAULT '{"0":"Does not meet","1":"Partially meets","2":"Fully meets"}',
            signal     TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS judge_scores (
            id           TEXT PRIMARY KEY,
            trace_id     TEXT NOT NULL,
            criterion_id TEXT NOT NULL,
            score        INTEGER,
            explanation  TEXT DEFAULT '',
            model        TEXT DEFAULT '',
            created_at   TEXT DEFAULT (datetime('now')),
            UNIQUE(trace_id, criterion_id, model)
        );
        """)


# ── Projects ─────────────────────────────────────────────────────────────────

def create_project(name: str, desc: str = "") -> str:
    pid = str(uuid.uuid4())
    with conn() as c:
        c.execute("INSERT INTO projects(id,name,desc) VALUES(?,?,?)", (pid, name, desc))
    return pid


def list_projects() -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT id,name,desc,created_at FROM projects ORDER BY created_at DESC"
        )]


def delete_project(pid: str):
    with conn() as c:
        for tbl in ("judge_scores","criteria","annotations","reviews","codes","traces"):
            c.execute(f"DELETE FROM {tbl} WHERE {'project_id' if tbl not in ('judge_scores','annotations','reviews') else 'trace_id'} IN "
                      f"(SELECT id FROM traces WHERE project_id=?)", (pid,)) if tbl in ("judge_scores","annotations","reviews") else \
            c.execute(f"DELETE FROM {tbl} WHERE project_id=?", (pid,))
        c.execute("DELETE FROM projects WHERE id=?", (pid,))


# ── Traces ────────────────────────────────────────────────────────────────────

def import_traces(project_id: str, rows: list[dict]) -> int:
    inserted = 0
    with conn() as c:
        for r in rows:
            tid = str(uuid.uuid4())
            c.execute(
                "INSERT OR IGNORE INTO traces(id,project_id,query,response,metadata) VALUES(?,?,?,?,?)",
                (tid, project_id, r.get("query",""), r.get("response",""),
                 json.dumps(r.get("metadata", {})))
            )
            inserted += 1
    return inserted


def get_traces(project_id: str, selected_only: bool = False) -> list[dict]:
    with conn() as c:
        sql = "SELECT * FROM traces WHERE project_id=?"
        params = [project_id]
        if selected_only:
            sql += " AND selected=1"
        sql += " ORDER BY created_at"
        return [dict(r) for r in c.execute(sql, params)]


def set_selected(trace_id: str, selected: bool):
    with conn() as c:
        c.execute("UPDATE traces SET selected=? WHERE id=?", (int(selected), trace_id))


def bulk_select(project_id: str, selected: bool):
    with conn() as c:
        c.execute("UPDATE traces SET selected=? WHERE project_id=?", (int(selected), project_id))


# ── Annotators ────────────────────────────────────────────────────────────────

def get_or_create_annotator(name: str) -> str:
    with conn() as c:
        row = c.execute("SELECT id FROM annotators WHERE name=?", (name,)).fetchone()
        if row:
            return row["id"]
        aid = str(uuid.uuid4())
        c.execute("INSERT INTO annotators(id,name) VALUES(?,?)", (aid, name))
        return aid


def list_annotators() -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM annotators ORDER BY name")]


# ── Codes ─────────────────────────────────────────────────────────────────────

def create_code(project_id: str, label: str, definition: str = "",
                category: str = "General", color: str = "#2196f3") -> str:
    cid = str(uuid.uuid4())
    with conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO codes(id,project_id,label,definition,category,color) VALUES(?,?,?,?,?,?)",
            (cid, project_id, label.strip(), definition, category, color)
        )
    return cid


def list_codes(project_id: str) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM codes WHERE project_id=? ORDER BY category,label", (project_id,)
        )]


def update_code(code_id: str, label: str = None, definition: str = None,
                category: str = None, color: str = None):
    with conn() as c:
        if label      is not None: c.execute("UPDATE codes SET label=? WHERE id=?", (label, code_id))
        if definition is not None: c.execute("UPDATE codes SET definition=? WHERE id=?", (definition, code_id))
        if category   is not None: c.execute("UPDATE codes SET category=? WHERE id=?", (category, code_id))
        if color      is not None: c.execute("UPDATE codes SET color=? WHERE id=?", (color, code_id))


def delete_code(code_id: str):
    with conn() as c:
        c.execute("DELETE FROM annotations WHERE code_id=?", (code_id,))
        c.execute("DELETE FROM codes WHERE id=?", (code_id,))


# ── Annotations ───────────────────────────────────────────────────────────────

def add_annotation(trace_id: str, annotator_id: str, code_id: str, note: str = ""):
    with conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO annotations(id,trace_id,annotator_id,code_id,note) VALUES(?,?,?,?,?)",
            (str(uuid.uuid4()), trace_id, annotator_id, code_id, note)
        )


def remove_annotation(trace_id: str, annotator_id: str, code_id: str):
    with conn() as c:
        c.execute(
            "DELETE FROM annotations WHERE trace_id=? AND annotator_id=? AND code_id=?",
            (trace_id, annotator_id, code_id)
        )


def get_annotations(trace_id: str, annotator_id: str) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("""
            SELECT a.*, c.label, c.color, c.category
            FROM annotations a JOIN codes c ON a.code_id=c.id
            WHERE a.trace_id=? AND a.annotator_id=?
        """, (trace_id, annotator_id))]


def mark_reviewed(trace_id: str, annotator_id: str):
    with conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO reviews(trace_id,annotator_id) VALUES(?,?)",
            (trace_id, annotator_id)
        )


def get_review_status(project_id: str) -> dict:
    """Returns {trace_id: [annotator_name, ...]} for all reviewed traces."""
    with conn() as c:
        rows = c.execute("""
            SELECT r.trace_id, a.name
            FROM reviews r
            JOIN annotators a ON r.annotator_id=a.id
            JOIN traces t ON r.trace_id=t.id
            WHERE t.project_id=?
        """, (project_id,)).fetchall()
    result: dict[str, list] = {}
    for row in rows:
        result.setdefault(row["trace_id"], []).append(row["name"])
    return result


def get_all_annotations_for_project(project_id: str) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("""
            SELECT a.trace_id, a.annotator_id, an.name as annotator_name,
                   a.code_id, c.label as code_label, c.category
            FROM annotations a
            JOIN traces t ON a.trace_id=t.id
            JOIN codes c ON a.code_id=c.id
            JOIN annotators an ON a.annotator_id=an.id
            WHERE t.project_id=?
        """, (project_id,))]


# ── Criteria ──────────────────────────────────────────────────────────────────

def create_criterion(project_id: str, name: str, definition: str = "",
                     src_codes: list = None, scale: dict = None, signal: str = "") -> str:
    cid = str(uuid.uuid4())
    with conn() as c:
        c.execute(
            "INSERT INTO criteria(id,project_id,name,definition,src_codes,scale,signal) VALUES(?,?,?,?,?,?,?)",
            (cid, project_id, name, definition,
             json.dumps(src_codes or []),
             json.dumps(scale or {"0": "Does not meet", "1": "Partially meets", "2": "Fully meets"}),
             signal)
        )
    return cid


def list_criteria(project_id: str) -> list[dict]:
    with conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM criteria WHERE project_id=? ORDER BY created_at", (project_id,)
        )]
    for r in rows:
        r["src_codes"] = json.loads(r["src_codes"])
        r["scale"]     = json.loads(r["scale"])
    return rows


def update_criterion(cid: str, **kwargs):
    with conn() as c:
        for k, v in kwargs.items():
            if k in ("src_codes", "scale"):
                v = json.dumps(v)
            c.execute(f"UPDATE criteria SET {k}=? WHERE id=?", (v, cid))


def delete_criterion(cid: str):
    with conn() as c:
        c.execute("DELETE FROM judge_scores WHERE criterion_id=?", (cid,))
        c.execute("DELETE FROM criteria WHERE id=?", (cid,))


# ── Judge scores ──────────────────────────────────────────────────────────────

def save_judge_score(trace_id: str, criterion_id: str, score: int,
                     explanation: str, model: str):
    with conn() as c:
        c.execute("""
            INSERT OR REPLACE INTO judge_scores(id,trace_id,criterion_id,score,explanation,model)
            VALUES(?,?,?,?,?,?)
        """, (str(uuid.uuid4()), trace_id, criterion_id, score, explanation, model))


def get_judge_scores(project_id: str, model: str = None) -> list[dict]:
    with conn() as c:
        sql = """
            SELECT js.*, t.query, t.response, cr.name as criterion_name
            FROM judge_scores js
            JOIN traces t ON js.trace_id=t.id
            JOIN criteria cr ON js.criterion_id=cr.id
            WHERE t.project_id=?
        """
        params = [project_id]
        if model:
            sql += " AND js.model=?"
            params.append(model)
        return [dict(r) for r in c.execute(sql, params)]
