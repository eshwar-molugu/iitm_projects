from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest import mock

import fitz

from agents import evaluation_agent as ea
from tests.helpers import LONG_TEXT, criteria_fixture, make_pdf_bytes
from tools.document import MIN_TEXT_CHARS, DocumentError, _clean, extract_pdf_text


class DocumentToolTests(unittest.TestCase):
    def test_good_pdf_extracts_pages_with_markers(self):
        data = make_pdf_bytes([LONG_TEXT, LONG_TEXT])
        out = extract_pdf_text(data, filename="good.pdf")
        self.assertEqual(out["page_count"], 2)
        self.assertIn("[Page 1]", out["text"])
        self.assertIn("[Page 2]", out["text"])
        self.assertEqual(out["char_count"], len(out["text"]))
        self.assertGreaterEqual(out["char_count"], MIN_TEXT_CHARS)

    def test_clean_normalises_ligatures_nbsp_and_whitespace(self):
        self.assertEqual(_clean("ﬁnance team"), "finance team")
        self.assertEqual(_clean("a \t  b\x00c\n\n\n\nd   "), "a bc\n\nd")

    def test_corrupt_bytes_rejected(self):
        with self.assertRaises(DocumentError) as ctx:
            extract_pdf_text(b"this is not a pdf at all", filename="broken.pdf")
        self.assertIn("broken.pdf", str(ctx.exception))

    def test_password_protected_rejected(self):
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), LONG_TEXT[:300])
        data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
        doc.close()
        with self.assertRaisesRegex(DocumentError, "password protected"):
            extract_pdf_text(data, filename="locked.pdf")

    def test_near_empty_rejected_as_scanned_or_empty(self):
        with self.assertRaisesRegex(DocumentError, "scanned or empty"):
            extract_pdf_text(make_pdf_bytes(["Only a few words here."]), filename="thin.pdf")

    def test_reads_from_path(self):
        path = os.path.join(os.path.dirname(__file__), "..", "data", "rfps", "NexaWorks.pdf")
        if not os.path.exists(path):
            self.skipTest("sample PDFs not generated yet")
        self.assertIn("NexaFlow", extract_pdf_text(path)["text"])


class PromptTests(unittest.TestCase):
    def test_user_message_contents(self):
        messages, warnings = ea.build_messages(criteria_fixture(), "Apex", "DOCUMENT BODY MARKER")
        self.assertEqual(warnings, [])
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        user = messages[1]["content"]
        self.assertIn("criterion_id 1", user)
        self.assertIn("Commercial Value", user)
        self.assertIn("JSON only", user)
        self.assertIn("EVERY criterion", user)
        self.assertIn("DOCUMENT BODY MARKER", user)
        self.assertIn("=== SUPPLIER DOCUMENT START ===", user)
        self.assertNotIn("weight", user.lower())  # the LLM must not see weights

    def test_max_score_shown_as_range(self):
        criteria = [{"criterion_id": 1, "name": "Small", "description": "d", "weight": 100, "max_score": 5.0}]
        messages, _ = ea.build_messages(criteria, "Apex", "body")
        self.assertIn("0 to 5", messages[1]["content"])

    def test_long_document_truncated_with_warning(self):
        text = "x" * (ea.MAX_DOC_CHARS + 500)
        messages, warnings = ea.build_messages(criteria_fixture(), "Apex", text)
        self.assertEqual(warnings, ["Apex: document truncated to 60,000 characters for evaluation."])
        self.assertLess(len(messages[1]["content"]), ea.MAX_DOC_CHARS + 2000)

    def test_system_prompt_sets_untrusted_data_rule(self):
        self.assertIn("untrusted data", ea.SYSTEM_PROMPT)


class FakeCompletions:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])


def _client(replies):
    completions = FakeCompletions(replies)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


