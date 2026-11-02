import asyncio
import hashlib
import json
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from mcp.server.fastmcp.exceptions import ToolError
from open_assembly import native
from open_assembly.document import NativeAssemblyDocument, parse_document
from open_assembly.intent import questions
from open_assembly.mcp import create_mcp
from open_assembly.native_worker import STAGES
from open_assembly.project import ArtifactUnavailable, ProjectStore, RevisionConflict
from open_assembly.server import create_app


def controlled_native(document, output, **_):
    height = document.definitions[0].parameters.hook_top
    validation = {
        "valid": True,
        "roundtrip_valid": True,
        "solid_count": 1,
        "backend": "smlibpy",
        "native": {"parameters": {"hook_top": height}},
    }
    (output / "assembly.step").write_text(f"Controlled lifecycle fixture {height}")
    shutil.copyfile(native.registered_source(), output / "source.py")
    (output / "document.json").write_text(document.model_dump_json())
    (output / "validation.json").write_text(json.dumps(validation))
    for name in (
        "preview.json",
        "final.smb",
        "parameters.json",
        "rebuild.py",
        "provenance.json",
        "NOTICE.txt",
        "construction.json",
        "native-report.json",
    ):
        (output / name).write_text("{}")
    (output / "checkpoints").mkdir()
    for index, stage in enumerate(STAGES):
        for suffix in ("json", "smb"):
            (output / f"checkpoints/{index + 1:02}-{stage}.{suffix}").write_text("{}")
    return {"validation": validation}


@pytest.fixture
def native_store(tmp_path, monkeypatch):
    monkeypatch.setattr(native, "native_cases", lambda: {"cases": [{"available": True}]})
    monkeypatch.setattr(native, "build_native", controlled_native)
    store = ProjectStore(tmp_path / "jobs")
    job = store.create_native_example({"case_id": "wiring-cover"})
    assert job["state"] == "ready", job["error"]
    return store, job


@pytest.fixture
def held_executor(monkeypatch):
    release = threading.Event()
    submissions = []

    class HeldExecutor(ThreadPoolExecutor):
        def submit(self, fn, /, *args, **kwargs):
            submissions.append((fn, args, kwargs))

            def run():
                assert release.wait(10), "Held dispatcher was not released"
                return fn(*args, **kwargs)

            return super().submit(run)

    executor = HeldExecutor(max_workers=2)
    monkeypatch.setattr("open_assembly.server.ThreadPoolExecutor", lambda **_: executor)
    monkeypatch.setattr("open_assembly.mcp.ThreadPoolExecutor", lambda **_: executor)
    try:
        yield submissions
    finally:
        release.set()
        executor.shutdown(wait=True, cancel_futures=True)


def capture(store, job, request_id="raise-hook"):
    return store.capture_change_request(
        job["id"],
        {
            "request_id": request_id,
            "revision": job["revision"],
            "context_revision": job["context_revision"],
            "target": {"kind": "occurrence", "occurrence_id": "wiring_cover_1"},
            "text": "Raise the hook to 6.55 mm; keep the rest of the existing cover.",
        },
    )["request"]


def test_native_document_is_explicit_and_bounded():
    document = native.native_document()
    assert isinstance(parse_document(document.model_dump()), NativeAssemblyDocument)
    assert "recipe" not in document.model_dump()["definitions"][0]
    for change in (
        {"source_sha256": "f" * 64},
        {"occurrences": []},
        {"schema_version": 1},
        {"backend": "arbitrary-module"},
    ):
        with pytest.raises(ValueError):
            parse_document({**document.model_dump(), **change})


