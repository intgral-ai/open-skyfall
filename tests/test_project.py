import json
import sys
import threading
import types
import zipfile
from pathlib import Path

import pytest
from open_assembly.document import AssemblyDocument
from open_assembly.project import ArtifactUnavailable, ProjectStore, RevisionConflict


def measured_document():
    return AssemblyDocument.model_validate(
        {
            "input": {"name": "measured.png", "sha256": "a" * 64, "kind": "image", "units": "mm"},
            "definitions": [
                {
                    "id": "plate",
                    "label": "Base plate",
                    "recipe": {
                        "kind": "plate",
                        "parameters": {"length": 40, "width": 30, "height": 5},
                        "holes": [],
                    },
                }
            ],
            "occurrences": [{"id": "base", "definition_id": "plate"}],
        }
    )


def controlled_build(document, directory, reference_mesh=None):
    directory = Path(directory)
    validation = {
        "valid": True,
        "roundtrip_valid": True,
        "solid_count": len(document.occurrences),
        "expected_solid_count": len(document.occurrences),
    }
    (directory / "assembly.step").write_text(f"STEP {document.revision}")
    (directory / "source.py").write_text("raise RuntimeError('source must never execute')")
    (directory / "document.json").write_text(document.model_dump_json())
    (directory / "preview.json").write_text(
        json.dumps({"parts": [], "bounds": [[0, 0, 0], [40, 30, 5]]})
    )
    (directory / "validation.json").write_text(json.dumps(validation))
    (directory / "parts").mkdir()
    (directory / "parts" / "plate.step").write_text("part STEP")
    return {"validation": validation, "artifacts": {}}


@pytest.fixture
def geometry_stub(monkeypatch):
    module = types.ModuleType("open_assembly.geometry")
    module.build_assembly = controlled_build
    monkeypatch.setitem(sys.modules, "open_assembly.geometry", module)
    return module


@pytest.fixture
def image(tmp_path):
    path = tmp_path / "measured.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"measured reference")
    return path


@pytest.fixture
def ready_store(tmp_path, image, geometry_stub):
    store = ProjectStore(tmp_path / "projects")
    job = store.create(image, "mm")
    job = store.set_design(job["id"], job["revision"], measured_document())
    assert job["state"] == "ready"
    return store, job


def test_image_requires_host_measured_design(tmp_path, image):
    store = ProjectStore(tmp_path / "projects")
    job = store.create(image, "mm")
    assert job["state"] == "needs_evidence"
    assert job["document"] is None
    assert "host-provided measured" in job["error"]["message"]
    assert (store.job_directory(job["id"]) / "input.png").read_bytes() == image.read_bytes()
    assert store.rebuild(job["id"], 1)["state"] == "needs_evidence"


def test_units_are_never_guessed(tmp_path):
    path = tmp_path / "unknown.stl"
    path.write_bytes(b"not a mesh")
    store = ProjectStore(tmp_path / "projects")
    assert store.create(path, None)["state"] == "needs_evidence"
    with pytest.raises(ValueError, match="Units"):
        store.create(path, "meters")


def test_invalid_and_oversized_input(tmp_path):
    store = ProjectStore(tmp_path / "projects")
    path = tmp_path / "empty.stl"
    path.touch()
    with pytest.raises(ValueError, match="nonempty"):
        store.create(path, "mm")
    path = tmp_path / "fake.png"
    path.write_bytes(b"not a PNG")
    with pytest.raises(ValueError, match="Image content"):
        store.create(path, "mm")
    path = tmp_path / "large.stl"
    with path.open("wb") as stream:
        stream.truncate(30 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="30 MB"):
        store.create(path, "mm")


def test_malformed_mesh_is_reported(tmp_path, monkeypatch):
    module = types.ModuleType("open_assembly.reconstruction")

    def reject(path, units):
        raise ValueError("STL contains no triangles")

    module.inspect_stl = reject
    monkeypatch.setitem(sys.modules, "open_assembly.reconstruction", module)
    path = tmp_path / "broken.stl"
    path.write_bytes(b"solid broken\nendsolid")
    store = ProjectStore(tmp_path / "projects")
    job = store.create(path, "mm")
    assert job["state"] == "failed"
    assert job["error"]["message"] == "STL contains no triangles"
    assert job["artifacts"] == {}


def test_edit_is_revision_safe_and_clears_exports(ready_store):
    store, job = ready_store
    original = store.artifact(job["id"], "assembly.step")
    original_bytes = original.read_bytes()
    revised = store.edit(job["id"], job["revision"], "plate", {"length": 50}, defer_build=True)
    assert revised["revision"] == job["revision"] + 1
    assert revised["artifacts"] == {}
    assert revised["intent"] is None
    with pytest.raises(RevisionConflict):
        store.edit(job["id"], job["revision"], "plate", {"length": 60})
    with pytest.raises(ArtifactUnavailable):
        store.artifact(job["id"], "assembly.step")
    with pytest.raises(ArtifactUnavailable):
        store.bundle(job["id"])
    built = store.rebuild(job["id"], revised["revision"])
    assert built["state"] == "ready"
    assert store.artifact(job["id"], "assembly.step") != original
    assert original.read_bytes() == original_bytes


