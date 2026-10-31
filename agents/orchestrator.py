"""Workflow controller: calls the document tool, evaluation agent, validation tool, ranking tool and repository in order."""
from __future__ import annotations

import math
import secrets
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from agents.evaluation_agent import DEFAULT_MODEL, EvaluationError, evaluate_supplier
from db import repository
from db.init_db import load_active_criteria
from tools.document import DocumentError, extract_pdf_text
from tools.ranking import rank_suppliers
from tools.validation import validate_evaluation

MAX_EXPERIENCE_RATING = 10.0
TIE_BREAK_ORDER = [
    "Higher PPI",
    "Earlier submission date",
    "Higher experience rating",
    "Supplier name ascending",
]


class InputError(Exception):
    def __init__(self, errors: List[str]) -> None:
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


class WorkflowError(Exception):
    pass


def _parse_date(value: Any) -> Optional[str]:
    try:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, str):
            return date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        return None
    return None


def validate_supplier_inputs(suppliers: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    errors: List[str] = []
    clean: List[Dict[str, Any]] = []
    if len(suppliers) < 2:
        errors.append("Upload at least two supplier proposals so they can be compared with peers.")

    seen = set()
    for index, s in enumerate(suppliers, start=1):
        raw_name = str(s.get("supplier_name") or "").strip()
        label = raw_name or f"Supplier {index}"
        row_ok = True

        if not raw_name:
            errors.append(f"Supplier {index}: supplier name is required.")
            row_ok = False
        elif raw_name.casefold() in seen:
            errors.append(f"{label}: duplicate supplier name.")
            row_ok = False
        else:
            seen.add(raw_name.casefold())

        iso_date = _parse_date(s.get("submission_date"))
        if iso_date is None:
            errors.append(f"{label}: submission date is missing or invalid; use YYYY-MM-DD.")
            row_ok = False

        rating = s.get("experience_rating")
        rating_value: Optional[float] = None
        if not isinstance(rating, bool):
            try:
                rating_value = float(rating)
            except (TypeError, ValueError):
                rating_value = None
        if rating_value is None or not math.isfinite(rating_value) or not 0 <= rating_value <= MAX_EXPERIENCE_RATING:
            errors.append(f"{label}: experience rating must be a number from 0 to {MAX_EXPERIENCE_RATING:g}.")
            row_ok = False

        pdf_bytes = s.get("pdf_bytes")
        if not pdf_bytes:
            errors.append(f"{label}: a PDF file is required.")
            row_ok = False

        if row_ok:
            clean.append(
                {
                    "supplier_name": raw_name,
                    "submission_date": iso_date,
                    "experience_rating": rating_value,
                    "filename": s.get("filename") or f"{raw_name}.pdf",
                    "pdf_bytes": pdf_bytes,
                }
            )
    return clean, errors


def _new_run_id() -> str:
    return f"RFP-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{secrets.token_hex(3).upper()}"


def run_evaluation(
    conn,
    client,
    suppliers: List[Dict[str, Any]],
    model: str = DEFAULT_MODEL,
    progress: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    def say(message: str) -> None:
        if progress:
            progress(message)

    criteria = load_active_criteria(conn)
    if not criteria:
        raise WorkflowError("No active evaluation criteria found in the database.")

    clean, errors = validate_supplier_inputs(suppliers)
    if errors:
        raise InputError(errors)

    run_id = _new_run_id()
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    repository.create_run(conn, run_id, created_at)

    try:
        skip_warnings: List[str] = []
        skipped: List[Dict[str, str]] = []
        evaluated: List[Dict[str, Any]] = []

        for s in clean:
            name = s["supplier_name"]
            say(f"{name}: extracting text")
            try:
                doc = extract_pdf_text(s["pdf_bytes"], filename=s["filename"])
            except DocumentError as exc:
                skipped.append({"supplier_name": name, "reason": str(exc)})
                skip_warnings.append(f"{name} excluded from ranking: {exc}")
                continue

            try:
                say(f"{name}: evaluating with {model}")
                reply = evaluate_supplier(client, criteria, name, doc["text"], model=model)
            except EvaluationError as exc:
                skipped.append({"supplier_name": name, "reason": str(exc)})
                skip_warnings.append(f"{name} excluded from ranking: {exc}")
                continue

            say(f"{name}: validating")
            validated = validate_evaluation(reply["raw"], criteria, name)
            evaluated.append(
                {
                    "supplier": s,
                    "document": {
                        "filename": s["filename"],
                        "page_count": doc["page_count"],
                        "char_count": doc["char_count"],
                    },
                    "validated": validated,
                    "warnings": list(reply["warnings"]) + list(validated["warnings"]),
                }
            )

        if not evaluated:
            raise WorkflowError("no supplier could be evaluated.")

        warnings = list(skip_warnings)
        if len(evaluated) == 1:
            warnings.append("Only one supplier was evaluated; peer benchmarks and PPI are trivial.")

        ranking = rank_suppliers(
            criteria,
            [
                {
                    "supplier_name": e["supplier"]["supplier_name"],
                    "submission_date": e["supplier"]["submission_date"],
                    "experience_rating": e["supplier"]["experience_rating"],
                    "scores": e["validated"]["scores"],
                }
                for e in evaluated
            ],
        )
        warnings.extend(ranking["warnings"])

        by_name = {e["supplier"]["supplier_name"]: e for e in evaluated}
        ranked_suppliers = []
        for row in ranking["results"]:
            entry = by_name[row["supplier_name"]]
            validated = entry["validated"]
            details = {c["criterion_id"]: c for c in validated["criteria"]}
            for crit_row in row["criteria"]:
                detail = details[crit_row["criterion_id"]]
                crit_row["justification"] = detail["justification"]
                crit_row["evidence"] = detail["evidence"]
                crit_row["is_valid"] = detail["is_valid"]
            row.update(
                {
                    "risks": validated["risks"],
                    "overall_summary": validated["overall_summary"],
                    "evaluation_failed": validated["evaluation_failed"],
                    "warnings": entry["warnings"],
                    "document": entry["document"],
                }
            )
            ranked_suppliers.append(row)
            warnings.extend(entry["warnings"])

        status = "completed_with_warnings" if warnings else "completed"
        export = {
            "rfp_run_id": run_id,
            "created_at": created_at,
            "status": status,
            "model": model,
            "criteria": [
                {
                    "criterion_id": c["criterion_id"],
                    "name": c["name"],
                    "description": c["description"],
                    "weight": c["weight"],
                    "max_score": c["max_score"],
                }
                for c in criteria
            ],
            "benchmarks": {str(cid): value for cid, value in ranking["benchmarks"].items()},
            "tie_break_order": TIE_BREAK_ORDER,
            "tie_break_notes": ranking["tie_break_notes"],
            "suppliers": ranked_suppliers,
            "skipped_suppliers": skipped,
            "warnings": warnings,
        }
        repository.finalize_run(conn, run_id, status, export, ranked_suppliers)
        return export
    except Exception as exc:
        try:
            repository.fail_run(conn, run_id, str(exc))
        except Exception:
            pass
        raise WorkflowError(f"Run {run_id} failed: {exc}") from exc
