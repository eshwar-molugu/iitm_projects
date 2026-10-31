"""Headless Streamlit tests (streamlit.testing.v1.AppTest) using a temp DB and a fake LLM."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from streamlit.testing.v1 import AppTest

from agents import evaluation_agent
from db import init_db as dbmod
from tests.helpers import make_fake_client

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def _button(at, label):
    return next(b for b in at.button if b.label == label)


def _texts(elements):
    return [e.value for e in elements]


class AppTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._db = mock.patch.object(dbmod, "DB_PATH", Path(self._tmp.name) / "app.db")
        self._db.start()
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("OPENAI_API_KEY", None)

    def tearDown(self):
        self._env.stop()
        self._db.stop()
        self._tmp.cleanup()

    def new_app(self):
        return AppTest.from_file(APP, default_timeout=60).run()


class CriteriaScreenTests(AppTestBase):
    def test_criteria_screen_shows_five_rows_and_total(self):
        at = self.new_app()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.dataframe[0].value), 5)
        self.assertIn("Active weights total 100%.", _texts(at.success))


class SampleRunTests(AppTestBase):
    def _run_samples(self, client=None, key="sk-test", provider_value=None):
        client = client or make_fake_client({"Apex Systems": 8, "BrightPath Tech": 3, "NexaWorks": 7, "Orbit Digital": 9})
        at = self.new_app()
        if provider_value:
            at.selectbox(key="provider").select(provider_value).run()
        at.text_input(key=f"key_{provider_value or 'openai'}").input(key).run()
        _button(at, "Load sample RFPs").click().run()
        with mock.patch.object(evaluation_agent, "get_client", return_value=client) as get_client:
            _button(at, "Evaluate suppliers").click().run()
        return at, get_client

    def test_sample_run_populates_all_tabs(self):
        at, _ = self._run_samples()
        self.assertEqual(len(at.exception), 0)
        self.assertIn("Done. Open the **Leaderboard**, **Detailed scorecard** and **Run details** tabs.",
                      _texts(at.success))
        leaderboard = at.dataframe[1].value if len(at.dataframe) > 1 else None
        self.assertIsNotNone(leaderboard)
        self.assertEqual(len(leaderboard), 4)
        self.assertEqual(leaderboard.iloc[0]["Supplier"], "Orbit Digital")  # highest scores in the fake
        subheaders = _texts(at.subheader)
        self.assertTrue(any(s.startswith("Leaderboard - RFP-") for s in subheaders))
        self.assertIn("Justification and evidence", subheaders)
        self.assertIn("Tie-break order", subheaders)
        self.assertIn("How adjacent ranks were decided", subheaders)
        self.assertEqual(len(at.session_state["result"]["suppliers"]), 4)

    def test_run_is_saved_to_database(self):
        self._run_samples()
        conn = dbmod.get_connection(dbmod.DB_PATH)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM supplier_results").fetchone()[0], 4)
            self.assertEqual(conn.execute("SELECT status FROM rfp_runs").fetchone()[0], "completed")
        finally:
            conn.close()

    def test_blank_name_shows_validation_error_and_no_llm_call(self):
        client = make_fake_client()
        at = self.new_app()
        at.text_input(key="key_openai").input("sk-test").run()
        _button(at, "Load sample RFPs").click().run()
        at.text_input(key="name_sample-Apex_Systems.pdf").input("   ").run()
        with mock.patch.object(evaluation_agent, "get_client", return_value=client):
            _button(at, "Evaluate suppliers").click().run()
        self.assertTrue(any("supplier name is required" in e.value for e in at.error))
        self.assertEqual(client.calls, [])

    def test_missing_key_names_the_provider(self):
        client = make_fake_client()
        at = self.new_app()
        _button(at, "Load sample RFPs").click().run()
        with mock.patch.object(evaluation_agent, "get_client", return_value=client):
            _button(at, "Evaluate suppliers").click().run()
        self.assertIn(
            "Enter your OpenAI API key in the sidebar (or configure OPENAI_API_KEY).",
            _texts(at.error),
        )

    def test_input_errors_shown_before_key_check(self):
        at = self.new_app()
        _button(at, "Load sample RFPs").click().run()
        at.text_input(key="name_sample-Orbit_Digital.pdf").input("").run()
        _button(at, "Evaluate suppliers").click().run()
        errors = _texts(at.error)
        self.assertTrue(any("supplier name is required" in e for e in errors))
        self.assertFalse(any("API key" in e for e in errors))

    def test_malformed_llm_reply_shows_warning_in_run_details(self):
        def broken(**kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="sorry, no JSON"))])

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=broken)))
        at, _ = self._run_samples(client=client)
        self.assertEqual(len(at.exception), 0)
        self.assertIn("Warnings", " ".join(_texts(at.subheader)))
        self.assertTrue(any("All criteria scored 0." in m.value for m in at.markdown))

    def test_provider_selection_passes_right_key_and_model(self):
        client = make_fake_client()
        at = self.new_app()
        at.selectbox(key="provider").select("anthropic").run()
        at.text_input(key="key_anthropic").input("ant-key").run()
        self.assertEqual(
            at.text_input(key="model_anthropic").value,
            evaluation_agent.PROVIDERS["anthropic"]["default_model"],
        )
        _button(at, "Load sample RFPs").click().run()
        with mock.patch.object(evaluation_agent, "get_client", return_value=client) as get_client:
            _button(at, "Evaluate suppliers").click().run()
        get_client.assert_called_once_with("ant-key", "anthropic")

    def test_download_button_present_after_run(self):
        at, _ = self._run_samples()
        labels = [b.proto.label for b in at.get("download_button")]
        self.assertIn("Download complete result (JSON)", labels)


if __name__ == "__main__":
    unittest.main()