def test_invalid_edit_does_not_change_revision(ready_store):
    store, job = ready_store
    with pytest.raises(ValueError):
        store.edit(job["id"], job["revision"], "plate", {"length": -3})
    assert store.get(job["id"]) == job
    with pytest.raises(RevisionConflict):
        store.set_design(job["id"], None, measured_document())


def test_old_build_cannot_publish_after_edit(ready_store, geometry_stub):
    store, job = ready_store
    started, finish = threading.Event(), threading.Event()

    def delayed(document, directory, reference_mesh=None):
        started.set()
        assert finish.wait(5)
        return controlled_build(document, directory, reference_mesh)

    geometry_stub.build_assembly = delayed
    worker = threading.Thread(target=store.rebuild, args=(job["id"], job["revision"]))
    worker.start()
    assert started.wait(5)
    revised = store.edit(job["id"], job["revision"], "plate", {"length": 75}, defer_build=True)
    finish.set()
    worker.join(5)
    assert not worker.is_alive()
    assert store.get(job["id"])["revision"] == revised["revision"]
    assert store.get(job["id"])["state"] == "queued"
    assert store.get(job["id"])["artifacts"] == {}


def test_cancel_invalidates_inflight_build(ready_store, geometry_stub):
    store, job = ready_store
    started, finish = threading.Event(), threading.Event()

    def delayed(document, directory, reference_mesh=None):
        started.set()
        assert finish.wait(5)
        return controlled_build(document, directory, reference_mesh)

    geometry_stub.build_assembly = delayed
    worker = threading.Thread(target=store.rebuild, args=(job["id"], job["revision"]))
    worker.start()
    assert started.wait(5)
    cancelled = store.cancel(job["id"])
    finish.set()
    worker.join(5)
    assert store.get(job["id"]) == cancelled
    assert cancelled["state"] == "cancelled"


@pytest.mark.parametrize(
    "name",
    [
        "../manifest.json",
        "/etc/passwd",
        "parts/../../input.png",
        "parts\\plate.step",
        "./assembly.step",
    ],
)
def test_unsafe_artifact_names_are_rejected(ready_store, name):
    store, job = ready_store
    with pytest.raises(ValueError):
        store.artifact(job["id"], name)


def test_artifacts_cannot_change_after_validation(ready_store):
    store, job = ready_store
    path = store.artifact(job["id"], "assembly.step")
    path.write_text("tampered")
    with pytest.raises(ArtifactUnavailable, match="changed"):
        store.artifact(job["id"], "assembly.step")
    with pytest.raises(ArtifactUnavailable):
        store.bundle(job["id"])


def test_bundle_contains_only_current_accepted_artifacts(ready_store):
    store, job = ready_store
    with zipfile.ZipFile(store.bundle(job["id"])) as bundle:
        assert set(bundle.namelist()) == {"manifest.json", *job["artifacts"]}
        assert json.loads(bundle.read("manifest.json"))["revision"] == job["revision"]
        assert (
            bundle.read("assembly.step") == store.artifact(job["id"], "assembly.step").read_bytes()
        )


def test_intent_publication_preserves_geometry_and_checks_revision(ready_store):
    store, job = ready_store
    assembly = store.artifact(job["id"], "assembly.step")
    (assembly.parent / "assembly-pmi.step").write_text("STEP with actual engine intent")
    result = {"artifacts": {"assembly-pmi.step": {}}, "report": {"written": True}}
    updated = store.update_intent(job["id"], job["revision"], result)
    assert updated["intent"] == result
    assert updated["artifacts"]["assembly.step"] == job["artifacts"]["assembly.step"]
    assert (
        store.artifact(job["id"], "assembly-pmi.step").read_text()
        == "STEP with actual engine intent"
    )
    with pytest.raises(RevisionConflict):
        store.update_intent(job["id"], job["revision"] - 1, result)


def test_failed_geometry_never_publishes(ready_store, geometry_stub):
    store, job = ready_store

    def rejected(document, directory, reference_mesh=None):
        result = controlled_build(document, directory, reference_mesh)
        result["validation"]["valid"] = False
        return result

    geometry_stub.build_assembly = rejected
    failed = store.rebuild(job["id"], job["revision"])
    assert failed["state"] == "failed"
    assert failed["artifacts"] == {}
    with pytest.raises(ArtifactUnavailable):
        store.artifact(job["id"], "assembly.step")


def test_create_document_replays_a_validated_measured_recipe(tmp_path, geometry_stub):
    store = ProjectStore(tmp_path / "projects")
    document = measured_document()
    job = store.create_document(document, "Measured assembly")
    assert job["state"] == "ready"
    assert job["name"] == "Measured assembly"
    assert job["input"]["kind"] == "recipe"
    source = store.job_directory(job["id"]) / "input.json"
    assert AssemblyDocument.model_validate_json(source.read_bytes()) == document
    assert store.artifact(job["id"], "assembly.step").is_file()


def test_create_document_rejects_unknown_units(tmp_path, geometry_stub):
    store = ProjectStore(tmp_path / "projects")
    document = measured_document().model_dump()
    document["input"]["units"] = None
    with pytest.raises(ValueError, match="explicit input units"):
        store.create_document(document)
    assert store.list() == []
