from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from agents.orchestrator import InputError, TIE_BREAK_ORDER, WorkflowError, run_evaluation, validate_supplier_inputs
from db import init_db as dbmod
from db import repository
from tests.helpers import LONG_TEXT, fixed_reply_client, make_fake_client, make_pdf_bytes


def _supplier(name, submitted="2026-03-01", rating=5.0, pdf=None, filename=None):
    return {
        "supplier_name": name,
        "submission_date": submitted,
        "experience_rating": rating,
        "filename": filename or f"{name.replace(' ', '_')}.pdf",
        "pdf_bytes": pdf if pdf is not None else make_pdf_bytes([LONG_TEXT, LONG_TEXT]),
    }


class OrchestratorTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "test.db"
        dbmod.init_db(self.db_path)
        self.conn = dbmod.get_connection(self.db_path)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def count(self, table):
        return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


class FullRunTests(OrchestratorTestBase):
    def test_full_run_ranks_persists_and_round_trips(self):
        client = make_fake_client({"Apex": 8, "Nexa": 7, "Orbit": 9})
        progress = []
        export = run_evaluation(
            self.conn,
            client,
            [
                _supplier("Apex", submitted="2026-03-02", rating=8),
                _supplier("Nexa", submitted="2026-03-03", rating=7),
                _supplier("Orbit", submitted="2026-03-01", rating=9),
            ],
            model="test-model",
            progress=progress.append,
        )
        self.assertEqual(export["status"], "completed")
        self.assertEqual(export["model"], "test-model")
        self.assertTrue(export["rfp_run_id"].startswith("RFP-"))
        self.assertEqual(export["tie_break_order"], TIE_BREAK_ORDER)
        self.assertEqual(len(export["tie_break_notes"]), 2)
        self.assertEqual([s["final_rank"] for s in export["suppliers"]], [1, 2, 3])
        self.assertEqual(export["suppliers"][0]["supplier_name"], "Orbit")  # highest scores
        self.assertEqual(len(export["suppliers"][0]["criteria"]), 5)
        self.assertEqual(export["suppliers"][0]["document"]["page_count"], 2)
        self.assertIn("Justification for criterion 1.", export["suppliers"][0]["criteria"][0]["justification"])
        self.assertTrue(any("extracting text" in p for p in progress))
        self.assertTrue(any("evaluating with test-model" in p for p in progress))
        self.assertTrue(any("validating" in p for p in progress))

        self.assertEqual(self.count("rfp_runs"), 1)
        self.assertEqual(self.count("supplier_results"), 3)
        loaded = repository.load_run(self.conn, export["rfp_run_id"])
        self.assertEqual(loaded, export)

    def test_supplier_results_rows_match_ranking(self):
        client = make_fake_client({"A": 9, "B": 4})
        export = run_evaluation(self.conn, client, [_supplier("A"), _supplier("B")])
        rows = self.conn.execute(
            "SELECT supplier_name, final_rank, absolute_score, ppi FROM supplier_results ORDER BY final_rank"
        ).fetchall()
        self.assertEqual([r["supplier_name"] for r in rows], ["A", "B"])
        self.assertAlmostEqual(rows[0]["absolute_score"], export["suppliers"][0]["absolute_score"])
        self.assertAlmostEqual(rows[0]["ppi"], export["suppliers"][0]["ppi"])

    def test_criteria_snapshot_and_benchmarks_stored(self):
        export = run_evaluation(self.conn, make_fake_client({"A": 9, "B": 4}), [_supplier("A"), _supplier("B")])
        self.assertEqual(len(export["criteria"]), 5)
        self.assertEqual(set(export["benchmarks"]), {"1", "2", "3", "4", "5"})
        self.assertEqual(export["benchmarks"]["1"], 9.0)