class EvaluateSupplierTests(unittest.TestCase):
    def test_json_mode_and_temperature_zero(self):
        client, completions = _client(['{"criteria": []}'])
        out = ea.evaluate_supplier(client, criteria_fixture(), "Apex", "body", model="m1")
        call = completions.calls[0]
        self.assertEqual(call["response_format"], {"type": "json_object"})
        self.assertEqual(call["temperature"], 0)
        self.assertEqual(call["model"], "m1")
        self.assertEqual(out["raw"], '{"criteria": []}')
        self.assertEqual(out["model"], "m1")
        self.assertEqual(out["warnings"], [])

    def test_retry_then_success_records_warning(self):
        client, completions = _client([RuntimeError("rate limited"), "{}"])
        out = ea.evaluate_supplier(client, criteria_fixture(), "Apex", "body")
        self.assertEqual(len(completions.calls), 2)
        self.assertEqual(
            out["warnings"], ["Apex: LLM call attempt 1 failed (rate limited); retrying."]
        )

    def test_fails_after_two_attempts(self):
        client, completions = _client([RuntimeError("boom"), RuntimeError("boom again")])
        with self.assertRaises(ea.EvaluationError) as ctx:
            ea.evaluate_supplier(client, criteria_fixture(), "Apex", "body")
        self.assertEqual(len(completions.calls), 2)
        self.assertIn("LLM call failed after 2 attempts", str(ctx.exception))

    def test_empty_content_counts_as_failure(self):
        client, completions = _client(["   ", "   "])
        with self.assertRaisesRegex(ea.EvaluationError, "after 2 attempts"):
            ea.evaluate_supplier(client, criteria_fixture(), "Apex", "body")
        self.assertEqual(len(completions.calls), 2)


class GetClientTests(unittest.TestCase):
    def test_unknown_provider(self):
        with self.assertRaisesRegex(ea.EvaluationError, "Unknown provider"):
            ea.get_client("key", provider="mistral")

    def test_missing_key_names_provider_and_env_var(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ea.EvaluationError, r"OpenAI API key not provided \(set OPENAI_API_KEY"):
                ea.get_client(None, provider="openai")

    def test_env_var_used_when_no_argument(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "g-key"}, clear=True):
            with mock.patch("openai.OpenAI") as openai_cls:
                ea.get_client(None, provider="gemini")
        openai_cls.assert_called_once_with(api_key="g-key", base_url=ea.GEMINI_BASE_URL)

    def test_gemini_uses_openai_compatible_base_url(self):
        with mock.patch("openai.OpenAI") as openai_cls:
            ea.get_client("g-key", provider="gemini")
        openai_cls.assert_called_once_with(api_key="g-key", base_url=ea.GEMINI_BASE_URL)

    def test_openai_plain_client(self):
        with mock.patch("openai.OpenAI") as openai_cls:
            ea.get_client("sk-x", provider="openai")
        openai_cls.assert_called_once_with(api_key="sk-x")

    def test_anthropic_adapter_maps_system_and_drops_response_format(self):
        block = SimpleNamespace(type="text", text='{"criteria": []}')
        response = SimpleNamespace(content=[block])
        with mock.patch("anthropic.Anthropic") as anth_cls:
            anth_cls.return_value.messages.create.return_value = response
            adapter = ea.get_client("ant-key", provider="anthropic")
            out = adapter.chat.completions.create(
                model="claude-haiku-4-5",
                messages=[
                    {"role": "system", "content": "SYS"},
                    {"role": "user", "content": "USER"},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
        anth_cls.assert_called_once_with(api_key="ant-key")
        kwargs = anth_cls.return_value.messages.create.call_args.kwargs
        self.assertEqual(kwargs["system"], "SYS")
        self.assertEqual(kwargs["messages"], [{"role": "user", "content": "USER"}])
        self.assertEqual(kwargs["max_tokens"], ea.ANTHROPIC_MAX_TOKENS)
        self.assertEqual(kwargs["temperature"], 0)
        self.assertNotIn("response_format", kwargs)
        self.assertEqual(out.choices[0].message.content, '{"criteria": []}')

    def test_anthropic_adapter_joins_text_blocks_only(self):
        blocks = [
            SimpleNamespace(type="text", text='{"a":'),
            SimpleNamespace(type="tool_use", text="ignored"),
            SimpleNamespace(type="text", text=" 1}"),
        ]
        with mock.patch("anthropic.Anthropic") as anth_cls:
            anth_cls.return_value.messages.create.return_value = SimpleNamespace(content=blocks)
            adapter = ea.get_client("k", provider="anthropic")
            out = adapter.chat.completions.create(model="m", messages=[{"role": "user", "content": "u"}])
        self.assertEqual(out.choices[0].message.content, '{"a": 1}')


class RetryAndAdapterIntegrationTests(unittest.TestCase):
    def test_adapter_is_accepted_by_evaluate_supplier(self):
        block = SimpleNamespace(type="text", text='{"criteria": []}')
        with mock.patch("anthropic.Anthropic") as anth_cls:
            anth_cls.return_value.messages.create.return_value = SimpleNamespace(content=[block])
            adapter = ea.get_client("k", provider="anthropic")
            out = ea.evaluate_supplier(adapter, criteria_fixture(), "Apex", "body", model="claude-haiku-4-5")
        self.assertEqual(out["raw"], '{"criteria": []}')


if __name__ == "__main__":
    unittest.main()
