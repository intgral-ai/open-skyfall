import base64
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from open_assembly.decomposition import DecompositionStore, Plan, build_preview
from open_assembly.project import ProjectStore, RevisionConflict
from open_assembly.server import create_app

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/decomposition"


@pytest.fixture
def plan():
    return json.loads((EXAMPLE / "plan.json").read_text())


def create(store):
    return store.create(
        (EXAMPLE / "desk-lamp.png").read_bytes(), "Lamp", "Original MIT illustration"
    )


@pytest.mark.parametrize(
    "failure", ["cycle", "parent", "ancestor", "duplicate", "definition", "leaf", "nan", "wall"]
)
def test_reject_invalid_geometry_and_hierarchy(plan, failure):
    if failure == "cycle":
        plan["nodes"][1]["parent_id"] = "support"
        plan["nodes"][4]["parent_id"] = "head"
    elif failure == "parent":
        plan["nodes"][1]["parent_id"] = "shade"
    elif failure == "ancestor":
        plan["nodes"][4]["parent_id"] = "missing"
        plan["nodes"].reverse()
    elif failure == "duplicate":
        plan["nodes"][2]["id"] = "head"
    elif failure == "definition":
        plan["nodes"][2]["definition_id"] = "missing"
    elif failure == "leaf":
        plan["nodes"].append(
            {
                "id": "empty",
                "label": "Empty",
                "parent_id": "lamp",
                "evidence": "unknown",
                "note": "No geometry",
            }
        )
    elif failure == "nan":
        plan["nodes"][0]["position"] = [0, 0, float("nan")]
    else:
        plan["definitions"][0]["shapes"][0]["dimensions"][3] = 2
    with pytest.raises(ValueError):
        Plan.model_validate(plan)


def test_parent_transforms_shared_definitions_and_whole_normalization(plan):
    plan["nodes"].append(
        {
            "id": "other-base",
            "label": "Repeated base",
            "parent_id": "support",
            "definition_id": "base-shape",
            "position": [4, 0, 0],
            "evidence": "inferred",
            "note": "Test repeated placement",
        }
    )
    first = build_preview(Plan.model_validate(plan))
    parts = {part["id"]: part for part in first["parts"]}
    assert len(parts) == 6
    assert parts["base"]["definition_id"] == parts["other-base"]["definition_id"]
    assert np.array(parts["other-base"]["bounds"]).mean(axis=0) == pytest.approx([4, 0, 0])
    assert np.array(parts["shade"]["bounds"]).mean(axis=0) == pytest.approx([0, 0, 2.35])
    plan["nodes"][0]["position"] = [10, -7, 2]
    translated = build_preview(Plan.model_validate(plan))
    assert translated["normalization"]["scale"] == pytest.approx(first["normalization"]["scale"])
    assert np.subtract(
        translated["normalization"]["center"], first["normalization"]["center"]
    ) == pytest.approx([10, -7, 2])
    assert parts["base"]["bounds"][1][0] - parts["base"]["bounds"][0][0] == pytest.approx(1.68)


def test_revisions_source_binding_assets_and_reopen(tmp_path, plan):
    store = DecompositionStore(tmp_path)
    project = create(store)
    bad = copy.deepcopy(plan)
    bad["source_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="different source"):
        store.update(project["id"], {"revision": 0, "plan": bad})
    ready = store.update(project["id"], {"revision": 0, "plan": plan})
    assert ready["state"] == "ready"
    assert (
        len(json.loads(store.artifact(project["id"], ready["preview"]).read_text())["parts"]) == 5
    )
    with pytest.raises(RevisionConflict):
        store.update(project["id"], {"revision": 0, "plan": plan})
    plan["nodes"][2]["label"] = "Renamed shade"
    updated = store.update(project["id"], {"revision": 1, "plan": plan})
    reopened = DecompositionStore(tmp_path).get(project["id"])
    assert reopened == updated
    assert reopened["plan"]["nodes"][2]["id"] == "shade"
    assert reopened["plan"]["nodes"][2]["label"] == "Renamed shade"
    with pytest.raises(FileNotFoundError):
        store.artifact(project["id"], ready["preview"])
    with pytest.raises(FileNotFoundError):
        store.artifact(project["id"], "../manifest.json")
    path = store.artifact(project["id"], updated["preview"])
    path.write_text("{}")
    with pytest.raises(ValueError, match="integrity"):
        store.artifact(project["id"], updated["preview"])


def test_two_writers_cannot_publish_the_same_revision(tmp_path, plan):
    store = DecompositionStore(tmp_path)
    project = create(store)

    def update(_):
        try:
            return DecompositionStore(tmp_path).update(
                project["id"], {"revision": 0, "plan": plan}
            )["revision"]
        except RevisionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, range(2)))
    assert sorted(map(str, results)) == ["1", "conflict"]


def test_changed_source_cannot_be_read_or_used_to_publish(tmp_path, plan):
    store = DecompositionStore(tmp_path)
    project = create(store)
    (store.directory(project["id"]) / "source.bin").write_bytes(b"changed")
    with pytest.raises(ValueError, match="Source image integrity"):
        store.reference(project["id"])
    with pytest.raises(ValueError, match="Source image integrity"):
        store.update(project["id"], {"revision": 0, "plan": plan})
    assert store.get(project["id"])["state"] == "awaiting_plan"


def test_http_input_plan_reference_conflict_and_legacy_separation(tmp_path, plan):
    store = ProjectStore(tmp_path)
    with TestClient(
        create_app(store), base_url="http://127.0.0.1", client=("127.0.0.1", 50000)
    ) as client:
        raw = (EXAMPLE / "desk-lamp.png").read_bytes()
        source = {
            "data_base64": base64.b64encode(raw).decode(),
            "rights": "Original MIT illustration",
            "name": "Lamp",
        }
        response = client.post("/api/decompositions", json=source)
        assert response.status_code == 201, response.text
        project = response.json()
        path = f"/api/decompositions/{project['id']}"
        assert project["state"] == "awaiting_plan"
        assert client.get(path + "/reference").content.startswith(b"\x89PNG")
        assert client.get("/api/jobs").json() == []
        assert client.get("/api/decomposition-schema").status_code == 200
        example = client.get("/api/decomposition-example").json()
        assert example["id"] == "example" and len(example["preview_data"]["parts"]) == 5
        command = {"revision": 0, "plan": plan}
        response = client.put(path + "/plan", json=command)
        assert response.status_code == 200, response.text
        ready = response.json()
        assert client.get(path + "/artifacts/" + ready["preview"]).status_code == 200
        assert client.put(path + "/plan", json=command).status_code == 409
        assert client.post("/api/decompositions", json={**source, "rights": ""}).status_code == 422
        assert (
            client.post("/api/decompositions", json={**source, "data_base64": "bad"}).status_code
            == 422
        )
        assert (
            client.post(
                "/api/decompositions", json=source, headers={"Origin": "https://untrusted.example"}
            ).status_code
            == 403
        )
        assert client.get("/api/decompositions/not-an-id").status_code == 422
