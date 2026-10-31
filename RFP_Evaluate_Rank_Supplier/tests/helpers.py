"""Shared test helpers: an in-memory PDF builder and a fake LLM client (no network)."""
from __future__ import annotations

import json
import re
from types import SimpleNamespace
from typing import Callable, Dict, List, Optional, Union

import fitz

FILLER = (
    "The supplier describes its delivery approach, team roles, pricing assumptions and security controls "
    "in enough detail for a procurement reviewer to follow. "
)
LONG_TEXT = FILLER * 12


def make_pdf_bytes(pages: List[str]) -> bytes:
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(56, 56, 540, 780), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def make_fake_client(scores: Optional[Dict[str, Union[int, float, Dict[int, float]]]] = None, default: float = 6):
    """Fake OpenAI-style client. The reply is built from the criteria listed in the prompt.

    scores maps supplier name -> a single score for every criterion, or {criterion_id: score}.
    """
    scores = scores or {}
    calls: List[dict] = []

    def create(**kwargs):
        calls.append(kwargs)
        user = kwargs["messages"][-1]["content"]
        supplier = re.search(r"^Supplier: (.+)$", user, re.M).group(1).strip()
        criteria = re.findall(r"- criterion_id (\d+): (.+?) \(score 0 to ([\d.]+)\)", user)
        setting = scores.get(supplier, default)
        payload = {
            "supplier_name": supplier,
            "criteria": [],
            "risks": ["Sample risk"],
            "overall_summary": f"Summary for {supplier}.",
        }
        for cid, _name, max_score in criteria:
            value = setting[int(cid)] if isinstance(setting, dict) else setting
            payload["criteria"].append(
                {
                    "criterion_id": int(cid),
                    "score": min(float(value), float(max_score)),
                    "max_score": float(max_score),
                    "justification": f"Justification for criterion {cid}.",
                    "evidence": "Quoted text from the document.",
                }
            )
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    client.calls = calls
    return client


def fixed_reply_client(reply_for: Callable[[str], str]):
    """Fake client whose reply text is chosen by supplier name (for malformed-output tests)."""

    def create(**kwargs):
        user = kwargs["messages"][-1]["content"]
        supplier = re.search(r"^Supplier: (.+)$", user, re.M).group(1).strip()
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply_for(supplier)))])

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def criteria_fixture() -> List[dict]:
    """Five active criteria, weights 30/20/20/20/10, max 10, like the seed data."""
    rows = [
        (1, "Technical Capability", 30),
        (2, "Implementation Plan", 20),
        (3, "Commercial Value", 20),
        (4, "Security & Compliance", 20),
        (5, "Support & Experience", 10),
    ]
    return [
        {"criterion_id": cid, "name": name, "description": f"{name} description", "weight": w, "max_score": 10.0}
        for cid, name, w in rows
    ]
