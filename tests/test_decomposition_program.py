import copy
import hashlib
import json
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from open_assembly.decomposition import DecompositionStore, Plan, parameter_values, replay_bundle
from PIL import Image


@pytest.fixture
def image_bytes():
    buffer = BytesIO()
    Image.new("RGB", (100, 80), "white").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def explained_plan(image_bytes):
    parameters = {}
    for field, count in [("dimensions", 3), ("position", 3), ("rotation", 3)]:
        for i in range(count):
            parameters[f"shape/body/block/{field}/{i}"] = "synthetic"
    for node in ["root", "part"]:
        for field in ["position", "rotation"]:
            for i in range(3):
                parameters[f"node/{node}/{field}/{i}"] = "synthetic"
    return {
        "schema_version": 2,
        "source_sha256": hashlib.sha256(image_bytes).hexdigest(),
        "scale_note": "Synthetic relative units for a runtime test, not image measurement.",
        "assumptions": ["The blank image has no dimensional or physical-part evidence."],
        "definitions": [
            {"id": "body", "shapes": [{"id": "block", "kind": "box", "dimensions": [2, 3, 4]}]}
        ],
        "nodes": [
            {
                "id": "root",
                "label": "Root",
                "evidence": "inferred",
                "note": "Synthetic test assembly.",
            },
            {
                "id": "part",
                "label": "Part",
                "parent_id": "root",
                "definition_id": "body",
                "evidence": "unknown",
                "note": "Synthetic test geometry.",
            },
        ],
        "explanation": {
            "observations": [
                {
                    "id": "blank",
                    "region": [0, 0, 1, 1],
                    "statement": "The synthetic image is blank.",
                }
            ],
            "bases": {
                "synthetic": {
                    "kind": "assumed",
                    "observations": ["blank"],
                    "why": "Test values only. No source fidelity is claimed.",
                }
            },
            "parameters": parameters,
            "shapes": {"body/block": "synthetic"},
            "nodes": {
                id: {"part": "synthetic", "placement": "synthetic"} for id in ["root", "part"]
            },
            "scale": "synthetic",
        },
    }


def test_explanation_addresses_cover_default_poses_and_dimensions(explained_plan):
    plan = Plan.model_validate(explained_plan)
    values = parameter_values(plan)
    assert len(values) == 21
    assert values["shape/body/block/dimensions/2"] == 4
    assert values["shape/body/block/rotation/1"] == 0
    assert values["node/part/position/0"] == 0


@pytest.mark.parametrize(
    "defect",
    [
        "missing",
        "unknown-target",
        "basis",
        "observation",
        "region",
        "shape-id",
        "unsupported-observed",
    ],
)
def test_explanation_rejects_broken_bindings(explained_plan, defect):
    plan = copy.deepcopy(explained_plan)
    explanation = plan["explanation"]
    if defect == "missing":
        del explanation["parameters"]["shape/body/block/dimensions/0"]
    elif defect == "unknown-target":
        explanation["parameters"]["shape/body/block/hidden/0"] = "synthetic"
    elif defect == "basis":
        explanation["scale"] = "missing"
    elif defect == "observation":
        explanation["bases"]["synthetic"]["observations"] = ["missing"]
    elif defect == "region":
        explanation["observations"][0]["region"] = [0.8, 0, 0.1, 1]
    elif defect == "shape-id":
        del plan["definitions"][0]["shapes"][0]["id"]
    else:
        explanation["bases"]["synthetic"].update(kind="observed", observations=[])
    with pytest.raises(ValueError):
        Plan.model_validate(plan)


def accept(store, image_bytes, plan):
    project = store.create(image_bytes, "Test concept", "Original synthetic test image")
    return store.update(project["id"], {"revision": 0, "plan": plan})


def unpack(bundle, destination):
    destination.mkdir()
    with zipfile.ZipFile(bundle) as archive:
        for name in archive.namelist():
            (destination / name).write_bytes(archive.read(name))
    return destination


