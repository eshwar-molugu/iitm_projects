from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from db import init_db as dbmod
from db import repository


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "rfp.db"

    def tearDown(self):
        self._tmp.cleanup()

    def test_seed_creates_five_active_criteria_totalling_100(self):
        dbmod.init_db(self.path)
        conn = dbmod.get_connection(self.path)
        try:
            criteria = dbmod.load_active_criteria(conn)
        finally:
            conn.close()
        self.assertEqual([c["name"] for c in criteria], [
            "Technical Capability", "Implementation Plan", "Commercial Value",
            "Security & Compliance", "Support & Experience",
        ])
        self.assertEqual(sum(c["weight"] for c in criteria), 100)
        self.assertTrue(all(c["max_score"] == 10 for c in criteria))

    def test_init_is_idempotent_and_does_not_reseed(self):
        dbmod.init_db(self.path)
        dbmod.init_db(self.path)
        conn = dbmod.get_connection(self.path)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM evaluation_criteria").fetchone()[0], 5)
        finally:
            conn.close()

    def test_reset_reseeds_with_ids_restarting(self):
        dbmod.init_db(self.path)
        conn = dbmod.get_connection(self.path)
        try:
            conn.execute("UPDATE evaluation_criteria SET is_active = 0 WHERE criterion_id = 5")
            conn.commit()
        finally:
            conn.close()
        dbmod.init_db(self.path, reset=True)
        conn = dbmod.get_connection(self.path)
        try:
            ids = [c["criterion_id"] for c in dbmod.load_active_criteria(conn)]
        finally:
            conn.close()
        self.assertEqual(ids, [1, 2, 3, 4, 5])

    def test_inactive_criteria_are_excluded(self):
        dbmod.init_db(self.path)
        conn = dbmod.get_connection(self.path)
        try:
            conn.execute("UPDATE evaluation_criteria SET is_active = 0 WHERE criterion_id = 5")
            conn.commit()
            ids = [c["criterion_id"] for c in dbmod.load_active_criteria(conn)]
        finally:
            conn.close()
        self.assertNotIn(5, ids)

    def test_check_constraints_enforced(self):
        dbmod.init_db(self.path)
        conn = dbmod.get_connection(self.path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO evaluation_criteria (name, description, weight, max_score) VALUES ('X', 'd', -1, 10)"
                )
        finally:
            conn.close()

    def test_run_lifecycle_and_round_trip(self):
        dbmod.init_db(self.path)
        conn = dbmod.get_connection(self.path)
        try:
            repository.create_run(conn, "RFP-TEST-1", "2026-03-01T10:00:00+00:00")
            row = conn.execute("SELECT status, run_json FROM rfp_runs").fetchone()
            self.assertEqual(row["status"], "running")
            self.assertIsNone(repository.load_run(conn, "RFP-TEST-1"))

            supplier = {
                "supplier_name": "Apex", "submission_date": "2026-03-02", "experience_rating": 8.0,
                "absolute_score": 70.0, "ppi": 80.0, "final_rank": 1,
            }
            export = {"rfp_run_id": "RFP-TEST-1", "status": "completed", "suppliers": [supplier]}
            repository.finalize_run(conn, "RFP-TEST-1", "completed", export, [supplier])
            self.assertEqual(repository.load_run(conn, "RFP-TEST-1"), export)
            stored = conn.execute("SELECT result_json FROM supplier_results").fetchone()["result_json"]
            self.assertIn('"supplier_name": "Apex"', stored)
        finally:
            conn.close()

    def test_fail_run_marks_failed_with_error(self):
        dbmod.init_db(self.path)
        conn = dbmod.get_connection(self.path)
        try:
            repository.create_run(conn, "RFP-TEST-2", "2026-03-01T10:00:00+00:00")
            repository.fail_run(conn, "RFP-TEST-2", "boom")
            status = conn.execute("SELECT status FROM rfp_runs").fetchone()["status"]
            payload = repository.load_run(conn, "RFP-TEST-2")
        finally:
            conn.close()
        self.assertEqual(status, "failed")
        self.assertEqual(payload, {"rfp_run_id": "RFP-TEST-2", "status": "failed", "error": "boom"})

    def test_finalize_is_atomic(self):
        dbmod.init_db(self.path)
        conn = dbmod.get_connection(self.path)
        try:
            repository.create_run(conn, "RFP-TEST-3", "2026-03-01T10:00:00+00:00")
            good = {"supplier_name": "A", "submission_date": "2026-03-01", "experience_rating": 1.0,
                    "absolute_score": 1.0, "ppi": 1.0, "final_rank": 1}
            dup = dict(good)  # same name -> UNIQUE violation on the second insert
            with self.assertRaises(sqlite3.IntegrityError):
                repository.finalize_run(conn, "RFP-TEST-3", "completed", {"x": 1}, [good, dup])
            count = conn.execute("SELECT COUNT(*) FROM supplier_results").fetchone()[0]
            status = conn.execute("SELECT status FROM rfp_runs").fetchone()["status"]
        finally:
            conn.close()
        self.assertEqual(count, 0)
        self.assertEqual(status, "running")


if __name__ == "__main__":
    unittest.main()
