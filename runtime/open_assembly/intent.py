import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _engine():
    try:
        from specify_core import api
    except ImportError as exc:
        raise ValueError("Specify is unavailable; restore the pinned runtime with uv sync") from exc
    return api


def questions(store, job_id: str) -> dict:
    api = _engine()
    manifest = store.get(job_id)
    if (manifest["document"] or {}).get("backend") == "smlibpy":
        raise ValueError("Factory intent is not supported for registered native cases")
    if manifest["state"] != "ready":
        raise ValueError("Factory questions require a current geometry-validated assembly")
    step = store.artifact(job_id, "assembly.step")
    step_hash = _sha256(step)
    analyses = []
    parts = []
    for index, part in enumerate(api.parts(step)):
        analysis = api.analyse(step, part=index)
        analyses.append(analysis)
        items = []
        for question in api.questions(analysis, {}):
            data = asdict(question)
            items.append(
                {k: data[k] for k in ["id", "prompt", "kind", "default", "options", "faces", "why"]}
            )
        parts.append(
            {"index": index, "name": part.get("name", f"Part {index + 1}"), "questions": items}
        )
    identity = f"{job_id}:{manifest['revision']}:{step_hash}"
    analysis_id = hashlib.sha256(identity.encode()).hexdigest()[:24]
    saved = {
        "job_id": job_id,
        "revision": manifest["revision"],
        "analysis_id": analysis_id,
        "step_sha256": step_hash,
        "analyses": analyses,
        "parts": parts,
    }
    directory = store.job_directory(job_id) / "intent-analysis"
    directory.mkdir(exist_ok=True)
    target = directory / f"{analysis_id}.json"
    target.write_text(json.dumps(saved, indent=2))
    return {k: v for k, v in saved.items() if k not in {"analyses", "job_id"}}


def write_intent(
    store,
    job_id: str,
    revision: int,
    analysis_id: str,
    answers_by_part: dict,
    confirmed: bool = False,
    accept_defaults: bool = False,
) -> dict:
    if not confirmed:
        raise ValueError("Factory answers need explicit confirmation before writing PMI")
    if (
        not isinstance(analysis_id, str)
        or len(analysis_id) != 24
        or not all(c in "0123456789abcdef" for c in analysis_id)
    ):
        raise ValueError("Invalid factory analysis ID")
    api = _engine()
    manifest = store.get(job_id)
    if (manifest["document"] or {}).get("backend") == "smlibpy":
        raise ValueError("Factory intent is not supported for registered native cases")
    if manifest["revision"] != revision or manifest["state"] != "ready":
        raise ValueError("Factory analysis is stale; rebuild and request current questions")
    saved_path = store.job_directory(job_id) / "intent-analysis" / f"{analysis_id}.json"
    if not saved_path.is_file():
        raise ValueError("Factory analysis is missing; request current questions")
    saved = json.loads(saved_path.read_text())
    step = store.artifact(job_id, "assembly.step")
    if saved["revision"] != revision or saved["step_sha256"] != _sha256(step):
        raise ValueError("The STEP or revision changed; factory answers must be rematched")
    answer_key = hashlib.sha256(
        json.dumps(
            {"analysis": analysis_id, "answers": answers_by_part, "defaults": accept_defaults},
            sort_keys=True,
        ).encode()
    ).hexdigest()[:16]
    output_name = f"assembly-pmi-{answer_key}.step"
    intent_name = f"intent-{answer_key}.json"
    report_name = f"intent-report-{answer_key}.json"
    cached = step.parent / intent_name
    if cached.is_file():
        existing = json.loads(cached.read_text())
        if existing["output_sha256"] != _sha256(step.parent / output_name):
            raise ValueError("Stored PMI output changed; generate a new geometry revision")
        existing.pop("analysis_evidence", None)
        existing["artifacts"][intent_name] = {
            "path": intent_name,
            "sha256": _sha256(cached),
            "size": cached.stat().st_size,
        }
        store.update_intent(job_id, revision, existing)
        return existing
    expected = {str(i) for i in range(len(saved["analyses"]))}
    if not isinstance(answers_by_part, dict) or set(answers_by_part) - expected:
        raise ValueError("Answers refer to an unknown part definition")
    intents = []
    for index, analysis in enumerate(saved["analyses"]):
        answers = answers_by_part.get(str(index), {})
        if not isinstance(answers, dict):
            raise ValueError("Each part's answers must be a question-to-value object")
        allowed = {q["id"] for q in saved["parts"][index]["questions"]}
        if set(answers) - allowed:
            raise ValueError("An answer does not belong to this part's current interview")
        try:
            intents.append((api.apply(analysis, answers, accept_defaults=accept_defaults), answers))
        except (ValueError, RuntimeError) as exc:
            raise ValueError(
                f"Part {index + 1} factory requirements are incomplete or invalid: {exc}"
            ) from exc
    output = step.parent / output_name
    try:
        report = api.write_parts(step, intents, output)
    except (ValueError, RuntimeError) as exc:
        raise ValueError(f"Specify could not verify the PMI write: {exc}") from exc
    details = asdict(report)
    details["output"] = output_name
    readback = api.parts(output)
    original = api.parts(step)
    preserved = len(readback) == len(original) and all(
        before["product_id"] == after["product_id"]
        and before["instances"] == after["instances"]
        and np.allclose(before["placements"], after["placements"], atol=1e-6)
        for before, after in zip(original, readback)
    )
    if not preserved:
        raise ValueError("PMI export changed part definitions or occurrence counts")
    written = details.get("written", [])
    not_written = details.get("not_written", [])
    warnings = details.get("warnings", [])
    complete = not not_written and not warnings
    result = {
        "revision": revision,
        "analysis_id": analysis_id,
        "step_sha256": saved["step_sha256"],
        "output_sha256": _sha256(output),
        "output": output_name,
        "confirmed": True,
        "accepted_displayed_defaults": accept_defaults,
        "answers": answers_by_part,
        "verified": not not_written,
        "complete": complete,
        "state": "verified" if complete else "needs_review",
        "written": written,
        "not_written": not_written,
        "warnings": warnings,
        "assembly_preserved": preserved,
    }
    intent_file = step.parent / intent_name
    report_file = step.parent / report_name
    report_file.write_text(json.dumps(details, indent=2))
    result["artifacts"] = {
        name: {
            "path": name,
            "sha256": _sha256(step.parent / name),
            "size": (step.parent / name).stat().st_size,
        }
        for name in [output_name, report_name]
    }
    intent_file.write_text(json.dumps({**result, "analysis_evidence": saved}, indent=2))
    result["artifacts"][intent_name] = {
        "path": intent_name,
        "sha256": _sha256(intent_file),
        "size": intent_file.stat().st_size,
    }
    store.update_intent(job_id, revision, result)
    return result