def update_file_hash(directory, name):
    manifest = json.loads((directory / "bundle-manifest.json").read_text())
    raw = (directory / name).read_bytes()
    manifest["files"][name] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    (directory / "bundle-manifest.json").write_text(json.dumps(manifest))


def test_revision_bundle_replay_and_immutable_history(tmp_path, image_bytes, explained_plan):
    store = DecompositionStore(tmp_path / "store")
    first = accept(store, image_bytes, explained_plan)
    assert first["analysis"]["coverage"]["status"] == "complete"
    assert first["analysis"]["binding"]["program_sha256"] == first["artifacts"][first["program"]]
    assert len(first["analysis"]["trace"]) == 5
    original = store.bundle(first["id"]).read_bytes()
    explained_plan["definitions"][0]["shapes"][0]["dimensions"][0] = 5
    second = store.update(first["id"], {"revision": 1, "plan": explained_plan})
    assert second["revision"] == 2
    assert (
        store.revision(first["id"], 1)["plan"]["definitions"][0]["shapes"][0]["dimensions"][0] == 2
    )
    assert store.bundle(first["id"], 1).read_bytes() == original
    report = replay_bundle(store.bundle(first["id"], 1), tmp_path / "replay-one")
    assert report["outcome"] == "pass"
    assert report["binding"]["revision"] == 1
    for filename, key in [
        ("preview.json", "actual_preview_sha256"),
        ("trace.json", "actual_trace_sha256"),
    ]:
        assert (
            hashlib.sha256((tmp_path / "replay-one" / filename).read_bytes()).hexdigest()
            == report[key]
        )
    assert report["source_sha256"] == hashlib.sha256(image_bytes).hexdigest()
    checks = {check["scope"]: check["outcome"] for check in report["checks"]}
    assert checks["explanation_coverage"] == checks["replay"] == "pass"
    assert (
        checks["source_fidelity"] == checks["native_cad"] == checks["manufacturing"] == "unchecked"
    )
    replay_bundle(store.bundle(first["id"]), tmp_path / "replay-two")
    assert (
        json.loads((tmp_path / "replay-two/preview.json").read_text())["parts"][0]["bounds"][1][0]
        == 2.5
    )
    before = (tmp_path / "replay-two/replay-report.json").read_bytes()
    with pytest.raises(ValueError, match="empty directory"):
        replay_bundle(store.bundle(first["id"]), tmp_path / "replay-two")
    assert (tmp_path / "replay-two/replay-report.json").read_bytes() == before


@pytest.mark.parametrize(
    "name", ["source.bin", "program.json", "preview.json", "trace.json", "checks.json"]
)
def test_bundle_rejects_unregistered_byte_changes(tmp_path, image_bytes, explained_plan, name):
    store = DecompositionStore(tmp_path / "store")
    project = accept(store, image_bytes, explained_plan)
    directory = unpack(store.bundle(project["id"]), tmp_path / "bundle")
    with (directory / name).open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="integrity failed"):
        replay_bundle(directory, tmp_path / "must-stay-absent")
    assert not (tmp_path / "must-stay-absent").exists()


@pytest.mark.parametrize(
    "defect", ["vertices", "identity", "indices", "normalization", "trace", "checks"]
)
def test_replay_detects_semantic_faults_even_with_updated_file_hashes(
    tmp_path, image_bytes, explained_plan, defect
):
    store = DecompositionStore(tmp_path / "store")
    project = accept(store, image_bytes, explained_plan)
    directory = unpack(store.bundle(project["id"]), tmp_path / "bundle")
    name = (
        "trace.json"
        if defect == "trace"
        else "checks.json"
        if defect == "checks"
        else "preview.json"
    )
    value = json.loads((directory / name).read_text())
    if defect == "vertices":
        value["parts"][0]["vertices"][0][0] += 0.1
    elif defect == "identity":
        value["parts"][0]["id"] = "another-part"
    elif defect == "indices":
        value["parts"][0]["triangles"][0][0] = 100000
    elif defect == "normalization":
        value["normalization"]["scale"] *= 2
    elif defect == "trace":
        value[0]["parameters"]["dimensions"][0] = 99
    else:
        next(check for check in value["checks"] if check["scope"] == "native_cad")["outcome"] = (
            "pass"
        )
    (directory / name).write_text(json.dumps(value))
    update_file_hash(directory, name)
    report = replay_bundle(directory, tmp_path / "replay")
    assert report["outcome"] == "fail", report
    if defect == "trace":
        assert report["trace_matches"] is False
    elif defect == "checks":
        assert report["stored_checks_match"] is False
    else:
        assert report["geometry_matches"] is False


