from __future__ import annotations

import random
import unittest
from datetime import date

from tools.ranking import rank_suppliers


def _criteria(weights, max_score=10.0):
    return [
        {"criterion_id": i + 1, "name": f"C{i + 1}", "description": "", "weight": float(w), "max_score": max_score}
        for i, w in enumerate(weights)
    ]


def _supplier(name, scores, submitted="2026-03-01", rating=5.0):
    return {
        "supplier_name": name,
        "submission_date": submitted,
        "experience_rating": rating,
        "scores": {i + 1: float(s) for i, s in enumerate(scores)},
    }


class RankingFormulaTests(unittest.TestCase):
    def test_hand_worked_formula(self):
        # Weights 60/40 (total 100), max 10. A=(8,5), B=(6,10).
        # Benchmarks: C1=8, C2=10.
        # A: weighted 48 + 20 = 68; relative 100 and 50 -> PPI 100*0.6 + 50*0.4 = 80.
        # B: weighted 36 + 40 = 76; relative 75 and 100 -> PPI 75*0.6 + 100*0.4 = 85.
        out = rank_suppliers(
            _criteria([60, 40]),
            [_supplier("A", [8, 5]), _supplier("B", [6, 10])],
        )
        by_name = {r["supplier_name"]: r for r in out["results"]}
        self.assertAlmostEqual(by_name["A"]["absolute_score"], 68.0)
        self.assertAlmostEqual(by_name["B"]["absolute_score"], 76.0)
        self.assertAlmostEqual(by_name["A"]["ppi"], 80.0)
        self.assertAlmostEqual(by_name["B"]["ppi"], 85.0)
        self.assertEqual(out["benchmarks"], {1: 8.0, 2: 10.0})
        self.assertEqual([r["supplier_name"] for r in out["results"]], ["B", "A"])
        self.assertEqual([r["final_rank"] for r in out["results"]], [1, 2])
        a_c2 = by_name["A"]["criteria"][1]
        self.assertAlmostEqual(a_c2["gap"], -5.0)
        self.assertAlmostEqual(a_c2["relative_pct"], 50.0)

    def test_zero_benchmark_gives_relative_100(self):
        out = rank_suppliers(_criteria([50, 50]), [_supplier("A", [0, 0]), _supplier("B", [0, 0])])
        for row in out["results"]:
            self.assertEqual(row["ppi"], 100.0)
            self.assertEqual(row["absolute_score"], 0.0)
            for crit in row["criteria"]:
                self.assertEqual(crit["relative_pct"], 100.0)

    def test_weights_not_100_are_rescaled_with_warning(self):
        out = rank_suppliers(_criteria([30, 30]), [_supplier("A", [10, 10]), _supplier("B", [5, 5])])
        self.assertTrue(any("total 60, not 100" in w for w in out["warnings"]))
        top = out["results"][0]
        self.assertAlmostEqual(top["absolute_score"], 100.0)  # full marks on every criterion
        self.assertAlmostEqual(top["criteria"][0]["weight"], 50.0)

    def test_gap_is_zero_for_benchmark_leader(self):
        out = rank_suppliers(_criteria([50, 50]), [_supplier("A", [9, 4]), _supplier("B", [6, 4])])
        leader = next(r for r in out["results"] if r["supplier_name"] == "A")
        self.assertEqual(leader["criteria"][0]["gap"], 0.0)


class TieBreakTests(unittest.TestCase):
    def test_tie_broken_by_earlier_submission(self):
        criteria = _criteria([100])
        out = rank_suppliers(
            criteria,
            [
                _supplier("Late", [7], submitted="2026-04-01"),
                _supplier("Early", [7], submitted="2026-03-01"),
            ],
        )
        self.assertEqual([r["supplier_name"] for r in out["results"]], ["Early", "Late"])
        self.assertIn("earlier submission (2026-03-01 vs 2026-04-01)", out["tie_break_notes"][0])

    def test_tie_broken_by_higher_experience(self):
        out = rank_suppliers(
            _criteria([100]),
            [_supplier("Low", [7], rating=3), _supplier("High", [7], rating=9)],
        )
        self.assertEqual([r["supplier_name"] for r in out["results"]], ["High", "Low"])
        self.assertIn("higher experience rating (9 vs 3)", out["tie_break_notes"][0])

    def test_tie_broken_by_name_ascending(self):
        out = rank_suppliers(
            _criteria([100]),
            [_supplier("zeta", [7]), _supplier("Alpha", [7]), _supplier("beta", [7])],
        )
        self.assertEqual([r["supplier_name"] for r in out["results"]], ["Alpha", "beta", "zeta"])
        self.assertIn("supplier name ascending", out["tie_break_notes"][0])

    def test_higher_ppi_note(self):
        out = rank_suppliers(_criteria([100]), [_supplier("A", [9]), _supplier("B", [5])])
        self.assertEqual(out["tie_break_notes"], ["A ranked above B: higher PPI (100.0000 vs 55.5556)."])

    def test_output_is_deterministic_for_shuffled_input(self):
        base = [
            _supplier("Apex", [8, 7], submitted="2026-03-02", rating=8),
            _supplier("Nexa", [8, 7], submitted="2026-03-03", rating=7),
            _supplier("Orbit", [9, 3], submitted="2026-03-01", rating=9),
            _supplier("Brite", [4, 4], submitted="2026-03-04", rating=3),
        ]
        criteria = _criteria([60, 40])
        expected = rank_suppliers(criteria, base)
        rng = random.Random(7)
        for _ in range(10):
            shuffled = base[:]
            rng.shuffle(shuffled)
            self.assertEqual(rank_suppliers(criteria, shuffled), expected)


class RankingErrorTests(unittest.TestCase):
    def test_no_criteria(self):
        with self.assertRaises(ValueError):
            rank_suppliers([], [_supplier("A", [1])])

    def test_no_suppliers(self):
        with self.assertRaises(ValueError):
            rank_suppliers(_criteria([100]), [])

    def test_duplicate_names_case_insensitive(self):
        with self.assertRaises(ValueError):
            rank_suppliers(_criteria([100]), [_supplier("Apex", [1]), _supplier("apex", [2])])

    def test_missing_score(self):
        bad = {"supplier_name": "A", "submission_date": date(2026, 3, 1), "experience_rating": 1, "scores": {}}
        with self.assertRaises(ValueError):
            rank_suppliers(_criteria([100]), [bad, _supplier("B", [1])])

    def test_zero_total_weight(self):
        with self.assertRaises(ValueError):
            rank_suppliers(_criteria([0, 0]), [_supplier("A", [1, 1]), _supplier("B", [2, 2])])


if __name__ == "__main__":
    unittest.main()
