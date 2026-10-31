from __future__ import annotations

import unittest

from tests.helpers import criteria_fixture
from tools.validation import NOT_PROVIDED, parse_llm_json, validate_evaluation


def _reply(criteria=None, **overrides):
    body = {
        "supplier_name": "Apex",
        "criteria": criteria
        if criteria is not None
        else [
            {"criterion_id": c["criterion_id"], "score": 5, "max_score": 10, "justification": "ok", "evidence": "e"}
            for c in criteria_fixture()
        ],
        "risks": ["Late SAP sandbox"],
        "overall_summary": "Solid.",
    }
    body.update(overrides)
    return body


class ParseTests(unittest.TestCase):
    def test_fenced_json(self):
        raw = '```json\n{"criteria": []}\n```'
        self.assertEqual(parse_llm_json(raw), {"criteria": []})

    def test_prose_wrapped_json(self):
        raw = 'Here you go: {"criteria": [], "risks": []} Hope that helps.'
        self.assertEqual(parse_llm_json(raw), {"criteria": [], "risks": []})

    def test_empty_and_non_string(self):
        with self.assertRaisesRegex(ValueError, "empty response"):
            parse_llm_json("   ")
        with self.assertRaisesRegex(ValueError, "empty response"):
            parse_llm_json(None)

    def test_no_braces(self):
        with self.assertRaisesRegex(ValueError, "no JSON object"):
            parse_llm_json("I cannot help with that.")

    def test_invalid_json_inside_braces(self):
        with self.assertRaisesRegex(ValueError, "not valid JSON"):
            parse_llm_json("{criteria: [}")

    def test_top_level_must_be_object(self):
        with self.assertRaisesRegex(ValueError, "must be an object"):
            parse_llm_json("[1, 2]")


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.criteria = criteria_fixture()

    def test_clean_reply_passes_through(self):
        out = validate_evaluation(_reply(), self.criteria, "Apex")
        self.assertFalse(out["evaluation_failed"])
        self.assertEqual(out["warnings"], [])
        self.assertEqual(len(out["criteria"]), 5)
        self.assertEqual(out["scores"][1], 5.0)
        self.assertEqual(out["risks"], ["Late SAP sandbox"])
        self.assertTrue(all(c["is_valid"] for c in out["criteria"]))

    def test_unparseable_reply_scores_everything_zero(self):
        out = validate_evaluation("not json at all", self.criteria, "Apex")
        self.assertTrue(out["evaluation_failed"])
        self.assertTrue(all(c["score"] == 0 for c in out["criteria"]))
        self.assertTrue(all(c["justification"] == NOT_PROVIDED == c["evidence"] for c in out["criteria"]))
        self.assertFalse(any(c["is_valid"] for c in out["criteria"]))
        self.assertEqual(len(out["warnings"]), 1)
        self.assertTrue(out["warnings"][0].endswith("All criteria scored 0."))

    def test_missing_criterion_scored_zero_with_warning(self):
        criteria_reply = _reply()["criteria"][:4]  # drop criterion 5
        out = validate_evaluation(_reply(criteria=criteria_reply), self.criteria, "Apex")
        missing = next(c for c in out["criteria"] if c["criterion_id"] == 5)
        self.assertEqual(missing["score"], 0.0)
        self.assertTrue(any("no result for 'Support & Experience' (id 5); scored 0." in w for w in out["warnings"]))

    def test_duplicate_criterion_first_kept(self):
        reply = _reply()["criteria"]
        reply.append({"criterion_id": 1, "score": 9, "max_score": 10, "justification": "dup"})
        out = validate_evaluation(_reply(criteria=reply), self.criteria, "Apex")
        self.assertEqual(out["scores"][1], 5.0)
        self.assertTrue(any("duplicate result for criterion_id 1" in w for w in out["warnings"]))

    def test_unknown_criterion_ignored(self):
        reply = _reply()["criteria"]
        reply.append({"criterion_id": 99, "score": 9, "max_score": 10})
        out = validate_evaluation(_reply(criteria=reply), self.criteria, "Apex")
        self.assertNotIn(99, out["scores"])
        self.assertTrue(any("unknown or inactive criterion_id 99" in w for w in out["warnings"]))

    def test_clipping_uses_database_max(self):
        reply = _reply()["criteria"]
        reply[0] = {"criterion_id": 1, "score": 12, "max_score": 5, "justification": "j", "evidence": "e"}
        reply[1] = {"criterion_id": 2, "score": -3, "max_score": 10, "justification": "j", "evidence": "e"}
        out = validate_evaluation(_reply(criteria=reply), self.criteria, "Apex")
        by_id = {c["criterion_id"]: c for c in out["criteria"]}
        self.assertEqual(by_id[1]["score"], 10.0)  # configured max 10, not the LLM's 5
        self.assertEqual(by_id[2]["score"], 0.0)
        self.assertFalse(by_id[1]["is_valid"])
        self.assertTrue(any("differs from configured" in w for w in out["warnings"]))
        self.assertTrue(any("clipped to 10" in w for w in out["warnings"]))

    def test_nan_bool_and_string_scores_become_zero(self):
        reply = _reply()["criteria"]
        reply[0]["score"] = float("nan")
        reply[1]["score"] = True
        reply[2]["score"] = "8"
        out = validate_evaluation(_reply(criteria=reply), self.criteria, "Apex")
        by_id = {c["criterion_id"]: c for c in out["criteria"]}
        for cid in (1, 2, 3):
            self.assertEqual(by_id[cid]["score"], 0.0)
            self.assertFalse(by_id[cid]["is_valid"])
        self.assertEqual(sum("not a number" in w for w in out["warnings"]), 3)

    def test_supplier_name_mismatch_uses_entered_name(self):
        out = validate_evaluation(_reply(supplier_name="Apex Systems Ltd"), self.criteria, "Apex")
        self.assertEqual(out["supplier_name"], "Apex")
        self.assertTrue(any("entered name used" in w for w in out["warnings"]))

    def test_name_case_difference_is_not_a_warning(self):
        out = validate_evaluation(_reply(supplier_name="APEX"), self.criteria, "Apex")
        self.assertEqual(out["warnings"], [])

    def test_criteria_not_a_list(self):
        out = validate_evaluation(_reply(criteria="oops"), self.criteria, "Apex")
        self.assertTrue(any("not a list" in w for w in out["warnings"]))
        self.assertTrue(all(c["score"] == 0 for c in out["criteria"]))

    def test_risks_string_is_wrapped_and_blanks_dropped(self):
        out = validate_evaluation(_reply(risks="Single risk"), self.criteria, "Apex")
        self.assertEqual(out["risks"], ["Single risk"])
        out = validate_evaluation(_reply(risks=["  ", "Real risk", 7]), self.criteria, "Apex")
        self.assertEqual(out["risks"], ["Real risk"])

    def test_blank_text_fields_get_placeholder(self):
        reply = _reply()["criteria"]
        reply[0]["justification"] = "   "
        reply[0]["evidence"] = None
        out = validate_evaluation(_reply(criteria=reply, overall_summary=None), self.criteria, "Apex")
        first = out["criteria"][0]
        self.assertEqual(first["justification"], NOT_PROVIDED)
        self.assertEqual(first["evidence"], NOT_PROVIDED)
        self.assertEqual(out["overall_summary"], NOT_PROVIDED)


if __name__ == "__main__":
    unittest.main()