def test_unsupported_runtime_and_broken_program_do_not_replay(
    tmp_path, image_bytes, explained_plan
):
    store = DecompositionStore(tmp_path / "store")
    project = accept(store, image_bytes, explained_plan)
    directory = unpack(store.bundle(project["id"]), tmp_path / "bundle")
    program = json.loads((directory / "program.json").read_text())
    program["runtime"]["recipe"] = "unknown"
    (directory / "program.json").write_text(json.dumps(program))
    update_file_hash(directory, "program.json")
    with pytest.raises(ValueError, match=r"Unsupported runtime profile \(recipe\)"):
        replay_bundle(directory, tmp_path / "replay")
    program["plan"]["explanation"]["parameters"].pop("node/part/rotation/0")
    (directory / "program.json").write_text(json.dumps(program))
    update_file_hash(directory, "program.json")
    with pytest.raises(ValueError, match="cover every"):
        replay_bundle(directory, tmp_path / "replay")


def test_bundle_rejects_replaced_runner_even_with_updated_hashes(
    tmp_path, image_bytes, explained_plan
):
    store = DecompositionStore(tmp_path / "store")
    project = accept(store, image_bytes, explained_plan)
    directory = unpack(store.bundle(project["id"]), tmp_path / "bundle")
    marker = tmp_path / "must-not-exist"
    (directory / "replay.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
    )
    update_file_hash(directory, "replay.py")
    with pytest.raises(ValueError, match="reviewed runner"):
        replay_bundle(directory, tmp_path / "replay")
    assert not marker.exists()
    assert not (tmp_path / "replay").exists()


def test_symlink_workspace_uses_one_canonical_artifact_root(tmp_path, image_bytes, explained_plan):
    actual = tmp_path / "actual"
    actual.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(actual, target_is_directory=True)
    store = DecompositionStore(alias)
    project = accept(store, image_bytes, explained_plan)
    assert store.root == actual / "decompositions"
    assert replay_bundle(store.bundle(project["id"]), tmp_path / "replay")["outcome"] == "pass"


def test_fresh_dimensioned_worktable_is_replayable(tmp_path):
    case = Path(__file__).resolve().parents[1] / "examples/decomposition/worktable"
    store = DecompositionStore(tmp_path / "store")
    project = accept(
        store, (case / "reference.png").read_bytes(), json.loads((case / "plan.json").read_text())
    )
    preview = json.loads(store.artifact(project["id"], project["preview"]).read_text())
    assert len(preview["parts"]) == 5
    assert {part["definition_id"] for part in preview["parts"]} == {
        "top-definition",
        "leg-definition",
    }
    assert min(part["bounds"][0][2] for part in preview["parts"]) == 0
    assert max(part["bounds"][1][2] for part in preview["parts"]) == 450
    by_id = {part["id"]: part for part in preview["parts"]}
    assert by_id["top"]["bounds"] == [[-200, -150, 430], [200, 150, 450]]
    for node, x, y in [
        ("leg-front-left", -170, -120),
        ("leg-front-right", 170, -120),
        ("leg-back-left", -170, 120),
        ("leg-back-right", 170, 120),
    ]:
        assert by_id[node]["bounds"] == [[x - 15, y - 15, 0], [x + 15, y + 15, 430]]
    report = replay_bundle(store.bundle(project["id"]), tmp_path / "replay")
    assert report["outcome"] == "pass"
    assert report["coverage"]["parameter_count"] == 54