def test_registered_input_bytes_match_the_evidence_identity(native_store):
    store, job = native_store
    source = store.job_directory(job["id"]) / job["input"]["filename"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == job["input"]["sha256"]
    assert job["input"]["sha256"] == job["document"]["source_sha256"]


@pytest.mark.parametrize(
    "height", [True, False, "6.55", None, float("nan"), float("inf"), 5.54, 6.56]
)
def test_parameter_boundary_rejects_coercion(native_store, height):
    store, job = native_store
    capture(store, job)
    before = store.get(job["id"])
    with pytest.raises(ValueError):
        store.native_edit(job["id"], {"request_id": "raise-hook", "hook_top": height})
    assert store.get(job["id"]) == before


def test_execution_is_idempotent_and_capture_stays_immutable(native_store):
    store, job = native_store
    saved = capture(store, job)
    command = {"request_id": saved["id"], "hook_top": 6.55}
    queued = store.native_edit(job["id"], command, defer_build=True)
    assert queued["revision"] == 1
    assert queued["document"]["definitions"][0]["parameters"]["hook_top"] == 5.55
    assert queued["executions"][-1]["output_revision"] == 2
    assert store.native_edit(job["id"], command, defer_build=True) == queued
    with pytest.raises(ArtifactUnavailable):
        store.artifact(job["id"], "assembly.step")
    edited = store.execute_native(job["id"], queued["build_id"])
    assert edited["revision"] == 2
    assert edited["executions"][-1]["status"] == "accepted"
    assert edited["executions"][-1]["status_version"] == 3
    assert edited["change_requests"] == [saved]
    assert (
        edited["executions"][-1]["output_step_sha256"]
        == edited["artifacts"]["assembly.step"]["sha256"]
    )
    store.update_context(job["id"], 0, {"goal": "Later requirements"})
    retried = store.native_edit(job["id"], command)
    assert len(retried["executions"]) == 2
    assert retried["executions"][-1] == edited["executions"][-1]
    with pytest.raises(RevisionConflict, match="different native proposal"):
        store.native_edit(job["id"], {**command, "hook_top": 6.0})


def test_admission_rejects_noop_unknown_keys_missing_capture_and_stale_context(native_store):
    store, job = native_store
    with pytest.raises(ValueError, match="Save a change request"):
        store.native_edit(job["id"], {"request_id": "missing", "hook_top": 6.55})
    capture(store, job)
    with pytest.raises(ValueError, match="must change"):
        store.native_edit(job["id"], {"request_id": "raise-hook", "hook_top": 5.55})
    with pytest.raises(ValueError):
        store.native_edit(
            job["id"], {"request_id": "raise-hook", "hook_top": 6.55, "source": "evil.py"}
        )
    store.update_context(job["id"], 0, {"goal": "New context"})
    with pytest.raises(RevisionConflict, match="Context revision"):
        store.native_edit(job["id"], {"request_id": "raise-hook", "hook_top": 6.55})


@pytest.mark.parametrize("mutation", ["context", "cancel", "geometry", "reservation", "step"])
def test_publication_rejects_changed_bindings(native_store, monkeypatch, mutation):
    store, job = native_store
    capture(store, job)
    started, release = threading.Event(), threading.Event()
    calls = []

    def blocking(document, output, **kwargs):
        calls.append(document)
        started.set()
        assert release.wait(5)
        return controlled_native(document, output, **kwargs)

    monkeypatch.setattr(native, "build_native", blocking)
    queued = store.native_edit(
        job["id"], {"request_id": "raise-hook", "hook_top": 6.55}, defer_build=True
    )
    thread = threading.Thread(target=store.execute_native, args=(job["id"], queued["build_id"]))
    thread.start()
    assert started.wait(5)
    assert store.execute_native(job["id"], queued["build_id"])["state"] == "building"
    if mutation == "context":
        updated = store.update_context(job["id"], 0, {"goal": "Newer context survives"})
        capture(store, updated, "later-capture")
    elif mutation == "cancel":
        store.cancel(job["id"])
    elif mutation == "step":
        step = store.job_directory(job["id"]) / job["artifact_directory"] / "assembly.step"
        step.write_bytes(b"x" * step.stat().st_size)
    else:
        with store._locked(job["id"]) as directory:
            current = store._read(directory)
            if mutation == "geometry":
                current["revision"] += 1
            else:
                current["build_id"] = "new-reservation"
            store._save(directory, current)
    release.set()
    thread.join(5)
    assert not thread.is_alive()
    current = store.get(job["id"])
    assert len(calls) == 1
    assert current["executions"][-1]["status"] == "stale"
    assert current["artifacts"] == job["artifacts"]
    assert current["document"] == job["document"]
    if mutation == "context":
        assert current["context"]["goal"] == "Newer context survives"
        assert [row["id"] for row in current["change_requests"]] == ["raise-hook", "later-capture"]
    if mutation == "reservation":
        assert current["build_id"] == "new-reservation"
    else:
        assert current["state"] == "ready"


@pytest.mark.parametrize("failure", ["exception", "validation", "missing-checkpoint", "source"])
def test_failed_run_preserves_accepted_geometry_and_requires_new_capture(
    native_store, monkeypatch, failure
):
    store, job = native_store
    saved = capture(store, job)
    count = []

    def failing(document, output, **kwargs):
        count.append(1)
        if failure == "exception":
            raise ValueError("Native kernel rejected the edit")
        result = controlled_native(document, output, **kwargs)
        if failure == "validation":
            result["validation"]["valid"] = False
        elif failure == "missing-checkpoint":
            (output / "checkpoints/10-pocket.smb").unlink()
        else:
            (output / "source.py").write_text("changed")
        return result

    monkeypatch.setattr(native, "build_native", failing)
    command = {"request_id": saved["id"], "hook_top": 6.55}
    failed = store.native_edit(job["id"], command)
    assert failed["state"] == "ready" and failed["revision"] == 1
    assert failed["executions"][-1]["status"] == "failed"
    assert failed["artifacts"] == job["artifacts"]
    assert failed["change_requests"] == [saved]
    assert store.native_edit(job["id"], command) == failed
    assert len(count) == 1
    monkeypatch.setattr(native, "build_native", controlled_native)
    capture(store, failed, "retry-with-new-capture")
    accepted = store.native_edit(job["id"], {**command, "request_id": "retry-with-new-capture"})
    assert accepted["revision"] == 2


def test_tampered_download_and_admission_are_rejected(native_store):
    store, job = native_store
    capture(store, job)
    step = store.artifact(job["id"], "assembly.step")
    content = step.read_bytes()
    step.write_bytes(b"x" * len(content))
    with pytest.raises(ArtifactUnavailable, match="changed"):
        store.artifact(job["id"], "assembly.step")
    with pytest.raises(ArtifactUnavailable, match="changed"):
        store.native_edit(job["id"], {"request_id": "raise-hook", "hook_top": 6.55})
    step.unlink()
    other = step.parent / "outside.step"
    other.write_bytes(content)
    step.symlink_to(other)
    with pytest.raises(ArtifactUnavailable, match="authorized"):
        store.artifact(job["id"], "assembly.step")
    with pytest.raises(ValueError, match="safe relative"):
        store.artifact(job["id"], "../assembly.step")


def test_native_documents_cannot_bypass_capture(native_store):
    store, job = native_store
    with pytest.raises(ValueError, match="native-examples"):
        store.create_document(job["document"])
    with pytest.raises(ValueError, match="captured native edit"):
        store.set_design(job["id"], 1, job["document"])
    with pytest.raises(ValueError, match="captured native edit"):
        store.edit(job["id"], 1, "wiring_cover", {"hook_top": 6.55})
    with pytest.raises(ValueError, match="legacy rebuild"):
        store.rebuild(job["id"], 1)
    with pytest.raises(ValueError, match="Factory intent"):
        questions(store, job["id"])
    assert store.get(job["id"]) == job


def test_missing_runtime_is_visible_and_creates_no_job(tmp_path, monkeypatch):
    monkeypatch.delenv("OPEN_ASSEMBLY_SMLIB_PYTHON", raising=False)
    store = ProjectStore(tmp_path)
    assert native.native_cases()["cases"][0]["available"] is False
    with pytest.raises(ValueError, match="OPEN_ASSEMBLY_SMLIB_PYTHON"):
        store.create_native_example({"case_id": "wiring-cover"})
    assert store.list() == []


def test_http_and_mcp_share_native_execution(native_store):
    store, job = native_store
    mcp = create_mcp(store)

    def call(method, path, payload=None):
        return asyncio.run(
            mcp.call_tool(
                "workspace_request",
                {
                    "method": method,
                    "path": path,
                    "payload": payload,
                },
            )
        )[1]

    with TestClient(
        create_app(store), base_url="http://127.0.0.1", client=("127.0.0.1", 55000)
    ) as client:
        path = f"/api/jobs/{job['id']}"
        saved = capture(store, job)
        command = {"request_id": saved["id"], "hook_top": 6.55}
        response = client.post(path + "/native-edits", json=command)
        assert response.status_code == 202
        for _ in range(100):
            current = call("GET", path)
            if current["state"] == "ready":
                break
            time.sleep(0.01)
        assert current["revision"] == 2
        assert call("POST", path + "/native-edits", command) == current
        assert client.get(path).json() == current
        downloaded = client.get(path + "/artifacts/assembly.step")
        assert (
            hashlib.sha256(downloaded.content).hexdigest()
            == current["artifacts"]["assembly.step"]["sha256"]
        )
        bad = {**command, "hook_top": "6.55"}
        assert client.post(path + "/native-edits", json=bad).status_code == 422
        with pytest.raises(ToolError, match="validation"):
            call("POST", path + "/native-edits", bad)
        injected = {**command, "admit": None}
        assert client.post(path + "/native-edits", json=injected).status_code == 422
        with pytest.raises(ToolError, match="validation"):
            call("POST", path + "/native-edits", injected)
        assert client.post(path + "/rebuild", json={"revision": 2}).status_code == 422
        with pytest.raises(ToolError, match="legacy rebuild"):
            call("POST", path + "/rebuild", {"revision": 2})
        assert (
            client.post(path + "/native-edits", json={**command, "hook_top": 6.0}).status_code
            == 409
        )


def test_http_queued_retries_preserve_build_capacity(native_store, held_executor):
    store, job = native_store
    saved = capture(store, job)
    command = {"request_id": saved["id"], "hook_top": 6.55}
    with TestClient(
        create_app(store), base_url="http://127.0.0.1", client=("127.0.0.1", 55000)
    ) as client:
        path = f"/api/jobs/{job['id']}/native-edits"
        responses = [client.post(path, json=command) for _ in range(20)]
        assert [response.status_code for response in responses] == [202] * 20
        assert all(response.json() == responses[0].json() for response in responses)
        assert len(held_executor) == 1
        for _ in range(15):
            assert (
                client.post("/api/native-examples", json={"case_id": "wiring-cover"}).status_code
                == 202
            )
        assert (
            client.post("/api/native-examples", json={"case_id": "wiring-cover"}).status_code == 503
        )
        assert len(held_executor) == 16


@pytest.mark.parametrize("outcome", ["accepted", "failed"])
def test_http_terminal_retry_and_conflict_bypass_full_queue(
    native_store, held_executor, monkeypatch, outcome
):
    store, job = native_store
    saved = capture(store, job)
    command = {"request_id": saved["id"], "hook_top": 6.55}
    if outcome == "failed":

        def fail(document, output, **kwargs):
            raise ValueError("Native kernel rejected the edit")

        monkeypatch.setattr(native, "build_native", fail)
    terminal = store.native_edit(job["id"], command)
    assert terminal["executions"][-1]["status"] == outcome
    monkeypatch.setattr(native, "build_native", controlled_native)
    with TestClient(
        create_app(store), base_url="http://127.0.0.1", client=("127.0.0.1", 55000)
    ) as client:
        for _ in range(16):
            assert (
                client.post("/api/native-examples", json={"case_id": "wiring-cover"}).status_code
                == 202
            )
        path = f"/api/jobs/{job['id']}/native-edits"
        retry = client.post(path, json=command)
        assert retry.status_code == 202
        assert retry.json() == terminal
        assert client.post(path, json={**command, "hook_top": 6.0}).status_code == 409
        assert len(held_executor) == 16


def test_http_full_queue_leaves_new_native_capture_unadmitted(native_store, held_executor):
    store, job = native_store
    saved = capture(store, job)
    before = store.get(job["id"])
    with TestClient(
        create_app(store), base_url="http://127.0.0.1", client=("127.0.0.1", 55000)
    ) as client:
        for _ in range(16):
            assert (
                client.post("/api/native-examples", json={"case_id": "wiring-cover"}).status_code
                == 202
            )
        response = client.post(
            f"/api/jobs/{job['id']}/native-edits",
            json={"request_id": saved["id"], "hook_top": 6.55},
        )
        assert response.status_code == 503
        assert store.get(job["id"]) == before
        assert len(held_executor) == 16


def test_http_concurrent_native_retries_dispatch_once(native_store, held_executor):
    store, job = native_store
    saved = capture(store, job)
    command = {"request_id": saved["id"], "hook_top": 6.55}
    with TestClient(
        create_app(store), base_url="http://127.0.0.1", client=("127.0.0.1", 55000)
    ) as client:
        path = f"/api/jobs/{job['id']}/native-edits"
        with ThreadPoolExecutor(max_workers=8) as callers:
            responses = list(callers.map(lambda _: client.post(path, json=command), range(24)))
        assert [response.status_code for response in responses] == [202] * 24
        assert all(response.json() == responses[0].json() for response in responses)
        assert len(store.get(job["id"])["executions"]) == 2
        assert len(held_executor) == 1


def test_mcp_queued_native_retries_dispatch_once(native_store, held_executor):
    store, job = native_store
    saved = capture(store, job)
    mcp = create_mcp(store)

    async def retry():
        return await mcp.call_tool(
            "workspace_request",
            {
                "method": "POST",
                "path": f"/api/jobs/{job['id']}/native-edits",
                "payload": {"request_id": saved["id"], "hook_top": 6.55},
            },
        )

    responses = [asyncio.run(retry())[1] for _ in range(20)]
    assert responses[0]["state"] == "queued"
    assert all(response == responses[0] for response in responses)
    assert len(store.get(job["id"])["executions"]) == 2
    assert len(held_executor) == 1
