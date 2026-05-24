from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import config


def _conn() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(config.RESEARCH_DB_PATH)


def init_research_db() -> None:
    with _conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unique_key TEXT UNIQUE,
            source TEXT,
            title TEXT,
            abstract TEXT,
            url TEXT,
            published_date TEXT,
            authors TEXT,
            cited_by_count INTEGER DEFAULT 0,
            relevance REAL DEFAULT 0,
            novelty REAL DEFAULT 0,
            grant_potential REAL DEFAULT 0,
            collaboration_potential REAL DEFAULT 0,
            industry_potential REAL DEFAULT 0,
            teaching_public_value REAL DEFAULT 0,
            feasibility REAL DEFAULT 0,
            risk REAL DEFAULT 0,
            total_score REAL DEFAULT 0,
            agent_commentary TEXT,
            evidence_gaps TEXT,
            recommended_action TEXT,
            status TEXT DEFAULT 'new',
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feedback_text TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS research_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            rationale TEXT,
            agent TEXT,
            priority TEXT,
            effort TEXT,
            risk TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            completed_at TEXT
        );
        """)
        # Graceful migration: add new columns if they don't exist yet
        _add_column_if_missing(conn, "papers", "session_id", "TEXT DEFAULT ''")
        _add_column_if_missing(conn, "papers", "extended_data", "TEXT DEFAULT '{}'")


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, col_def: str) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
        except sqlite3.OperationalError:
            pass  # race or already added


def paper_exists(unique_key: str) -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT id FROM papers WHERE unique_key = ?", (unique_key,)
        ).fetchone()
    return row is not None


def save_scored_paper(paper_data: dict, session_id: str = "") -> None:
    init_research_db()
    unique_key = paper_data.get("unique_key", "")
    if not unique_key:
        import hashlib
        base = paper_data.get("url", "") or paper_data.get("title", "")
        unique_key = hashlib.sha256(base.encode()).hexdigest()[:16]
    if paper_exists(unique_key):
        return

    authors = paper_data.get("authors", [])
    if isinstance(authors, list):
        authors = json.dumps(authors)
    evidence_gaps = paper_data.get("evidence_gaps", [])
    if isinstance(evidence_gaps, list):
        evidence_gaps = json.dumps(evidence_gaps)

    # Collect any extended scoring fields (OLED-specific) into JSON blob
    extended_keys = {
        "key_metrics", "oled_device_usefulness", "tadf_mechanism_relevance",
        "red_nir_emission_relevance", "lanthanide_relevance", "experimental_feasibility",
        "recommended_use", "opportunity_type",
    }
    extended = {k: paper_data[k] for k in extended_keys if k in paper_data}
    extended_data = json.dumps(extended)

    with _conn() as conn:
        conn.execute("""
        INSERT OR IGNORE INTO papers
        (unique_key, source, title, abstract, url, published_date, authors, cited_by_count,
         relevance, novelty, grant_potential, collaboration_potential, industry_potential,
         teaching_public_value, feasibility, risk, total_score, agent_commentary,
         evidence_gaps, recommended_action, status, created_at, session_id, extended_data)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            unique_key,
            paper_data.get("source", ""),
            paper_data.get("title", ""),
            paper_data.get("abstract", "")[:2000],
            paper_data.get("url", ""),
            paper_data.get("published_date", ""),
            authors,
            int(paper_data.get("cited_by_count", 0)),
            float(paper_data.get("relevance", 0)),
            float(paper_data.get("novelty", 0)),
            float(paper_data.get("grant_potential", 0)),
            float(paper_data.get("collaboration_potential", 0)),
            float(paper_data.get("industry_potential", 0)),
            float(paper_data.get("teaching_public_value", 0)),
            float(paper_data.get("feasibility", 0)),
            float(paper_data.get("risk", 0)),
            float(paper_data.get("total_score", 0)),
            paper_data.get("agent_commentary", ""),
            evidence_gaps,
            paper_data.get("recommended_action", "save_for_later"),
            paper_data.get("status", "new"),
            datetime.now(timezone.utc).isoformat(),
            session_id,
            extended_data,
        ))


def get_top_papers(
    limit: int = 10,
    session_id: str | None = None,
    global_memory: bool = False,
) -> list[dict]:
    """
    Retrieve top-scored papers.

    Args:
        limit:         Maximum number of papers to return.
        session_id:    If provided and global_memory=False, return only papers from this session.
        global_memory: If True, ignore session_id and return globally highest-scored papers.
    """
    init_research_db()
    with _conn() as conn:
        if session_id and not global_memory:
            rows = conn.execute(
                "SELECT * FROM papers WHERE session_id = ? ORDER BY total_score DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM papers ORDER BY total_score DESC LIMIT ?", (limit,)
            ).fetchall()

        cursor = conn.execute("SELECT * FROM papers LIMIT 0")
        cols = [d[0] for d in cursor.description] if cursor.description else []

    if not cols:
        cols = [
            "id", "unique_key", "source", "title", "abstract", "url", "published_date",
            "authors", "cited_by_count", "relevance", "novelty", "grant_potential",
            "collaboration_potential", "industry_potential", "teaching_public_value",
            "feasibility", "risk", "total_score", "agent_commentary", "evidence_gaps",
            "recommended_action", "status", "created_at",
        ]

    result = []
    for row in rows:
        d = dict(zip(cols, row))
        try:
            d["authors"] = json.loads(d.get("authors") or "[]")
        except Exception:
            d["authors"] = []
        try:
            d["evidence_gaps"] = json.loads(d.get("evidence_gaps") or "[]")
        except Exception:
            d["evidence_gaps"] = []
        try:
            extended = json.loads(d.get("extended_data") or "{}")
            d.update(extended)
        except Exception:
            pass
        result.append(d)
    return result


def save_feedback(feedback_text: str) -> None:
    init_research_db()
    with _conn() as conn:
        conn.execute(
            "INSERT INTO feedback (feedback_text, created_at) VALUES (?, ?)",
            (feedback_text, datetime.now(timezone.utc).isoformat()),
        )


def get_recent_feedback(limit: int = 10) -> list[dict]:
    init_research_db()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM feedback ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [{"id": r[0], "feedback_text": r[1], "created_at": r[2]} for r in rows]


def deduplicate_papers(papers: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for p in papers:
        key = p.get("unique_key", "") or p.get("url", "") or p.get("title", "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(p)
    return unique
