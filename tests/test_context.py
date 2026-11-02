import asyncio
import hashlib
import json
import threading
import zipfile
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from mcp.server.fastmcp.exceptions import ToolError
from open_assembly.context import ProjectContext
from open_assembly.mcp import create_mcp
from open_assembly.project import ProjectStore, RevisionConflict
from open_assembly.server import create_app
from test_project import controlled_build, measured_document
from test_project import geometry_stub as geometry_stub
from test_project import image as image
from test_project import ready_store as ready_store


def context():
    return {
        "goal": "A serviceable enclosure",
        "constraints": ["Keep the mounting pattern"],
        "excerpts": [{"title": "Service manual", "locator": "p. 12", "text": "Clearance 8 mm"}],
    }


def command(job, **changes):
    return {
        "request_id": "request-1",
        "context_revision": job["context_revision"],
        "revision": job["revision"],
        "target": {"kind": "project"},
        "text": "  Make room for a cable.\nKeep the original mounts.  ",
        **changes,
    }


def test_brief_is_immutable_evidence_without_a_build(tmp_path):
    store = ProjectStore(tmp_path)
    text = "  Cover for a sensor.\nNo dimensions yet.  "
    job = store.create_brief(text, "Sensor cover")
    source = store.job_directory(job["id"]) / "input.txt"
    assert source.read_bytes() == text.encode()
    assert job["input"]["sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert job["input"]["kind"] == "brief"
    assert job["context"] == ProjectContext(goal=text).model_dump()
    assert job["document"] is None
    assert job["state"] == "needs_evidence"
    assert store.rebuild(job["id"], 1) == job
    assert not (source.parent / "revisions").exists()
    updated = store.update_context(job["id"], 0, context())
    assert source.read_bytes() == text.encode()
    assert ProjectStore(tmp_path).get(job["id"]) == updated


def test_context_uses_fresh_store_and_preserves_geometry_pmi_and_bundle(ready_store):
    store, job = ready_store
    step = store.artifact(job["id"], "assembly.step")
    (step.parent / "assembly-pmi.step").write_text("PMI")
    job = store.update_intent(job["id"], job["revision"], {"artifacts": ["assembly-pmi.step"]})
    original = deepcopy(job)
    other = ProjectStore(store.root)
    updated = store.update_context(job["id"], 0, context())
    assert updated["context_revision"] == 1
    for key in (
        "revision",
        "state",
        "document",
        "artifacts",
        "validation",
        "intent",
        "input",
        "artifact_directory",
    ):
        assert updated[key] == original[key]
    with pytest.raises(RevisionConflict, match="Context revision"):
        other.update_context(job["id"], 0, ProjectContext(goal="Stale"))
    with zipfile.ZipFile(store.bundle(job["id"])) as bundle:
        assert json.loads(bundle.read("manifest.json"))["context"] == context()
        assert bundle.read("assembly-pmi.step") == b"PMI"
    assert other.get(job["id"]) == updated


def test_capture_freezes_context_derives_scope_and_retries_after_both_revisions(ready_store):
    store, job = ready_store
    document = measured_document().model_dump()
    document["occurrences"].append({"id": "second", "definition_id": "plate"})
    job = store.set_design(job["id"], job["revision"], document)
    job = store.update_context(job["id"], 0, context())
    body = command(job, target={"kind": "occurrence", "occurrence_id": "base"})
    result = store.capture_change_request(job["id"], body)
    captured = result["request"]
    assert captured["target"] == {
        "kind": "occurrence",
        "occurrence_id": "base",
        "definition_id": "plate",
        "affected_occurrence_ids": ["base", "second"],
    }
    assert captured["step_sha256"] == job["artifacts"]["assembly.step"]["sha256"]
    assert captured["text"] == body["text"]
    assert captured["execution"] == "pending"
    assert result["job"]["revision"] == job["revision"]
    assert result["job"]["context_revision"] == job["context_revision"]
    store.update_context(job["id"], 1, ProjectContext(goal="Later"))
    store.edit(job["id"], job["revision"], "plate", {"length": 48}, defer_build=True)
    retry = ProjectStore(store.root).capture_change_request(job["id"], body)
    assert retry["request"] == captured
    assert retry["request"]["context"] == context()
    assert len(retry["job"]["change_requests"]) == 1
    with pytest.raises(RevisionConflict, match="different command"):
        store.capture_change_request(job["id"], {**body, "text": "Different"})
    with pytest.raises(RevisionConflict):
        store.capture_change_request(job["id"], {**body, "request_id": "new"})


def test_capture_rejects_stale_geometry_context_and_invalid_scope(ready_store):
    store, job = ready_store
    for changes, error in [
        ({"revision": job["revision"] - 1}, RevisionConflict),
        ({"context_revision": 1}, RevisionConflict),
        ({"target": {"kind": "occurrence", "occurrence_id": "missing"}}, ValueError),
        (
            {"target": {"kind": "occurrence", "occurrence_id": "base", "definition_id": "plate"}},
            ValueError,
        ),
        ({"target": {"kind": "body", "body_id": "base"}}, ValueError),
        ({"revision": True}, ValueError),
        ({"context_revision": "0"}, ValueError),
    ]:
        with pytest.raises(error):
            store.capture_change_request(job["id"], command(job, **changes))
    assert store.get(job["id"]) == job


def test_context_and_capture_survive_inflight_build_publication(ready_store, geometry_stub):
    store, job = ready_store
    started, finish = threading.Event(), threading.Event()

    def delayed(document, directory, reference_mesh=None):
        started.set()
        assert finish.wait(5)
        return controlled_build(document, directory, reference_mesh)

    geometry_stub.build_assembly = delayed
    worker = threading.Thread(target=store.rebuild, args=(job["id"], job["revision"]))
    worker.start()
    try:
        assert started.wait(5)
        other = ProjectStore(store.root)
        saved = other.update_context(job["id"], 0, context())
        captured = other.capture_change_request(job["id"], command(saved))
    finally:
        finish.set()
        worker.join(5)
    assert not worker.is_alive()
    final = store.get(job["id"])
    assert final["state"] == "ready"
    assert final["context"] == context()
    assert final["context_revision"] == 1
    assert final["change_requests"] == captured["job"]["change_requests"]


def test_legacy_defaults_do_not_rewrite_geometry_or_manifest(ready_store):
    store, job = ready_store
    path = store.job_directory(job["id"]) / "manifest.json"
    for key in ("context_revision", "context", "change_requests"):
        job.pop(key)
    path.write_text(json.dumps(job))
    original = path.read_bytes()
    loaded = store.get(job["id"])
    assert loaded["context_revision"] == 0
    assert loaded["context"] == ProjectContext().model_dump()
    assert loaded["change_requests"] == []
    assert loaded["artifacts"] == job["artifacts"]
    assert path.read_bytes() == original


@pytest.mark.parametrize("bad", [True, 3, "", "  ", "x" * 20_001])
def test_brief_validation_is_strict_and_bounded(tmp_path, bad):
    store = ProjectStore(tmp_path)
    with pytest.raises(ValueError):
        store.create_brief(bad)
    assert store.list() == []


def test_http_mcp_share_validation_persistence_and_conflicts(tmp_path):
    store = ProjectStore(tmp_path)
    mcp = create_mcp(store)

    def call(method, path, payload=None):
        result = asyncio.run(
            mcp.call_tool("workspace_request", {"method": method, "path": path, "payload": payload})
        )
        return result[1]

    with TestClient(
        create_app(store), base_url="http://127.0.0.1", client=("127.0.0.1", 55000)
    ) as client:
        response = client.post("/api/briefs", json={"text": "Sensor cover", "name": "Cover"})
        assert response.status_code == 201
        job = response.json()
        path = f"/api/jobs/{job['id']}"
        assert call("GET", path) == job
        saved = call("PATCH", path + "/context", {"context_revision": 0, "context": context()})
        assert client.get(path).json() == saved
        assert (
            client.patch(
                path + "/context", json={"context_revision": 0, "context": context()}
            ).status_code
            == 409
        )
        captured = client.post(path + "/change-requests", json=command(saved))
        assert captured.status_code == 201
        assert call("POST", path + "/change-requests", command(saved)) == captured.json()
        assert client.get(path).json()["change_requests"][0]["execution"] == "pending"
        for payload in [
            {"context_revision": True, "context": context()},
            {"context_revision": 1, "context": {**context(), "constraints": [1]}},
            {
                "context_revision": 1,
                "context": {**context(), "excerpts": [{"title": "No citation"}]},
            },
            {
                "context_revision": 1,
                "context": {**context(), "excerpts": context()["excerpts"] * 21},
            },
        ]:
            assert client.patch(path + "/context", json=payload).status_code == 422
            with pytest.raises(ToolError, match="validation"):
                call("PATCH", path + "/context", payload)
        from_mcp = call("POST", "/api/briefs", {"text": "New project"})
        assert client.get(f"/api/jobs/{from_mcp['id']}").json() == from_mcp