class FailureIsolationTests(OrchestratorTestBase):
    def test_bad_pdf_is_skipped_and_others_ranked(self):
        export = run_evaluation(
            self.conn,
            make_fake_client({"A": 8, "C": 6}),
            [
                _supplier("A"),
                _supplier("B", pdf=b"not a pdf", filename="B.pdf"),
                _supplier("C"),
            ],
        )
        self.assertEqual(export["status"], "completed_with_warnings")
        self.assertEqual([s["supplier_name"] for s in export["suppliers"]], ["A", "C"])
        self.assertEqual(export["skipped_suppliers"][0]["supplier_name"], "B")
        self.assertTrue(any("B excluded from ranking" in w for w in export["warnings"]))
        self.assertEqual(self.count("supplier_results"), 2)

    def test_llm_failure_excludes_only_that_supplier(self):
        base = make_fake_client({"A": 8, "C": 6})

        def create(**kwargs):
            if "Supplier: B" in kwargs["messages"][-1]["content"]:
                raise RuntimeError("network down")
            return base.chat.completions.create(**kwargs)

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        export = run_evaluation(self.conn, client, [_supplier("A"), _supplier("B"), _supplier("C")])
        self.assertEqual([s["supplier_name"] for s in export["suppliers"]], ["A", "C"])
        self.assertTrue(any("LLM call failed after 2 attempts" in w for w in export["warnings"]))

    def test_all_failing_marks_run_failed_with_no_results(self):
        with self.assertRaises(WorkflowError):
            run_evaluation(
                self.conn,
                make_fake_client(),
                [
                    _supplier("A", pdf=b"junk-a", filename="A.pdf"),
                    _supplier("B", pdf=b"junk-b", filename="B.pdf"),
                ],
            )
        self.assertEqual(self.count("supplier_results"), 0)
        status = self.conn.execute("SELECT status FROM rfp_runs").fetchone()["status"]
        self.assertEqual(status, "failed")

    def test_malformed_json_keeps_supplier_with_zeros(self):
        client = fixed_reply_client(lambda name: "I am sorry, I cannot do that." if name == "B" else '{"criteria": []}')
        export = run_evaluation(self.conn, client, [_supplier("A"), _supplier("B")])
        b = next(s for s in export["suppliers"] if s["supplier_name"] == "B")
        self.assertTrue(b["evaluation_failed"])
        self.assertEqual(b["absolute_score"], 0.0)
        self.assertTrue(any("All criteria scored 0." in w for w in b["warnings"]))
        self.assertEqual(export["status"], "completed_with_warnings")

    def test_single_supplier_warns_about_trivial_peers(self):
        export = run_evaluation(self.conn, make_fake_client({"A": 7}), [_supplier("A"), _supplier("B", pdf=b"bad", filename="B.pdf")])
        self.assertIn("Only one supplier was evaluated; peer benchmarks and PPI are trivial.", export["warnings"])
        self.assertEqual(export["tie_break_notes"], [])


class InputValidationTests(OrchestratorTestBase):
    def test_blank_name_rejected_before_any_db_write(self):
        with self.assertRaises(InputError) as ctx:
            run_evaluation(self.conn, make_fake_client(), [_supplier(""), _supplier("B")])
        self.assertIn("Supplier 1: supplier name is required.", ctx.exception.errors)
        self.assertEqual(self.count("rfp_runs"), 0)

    def test_bad_date_rating_and_missing_pdf(self):
        clean, errors = validate_supplier_inputs(
            [
                _supplier("A", submitted="31/03/2026"),
                _supplier("B", rating=11),
                _supplier("C", pdf=b""),
            ]
        )
        self.assertTrue(any("A: submission date is missing or invalid; use YYYY-MM-DD." in e for e in errors))
        self.assertTrue(any("B: experience rating must be a number from 0 to 10." in e for e in errors))
        self.assertTrue(any("C: a PDF file is required." in e for e in errors))
        self.assertEqual(clean, [])

    def test_fewer_than_two_suppliers(self):
        _, errors = validate_supplier_inputs([_supplier("A")])
        self.assertIn("Upload at least two supplier proposals so they can be compared with peers.", errors)

    def test_duplicate_names_case_insensitive(self):
        _, errors = validate_supplier_inputs([_supplier("Apex"), _supplier("APEX")])
        self.assertTrue(any("duplicate supplier name" in e for e in errors))

    def test_boolean_rating_rejected(self):
        _, errors = validate_supplier_inputs([_supplier("A", rating=True), _supplier("B")])
        self.assertTrue(any("experience rating" in e for e in errors))

    def test_date_objects_accepted_and_normalised(self):
        clean, errors = validate_supplier_inputs([_supplier("A", submitted=date(2026, 3, 1)), _supplier("B")])
        self.assertEqual(errors, [])
        self.assertEqual(clean[0]["submission_date"], "2026-03-01")
        self.assertEqual(clean[0]["experience_rating"], 5.0)

    def test_run_id_format(self):
        export = run_evaluation(self.conn, make_fake_client(), [_supplier("A"), _supplier("B")])
        self.assertRegex(export["rfp_run_id"], r"^RFP-\d{8}-\d{6}-[0-9A-F]{6}$")


if __name__ == "__main__":
    unittest.main()
