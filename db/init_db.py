"""SQLite schema, seed criteria and connection helper."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

DB_PATH = Path(__file__).resolve().parent / "rfp.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS evaluation_criteria (
  criterion_id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  description TEXT NOT NULL,
  weight REAL NOT NULL CHECK (weight >= 0),
  max_score REAL NOT NULL DEFAULT 10 CHECK (max_score > 0),
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);
CREATE TABLE IF NOT EXISTS rfp_runs (
  rfp_run_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL,
  run_json TEXT
);
CREATE TABLE IF NOT EXISTS supplier_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  rfp_run_id TEXT NOT NULL REFERENCES rfp_runs(rfp_run_id),
  supplier_name TEXT NOT NULL,
  submission_date TEXT NOT NULL,
  experience_rating REAL NOT NULL,
  absolute_score REAL NOT NULL,
  ppi REAL NOT NULL,
  final_rank INTEGER NOT NULL,
  result_json TEXT NOT NULL,
  UNIQUE (rfp_run_id, supplier_name)
);
"""

# (name, description, weight, max_score)
SEED_CRITERIA = [
    ("Technical Capability", "Architecture, integrations, scalability, technical fit", 30, 10),
    ("Implementation Plan", "Timeline, milestones, staffing, risk plan", 20, 10),
    ("Commercial Value", "Pricing clarity, total cost, assumptions", 20, 10),
    ("Security & Compliance", "Controls, certifications, privacy, auditability", 20, 10),
    ("Support & Experience", "Support model, similar projects, references", 10, 10),
]


def get_connection(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path | str = DB_PATH, reset: bool = False) -> None:
    """Create tables and seed criteria when the criteria table is empty."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        with conn:
            if reset:
                conn.execute("DELETE FROM evaluation_criteria")
                conn.execute("DELETE FROM sqlite_sequence WHERE name = 'evaluation_criteria'")
            count = conn.execute("SELECT COUNT(*) FROM evaluation_criteria").fetchone()[0]
            if count == 0:
                conn.executemany(
                    "INSERT INTO evaluation_criteria (name, description, weight, max_score) VALUES (?, ?, ?, ?)",
                    SEED_CRITERIA,
                )
    finally:
        conn.close()


def load_active_criteria(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT criterion_id, name, description, weight, max_score "
        "FROM evaluation_criteria WHERE is_active = 1 ORDER BY criterion_id"
    ).fetchall()
    return [
        {
            "criterion_id": int(r["criterion_id"]),
            "name": r["name"],
            "description": r["description"],
            "weight": float(r["weight"]),
            "max_score": float(r["max_score"]),
        }
        for r in rows
    ]


def _main() -> None:
    parser = argparse.ArgumentParser(description="Create and seed the RFP database.")
    parser.add_argument("--reset", action="store_true", help="delete criteria and re-seed")
    args = parser.parse_args()
    init_db(DB_PATH, reset=args.reset)
    conn = get_connection(DB_PATH)
    try:
        print(f"Database: {DB_PATH}")
        for c in load_active_criteria(conn):
            print(f"  {c['criterion_id']}. {c['name']}: weight {c['weight']:g}, max {c['max_score']:g}")
    finally:
        conn.close()


if __name__ == "__main__":
    _main()
