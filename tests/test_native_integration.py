import hashlib
import json
import os
from pathlib import Path

import pytest
from open_assembly.document import NATIVE_SOURCE_SHA256, parse_document
from open_assembly.native import _comparison
from open_assembly.project import ProjectStore


@pytest.fixture(scope="module")
def real_native_run(tmp_path_factory):
    if not os.environ.get("OPEN_ASSEMBLY_SMLIB_PYTHON"):
        pytest.skip("Set OPEN_ASSEMBLY_SMLIB_PYTHON for the real native integration")
    evidence = os.environ.get("OPEN_ASSEMBLY_NATIVE_TEST_EVIDENCE")
    if evidence:
        root = Path(evidence)
        baseline = json.loads((root / "baseline.json").read_text())
        edited = json.loads((root / "edited.json").read_text())
        return ProjectStore(root / "jobs"), baseline, edited
    store = ProjectStore(tmp_path_factory.mktemp("native-kernel") / "jobs")
    baseline = store.create_native_example({"case_id": "wiring-cover"})
    assert baseline["state"] == "ready", baseline["error"]
    store.update_context(baseline["id"], 0, {"goal": "Raise the hook by 1 mm"})
    store.capture_change_request(
        baseline["id"],
        {
            "request_id": "real-hook-raise",
            "revision": 1,
            "context_revision": 1,
            "target": {"kind": "occurrence", "occurrence_id": "wiring_cover_1"},
            "text": "Raise hook_top from 5.55 to 6.55 mm.",
        },
    )
    edited = store.native_edit(baseline["id"], {"request_id": "real-hook-raise", "hook_top": 6.55})
    return store, baseline, edited


def test_real_native_baseline_edit_and_deliverable_identity(real_native_run):
    store, baseline, edited = real_native_run
    assert baseline["revision"] == 1 and baseline["state"] == "ready"
    assert edited["revision"] == 2 and edited["state"] == "ready", edited["error"]
    assert (
        baseline["artifacts"]["assembly.step"]["sha256"]
        != edited["artifacts"]["assembly.step"]["sha256"]
    )
    for job in (baseline, edited):
        output = store.job_directory(job["id"]) / job["artifact_directory"]
        document = parse_document(job["document"])
        collected = store._validated_artifacts(document, output, {"validation": job["validation"]})
        assert collected == job["artifacts"]
        assert (
            hashlib.sha256((output / "source.py").read_bytes()).hexdigest() == NATIVE_SOURCE_SHA256
        )
        validation = json.loads((output / "validation.json").read_text())
        report = validation["native"]
        assert report["runtime"]["smlibpy"]
        assert len(report["runtime"]["binary_sha256"]) == 64
        assert report["runtime"]["foreign_construction_modules_loaded"] == []
        assert all(report["checks"].values())
        assert validation["independent_step"]["valid"]
        assert validation["independent_step"]["units_mm"]
        assert validation["independent_step"]["solid_count"] == 1
        assert len(job["document"]["definitions"]) == len(job["document"]["occurrences"]) == 1
        construction = json.loads((output / "construction.json").read_text())
        assert construction["physical_part_count"] == 1
        assert len(construction["stages"]) == 10
        for stage in construction["stages"]:
            preview = json.loads((output / stage["preview_artifact"]).read_text())
            assert len(preview["parts"]) == 1
            assert len(preview["parts"][0]["vertices"][0]) == 3
            assert len(preview["parts"][0]["triangles"][0]) == 3
            assert preview["bounds"] == stage["metrics"]["bounds"]
            assert (output / stage["native_artifact"]).stat().st_size > 1000
        assert json.loads(
            (output / construction["stages"][-1]["preview_artifact"]).read_text()
        ) == json.loads((output / "preview.json").read_text())
    comparison = edited["validation"]["comparison"]
    assert comparison["valid"]
    assert comparison["volume_delta_mm3"] == pytest.approx(12.045, abs=0.001)
    assert comparison["z_max_delta_mm"] == pytest.approx(1.0, abs=1e-9)
    assert len(comparison["protected_stages"]) == 6
    step = store.artifact(edited["id"], "assembly.step")
    assert (
        hashlib.sha256(step.read_bytes()).hexdigest()
        == edited["executions"][-1]["output_step_sha256"]
    )
    assert edited["executions"][-1]["request_id"] == "real-hook-raise"
    assert edited["change_requests"][0]["execution"] == "pending"


def test_protected_metrics_reject_changes_without_exact_float_equality(real_native_run):
    _, baseline, edited = real_native_run
    before = baseline["validation"]["native"]
    after = json.loads(json.dumps(edited["validation"]["native"]))
    after["stages"][5]["metrics"]["bounds"][0][1] += 1e-14
    assert _comparison(before, after, 1, 5.55, 6.55)["valid"]
    after["stages"][5]["metrics"]["faces"] += 1
    assert not _comparison(before, after, 1, 5.55, 6.55)["valid"]
