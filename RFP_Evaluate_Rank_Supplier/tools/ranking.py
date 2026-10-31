"""Deterministic scoring, benchmarks, PPI, tie-breaks and ranks. No LLM involved."""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Union

ROUND_DP = 6
EXPECTED_TOTAL = 100.0


def _as_date(value: Union[date, str]) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def rank_suppliers(criteria: List[Dict[str, Any]], suppliers: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not criteria:
        raise ValueError("No active criteria to rank.")
    if not suppliers:
        raise ValueError("No suppliers to rank.")

    seen = set()
    for s in suppliers:
        key = s["supplier_name"].casefold()
        if key in seen:
            raise ValueError(f"Duplicate supplier name: {s['supplier_name']}.")
        seen.add(key)

    for s in suppliers:
        for c in criteria:
            if c["criterion_id"] not in s["scores"]:
                raise ValueError(
                    f"{s['supplier_name']} has no score for criterion {c['criterion_id']} ({c['name']})."
                )

    total = sum(float(c["weight"]) for c in criteria)
    if total <= 0:
        raise ValueError("Total weight of active criteria must be greater than zero.")

    warnings: List[str] = []
    if abs(total - EXPECTED_TOTAL) > 1e-9:
        warnings.append(
            f"Active criteria weights total {total:g}, not 100. "
            "Absolute scores are rescaled to a 0-100 range."
        )

    eff_weight = {c["criterion_id"]: float(c["weight"]) * 100.0 / total for c in criteria}
    benchmarks = {
        c["criterion_id"]: max(float(s["scores"][c["criterion_id"]]) for s in suppliers) for c in criteria
    }

    results = []
    for s in suppliers:
        absolute = 0.0
        ppi_numerator = 0.0
        rows = []
        for c in criteria:
            cid = c["criterion_id"]
            score = float(s["scores"][cid])
            max_score = float(c["max_score"])
            bench = benchmarks[cid]
            weight = eff_weight[cid]
            weighted = score / max_score * weight
            gap = score - bench
            relative = 100.0 if bench == 0 else score / bench * 100.0
            absolute += weighted
            ppi_numerator += relative * weight
            rows.append(
                {
                    "criterion_id": cid,
                    "criterion_name": c["name"],
                    "score": round(score, ROUND_DP),
                    "max_score": round(max_score, ROUND_DP),
                    "weight": round(weight, ROUND_DP),
                    "weighted_score": round(weighted, ROUND_DP),
                    "benchmark": round(bench, ROUND_DP),
                    "gap": round(gap, ROUND_DP),
                    "relative_pct": round(relative, ROUND_DP),
                }
            )
        results.append(
            {
                "supplier_name": s["supplier_name"],
                "submission_date": _as_date(s["submission_date"]).isoformat(),
                "experience_rating": float(s["experience_rating"]),
                "absolute_score": round(absolute, ROUND_DP),
                "ppi": round(ppi_numerator / EXPECTED_TOTAL, ROUND_DP),
                "criteria": rows,
            }
        )

    results.sort(
        key=lambda r: (
            -r["ppi"],
            _as_date(r["submission_date"]),
            -r["experience_rating"],
            r["supplier_name"].casefold(),
            r["supplier_name"],
        )
    )
    for rank, row in enumerate(results, start=1):
        row["final_rank"] = rank

    notes = [_tie_note(results[i], results[i + 1]) for i in range(len(results) - 1)]

    return {
        "results": results,
        "benchmarks": benchmarks,
        "tie_break_notes": notes,
        "warnings": warnings,
    }


def _tie_note(a: Dict[str, Any], b: Dict[str, Any]) -> str:
    head = f"{a['supplier_name']} ranked above {b['supplier_name']}"
    if a["ppi"] != b["ppi"]:
        return f"{head}: higher PPI ({a['ppi']:.4f} vs {b['ppi']:.4f})."
    if a["submission_date"] != b["submission_date"]:
        return (
            f"{head}: PPI tied at {a['ppi']:.4f}; earlier submission "
            f"({a['submission_date']} vs {b['submission_date']})."
        )
    if a["experience_rating"] != b["experience_rating"]:
        return (
            f"{head}: PPI and submission date tied; higher experience rating "
            f"({a['experience_rating']:g} vs {b['experience_rating']:g})."
        )
    return f"{head}: PPI, submission date and experience rating all tied; supplier name ascending."
