import importlib
import sys
import threading
import time
import types

import pytest
from fastapi.testclient import TestClient
from open_assembly.project import ProjectStore
from open_assembly.server import create_app
from test_project import controlled_build, measured_document


@pytest.fixture
def client(tmp_path, monkeypatch):
    module = types.ModuleType("open_assembly.geometry")
    module.build_assembly = controlled_build
    monkeypatch.setitem(sys.modules, "open_assembly.geometry", module)
    app = create_app(ProjectStore(tmp_path / "projects"))
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 55000)) as client:
        yield client


def upload_image(client):
    response = client.post(
        "/api/jobs", files={"file": ("reference.png", b"\x89PNG\r\n\x1a\nreference", "image/png")}
    )
    assert response.status_code == 202, response.text
    return response.json()


def wait_ready(client, job_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        job = response.json()
        if job["state"] not in {"queued", "building"}:
            assert job["state"] == "ready", job
            return job
        time.sleep(0.01)
    pytest.fail("Background build did not finish")


def design_image(client):
    job = upload_image(client)
    response = client.post(
        f"/api/jobs/{job['id']}/design",
        json={
            "revision": job["revision"],
            "document": measured_document().model_dump(),
        },
    )
    assert response.status_code == 202, response.text
    return wait_ready(client, job["id"])


def test_health_root_and_real_project_list(client):
    assert client.get("/health").json()["status"] == "ok"
    assert "<title>CAD workspace</title>" in client.get("/").text
    assert client.get("/docs").status_code == 200
    assert client.get("/api/jobs").json() == []
    job = upload_image(client)
    assert job["name"] == "reference"
    assert job["state"] == "needs_evidence"
    assert client.get("/api/jobs").json()[0]["id"] == job["id"]


def test_actual_routes_publish_disk_artifacts_and_bundle(client):
    job = design_image(client)
    step = client.get(f"/api/jobs/{job['id']}/artifacts/assembly.step")
    assert step.status_code == 200
    assert step.content.startswith(b"STEP ")
    preview = client.get(f"/api/jobs/{job['id']}/artifacts/preview.json")
    assert preview.status_code == 200
    assert preview.json()["bounds"] == [[0, 0, 0], [40, 30, 5]]
    bundle = client.get(f"/api/jobs/{job['id']}/bundle")
    assert bundle.status_code == 200
    assert bundle.content.startswith(b"PK")
    assert step.headers["x-content-type-options"] == "nosniff"


def test_revision_conflict_and_request_validation(client):
    job = design_image(client)
    response = client.patch(
        f"/api/jobs/{job['id']}/parts/plate",
        json={
            "revision": job["revision"] - 1,
            "parameters": {"length": 80},
        },
    )
    assert response.status_code == 409
    response = client.patch(
        f"/api/jobs/{job['id']}/parts/plate",
        json={
            "revision": job["revision"],
            "parameters": {"height": -1},
        },
    )
    assert response.status_code == 422
    assert client.get(f"/api/jobs/{job['id']}").json()["revision"] == job["revision"]
    response = client.post(
        f"/api/jobs/{job['id']}/rebuild", json={"revision": str(job["revision"])}
    )
    assert response.status_code == 422


def test_unknown_units_and_invalid_uploads(client):
    response = client.post(
        "/api/jobs", files={"file": ("part.stl", b"solid missing scale", "model/stl")}
    )
    assert response.status_code == 202
    assert response.json()["state"] == "needs_evidence"
    response = client.post(
        "/api/jobs", data={"units": "m"}, files={"file": ("part.stl", b"solid", "model/stl")}
    )
    assert response.status_code == 422
    response = client.post(
        "/api/jobs", files={"file": ("execute.py", b"raise RuntimeError", "text/plain")}
    )
    assert response.status_code == 422
    response = client.post("/api/jobs", files={"file": ("fake.png", b"not an image", "image/png")})
    assert response.status_code == 422
    response = client.post(
        "/api/jobs", content=b"", headers={"content-length": str(32 * 1024 * 1024)}
    )
    assert response.status_code == 413


def test_missing_intent_engine_is_explicit(client, monkeypatch):
    job = design_image(client)
    original = importlib.import_module

    def without_intent(name, package=None):
        if name == "open_assembly.intent":
            raise ImportError("Specify unavailable")
        return original(name, package)

    monkeypatch.setattr(importlib, "import_module", without_intent)
    response = client.get(f"/api/jobs/{job['id']}/intent")
    assert response.status_code == 409
    assert "Specify" in response.json()["detail"]


def test_intent_routes_delegate_exact_request(client, monkeypatch):
    job = design_image(client)
    module = types.ModuleType("open_assembly.intent")
    module.questions = lambda store, job_id: {
        "revision": store.get(job_id)["revision"],
        "parts": [],
    }

    def write(
        store, job_id, revision, analysis_id, answers, confirmed=False, accept_defaults=False
    ):
        return {
            "revision": revision,
            "analysis_id": analysis_id,
            "answers": answers,
            "confirmed": confirmed,
            "accept_defaults": accept_defaults,
        }

    module.write_intent = write
    monkeypatch.setitem(sys.modules, "open_assembly.intent", module)
    assert client.get(f"/api/jobs/{job['id']}/intent").json()["revision"] == job["revision"]
    body = {
        "revision": job["revision"],
        "analysis_id": "real-analysis",
        "answers": {"0": {"fit": "H7"}},
        "confirmed": True,
        "accept_defaults": False,
    }
    response = client.post(f"/api/jobs/{job['id']}/intent", json=body)
    assert response.status_code == 200
    assert response.json() == body


@pytest.mark.parametrize(
    "headers",
    [
        {"host": "evil.example"},
        {"origin": "https://evil.example"},
        {"origin": "http://127.0.0.1.evil.example"},
        {"sec-fetch-site": "cross-site"},
    ],
)
def test_untrusted_mutation_is_rejected(client, headers):
    response = client.post(
        "/api/jobs",
        headers=headers,
        files={"file": ("reference.png", b"\x89PNG\r\n\x1a\nreference")},
    )
    assert response.status_code == 403
    assert client.get("/api/jobs").json() == []


def test_same_origin_browser_is_accepted(client):
    response = client.post(
        "/api/jobs",
        headers={"origin": "http://127.0.0.1"},
        files={"file": ("reference.png", b"\x89PNG\r\n\x1a\nreference")},
    )
    assert response.status_code == 202
    assert "access-control-allow-origin" not in response.headers


def test_remote_peer_cannot_mutate(tmp_path):
    app = create_app(ProjectStore(tmp_path / "projects"))
    with TestClient(app, base_url="http://localhost", client=("203.0.113.2", 50000)) as remote:
        response = remote.post(
            "/api/jobs", files={"file": ("reference.png", b"\x89PNG\r\n\x1a\nreference")}
        )
        assert response.status_code == 403


def test_build_returns_while_geometry_is_still_running(client, monkeypatch):
    job = upload_image(client)
    started, release = threading.Event(), threading.Event()
    module = sys.modules["open_assembly.geometry"]

    def slow(document, directory, reference_mesh=None):
        started.set()
        assert release.wait(5)
        return controlled_build(document, directory, reference_mesh)

    monkeypatch.setattr(module, "build_assembly", slow)
    try:
        response = client.post(
            f"/api/jobs/{job['id']}/design",
            json={
                "revision": job["revision"],
                "document": measured_document().model_dump(),
            },
        )
        assert response.status_code == 202
        assert started.wait(5)
        assert client.get("/health").status_code == 200
        building = client.get(f"/api/jobs/{job['id']}").json()
        assert building["state"] == "building"
        assert client.get(f"/api/jobs/{job['id']}/artifacts/assembly.step").status_code == 409
        cancelled = client.post(f"/api/jobs/{job['id']}/cancel").json()
        assert cancelled["state"] == "cancelled"
    finally:
        release.set()
