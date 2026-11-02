import json
import time
from pathlib import Path


def evaluate(output: Path, count: int = 10) -> dict:
    from .fixtures import create_cohort
    from .project import ProjectStore

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    cases = create_cohort(output / "fixtures", count)
    store = ProjectStore(output / "workspace")
    results = []
    for case in cases:
        start = time.perf_counter()
        job = store.create(Path(case["input"]), "mm")
        elapsed = time.perf_counter() - start
        reference = case["metadata"]
        doc = job.get("document") or {}
        validation = job.get("validation") or {}
        counts_match = (
            len(doc.get("occurrences", [])) == reference["occurrence_count"]
            and len(doc.get("definitions", [])) == reference["definition_count"]
        )
        results.append(
            {
                "variant": reference["variant"],
                "id": job["id"],
                "state": job["state"],
                "accepted_geometry": job["state"] == "ready"
                and validation.get("valid", False)
                and counts_match,
                "seconds": elapsed,
                "definition_count": len(doc.get("definitions", [])),
                "occurrence_count": len(doc.get("occurrences", [])),
                "error": job.get("error"),
                "validation": validation,
            }
        )
    summary = {
        "scope": "Self-authored analytic feasibility fixtures. These related variants are not a held-out industrial benchmark.",
        "cases": results,
        "accepted_geometry": sum(r["accepted_geometry"] for r in results),
        "attempted": len(results),
        "model_calls": 0,
        "api_model_charges_usd": 0,
        "compute_and_labor_cost": "not monetized",
        "cost_advantage": "unproven",
        "whole_object_llm": "not run; provider not configured",
        "hierarchical_llm": "not run; use the MCP skill with a chat host or configure a metered evaluation provider",
        "specialized_checkpoint": "not run; no eligible checkpoint executed",
        "factory_intent": "tested separately; not included in geometry acceptance",
        "editability": "requires separate parameter-edit and source-replay evidence",
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary
