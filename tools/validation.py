"""Validate and normalise LLM output before anything is scored. Never raises from validate_evaluation."""
from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, List

NOT_PROVIDED = "Not provided by evaluator."


def parse_llm_json(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("LLM returned an empty response.")

    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("LLM response contains no JSON object.")
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM response is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("LLM JSON must be an object at the top level.")
    return data


def _text(value: Any) -> str:
    if value is None:
        return NOT_PROVIDED
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    stripped = str(value).strip()
    return stripped or NOT_PROVIDED


def _as_int(value: Any):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _as_score(value: Any):
    """Return a finite float for real numbers (not bool/str), else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _failed_result(raw_error: str, supplier_name: str, criteria: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = [
        {
            "criterion_id": int(c["criterion_id"]),
            "score": 0.0,
            "max_score": float(c["max_score"]),
            "justification": NOT_PROVIDED,
            "evidence": NOT_PROVIDED,
            "is_valid": False,
        }
        for c in criteria
    ]
    return {
        "supplier_name": supplier_name,
        "criteria": rows,
        "scores": {r["criterion_id"]: 0.0 for r in rows},
        "risks": [],
        "overall_summary": NOT_PROVIDED,
        "warnings": [f"{supplier_name}: {raw_error} All criteria scored 0."],
        "evaluation_failed": True,
    }


def validate_evaluation(raw: Any, criteria: List[Dict[str, Any]], supplier_name: str) -> Dict[str, Any]:
    by_id = {int(c["criterion_id"]): c for c in criteria}
    try:
        data = parse_llm_json(raw)
    except ValueError as exc:
        return _failed_result(str(exc), supplier_name, criteria)

    warnings: List[str] = []

    reported = data.get("supplier_name")
    if isinstance(reported, str) and reported.strip() and reported.strip().casefold() != supplier_name.strip().casefold():
        warnings.append(f"{supplier_name}: LLM reported supplier '{reported.strip()}'; entered name used.")

    entries = data.get("criteria")
    if not isinstance(entries, list):
        warnings.append(f"{supplier_name}: 'criteria' is missing or not a list; no criterion results used.")
        entries = []

    parsed: Dict[int, Dict[str, Any]] = {}
    for entry in entries:
        cid = _as_int(entry.get("criterion_id")) if isinstance(entry, dict) else None
        if cid is None:
            warnings.append(f"{supplier_name}: a criterion entry has no integer criterion_id; ignored.")
            continue
        if cid not in by_id:
            warnings.append(f"{supplier_name}: unknown or inactive criterion_id {cid}; ignored.")
            continue
        if cid in parsed:
            warnings.append(f"{supplier_name}: duplicate result for criterion_id {cid}; first kept.")
            continue
        parsed[cid] = entry

    rows: List[Dict[str, Any]] = []
    for cid, crit in by_id.items():
        name = crit["name"]
        max_score = float(crit["max_score"])
        entry = parsed.get(cid)
        if entry is None:
            warnings.append(f"{supplier_name}: no result for '{name}' (id {cid}); scored 0.")
            rows.append(
                {
                    "criterion_id": cid,
                    "score": 0.0,
                    "max_score": max_score,
                    "justification": NOT_PROVIDED,
                    "evidence": NOT_PROVIDED,
                    "is_valid": False,
                }
            )
            continue

        is_valid = True
        score = _as_score(entry.get("score"))
        if score is None:
            warnings.append(f"{supplier_name}: score for '{name}' is missing or not a number; scored 0.")
            score, is_valid = 0.0, False
        elif score < 0 or score > max_score:
            clipped = min(max(score, 0.0), max_score)
            warnings.append(
                f"{supplier_name}: score {score:g} for '{name}' is outside 0-{max_score:g}; clipped to {clipped:g}."
            )
            score, is_valid = clipped, False

        reported_max = _as_score(entry.get("max_score"))
        if reported_max is not None and reported_max != max_score:
            warnings.append(
                f"{supplier_name}: max_score {reported_max:g} for '{name}' differs from configured "
                f"{max_score:g}; configured value used."
            )

        rows.append(
            {
                "criterion_id": cid,
                "score": score,
                "max_score": max_score,
                "justification": _text(entry.get("justification")),
                "evidence": _text(entry.get("evidence")),
                "is_valid": is_valid,
            }
        )

    risks_raw = data.get("risks")
    if isinstance(risks_raw, str):
        risks_raw = [risks_raw]
    risks = [r.strip() for r in risks_raw if isinstance(r, str) and r.strip()] if isinstance(risks_raw, list) else []

    return {
        "supplier_name": supplier_name,
        "criteria": rows,
        "scores": {r["criterion_id"]: r["score"] for r in rows},
        "risks": risks,
        "overall_summary": _text(data.get("overall_summary")),
        "warnings": warnings,
        "evaluation_failed": False,
    }
