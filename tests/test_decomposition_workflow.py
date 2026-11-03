import copy
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from open_assembly.decomposition import DecompositionStore, replay_bundle
from open_assembly.decomposition_workflow import DecompositionWorkflow
from open_assembly.project import ProjectStore, RevisionConflict
from open_assembly.server import create_app

CASE = Path(__file__).resolve().parents[1] / "examples/decomposition/worktable"


@pytest.fixture
def workspace(tmp_path):
    store = DecompositionStore(tmp_path)
    project = store.create(
        (CASE / "reference.png").read_bytes(),
        "Review test",
        "Repository MIT fixture",
        description="Use the dimensioned drawing as a proposed side table.",
        workflow=True,
    )
    return store, project["id"]


def action(store, project_id, name, **payload):
    project = store.get(project_id)
    return DecompositionWorkflow(store).mutate(
        project_id,
        name,
        {
            "revision": project["revision"],
            "workflow_revision": project["workflow_revision"],
            **payload,
        },
    )


def propose(store, project_id):
    project = action(
        store,
        project_id,
        "proposal",
        proposal={
            "summary": "A top supported by four separate legs.",
            "parts": [
                {
                    "id": "table",
                    "label": "Side table",
                    "description": "Proposed separate physical parts.",
                }
            ],
        },
    )
    return action(
        store,
        project_id,
        "approve-proposal",
        proposal_digest=project["workflow"]["proposal"]["digest"],
    )


def accept(store, project_id):
    current = propose(store, project_id)
    return store.update(
        project_id,
        {
            "revision": 0,
            "workflow_revision": current["workflow_revision"],
            "plan": json.loads((CASE / "plan.json").read_text()),
        },
    )


def confirm(store, project_id, node_id="worktable"):
    current = store.get(project_id)
    return action(
        store,
        project_id,
        "approve",
        node_id=node_id,
        review_digest=current["workflow"]["scopes"][node_id]["review_digest"],
        confirmed=True,
    )


def test_proposal_acceptance_is_separate_from_part_confirmation(workspace):
    store, project_id = workspace
    current = store.get(project_id)
    assert current["workflow"]["phase"] == "input"
    assert current["plan"] is None
    with pytest.raises(ValueError, match="Confirm the proposal"):
        store.update(
            project_id,
            {
                "revision": 0,
                "workflow_revision": 0,
                "plan": json.loads((CASE / "plan.json").read_text()),
            },
        )
    current = accept(store, project_id)
    assert current["revision"] == 1
    assert current["workflow"]["phase"] == "review"
    assert not any(part["approved"] for part in current["workflow"]["parts"])
    with pytest.raises(ValueError, match="Confirm every selected part"):
        DecompositionWorkflow(store).build(
            project_id,
            {
                "revision": 1,
                "workflow_revision": current["workflow_revision"],
                "node_id": "worktable",
                "review_digest": current["workflow"]["scopes"]["worktable"]["review_digest"],
            },
        )


def test_literal_request_expands_shared_scope_and_invalidates_only_affected_parts(workspace):
    store, project_id = workspace
    initial = accept(store, project_id)
    confirmed = confirm(store, project_id)
    old_scope = confirmed["workflow"]["scopes"]["worktable"]["review_digest"]
    text = "Make the four square legs 35 mm wide. Keep the top and all leg centers unchanged."
    captured = action(
        store, project_id, "request", request_id="leg-width", node_id="leg-front-left", text=text
    )
    request = captured["workflow"]["requests"][0]
    assert request["text"] == text and len(request["part_ids"]) == 4
    assert request["program_sha256"] == initial["analysis"]["binding"]["program_sha256"]
    assert captured["workflow"]["approvals"].keys() == {"top"}
    retry = DecompositionWorkflow(store).mutate(
        project_id,
        "request",
        {
            "revision": 1,
            "workflow_revision": confirmed["workflow_revision"],
            "request_id": "leg-width",
            "node_id": "leg-front-left",
            "text": text,
        },
    )
    assert retry == captured
    with pytest.raises(ValueError, match="Resolve captured changes"):
        action(
            store,
            project_id,
            "approve",
            node_id="worktable",
            review_digest=old_scope,
            confirmed=True,
        )
    plan = copy.deepcopy(captured["plan"])
    leg = next(item for item in plan["definitions"] if item["id"] == "leg-definition")
    leg["shapes"][0]["dimensions"][0:2] = [35, 35]
    plan["explanation"]["bases"]["requested-leg-width"] = {
        "kind": "assumed",
        "observations": [],
        "why": text,
    }
    for axis in [0, 1]:
        plan["explanation"]["parameters"][f"shape/leg-definition/leg-box/dimensions/{axis}"] = (
            "requested-leg-width"
        )
    updated = store.update(
        project_id,
        {
            "revision": 1,
            "workflow_revision": captured["workflow_revision"],
            "request_id": "leg-width",
            "plan": plan,
        },
    )
    assert updated["workflow"]["requests"][0]["status"] == "applied"
    assert updated["workflow"]["approvals"].keys() == {"top"}
    assert store.revision(project_id, 1)["plan"] == initial["plan"]
    with pytest.raises(RevisionConflict):
        action(
            store,
            project_id,
            "approve",
            node_id="worktable",
            review_digest=old_scope,
            confirmed=True,
        )


def test_explicit_confirmation_and_workflow_revision_cannot_be_forged_by_plan_acceptance(workspace):
    store, project_id = workspace
    project = accept(store, project_id)
    digest = project["workflow"]["scopes"]["top"]["review_digest"]
    with pytest.raises(ValueError, match="Explicit user confirmation"):
        action(store, project_id, "approve", node_id="top", review_digest=digest, confirmed=False)
    with pytest.raises(ValueError):
        action(store, project_id, "approve", node_id="top", review_digest=digest, confirmed=1)
    confirm(store, project_id, "top")
    with pytest.raises(RevisionConflict, match="Workflow changed"):
        store.update(
            project_id,
            {
                "revision": 1,
                "workflow_revision": project["workflow_revision"],
                "plan": project["plan"],
            },
        )


def test_text_only_source_and_replay_preserve_literal_brief_without_fake_image(tmp_path):
    store = DecompositionStore(tmp_path)
    text = "Design a top 400 x 300 x 20 mm with four legs 30 x 30 x 430 mm."
    project = store.request(
        "POST",
        "/api/decompositions",
        {
            "name": "Text design",
            "description": text,
            "rights": "Synthetic test brief",
            "workflow": True,
        },
    )
    project_id = project["id"]
    assert project["source"]["kind"] == "text"
    assert not (store.directory(project_id) / "reference.png").exists()
    assert (store.directory(project_id) / "source.bin").read_text() == text
    with pytest.raises(FileNotFoundError, match="text brief"):
        store.reference(project_id)
    current = propose(store, project_id)
    plan = json.loads((CASE / "plan.json").read_text())
    plan["source_sha256"] = project["source"]["sha256"]
    plan["explanation"]["observations"] = [
        {
            "kind": "text",
            "id": obs["id"],
            "quote": text,
            "statement": "Design requirement; geometry is proposed, not image-observed.",
        }
        for obs in plan["explanation"]["observations"]
    ]
    for basis in plan["explanation"]["bases"].values():
        basis["kind"] = "assumed"
    accepted = store.update(
        project_id, {"revision": 0, "workflow_revision": current["workflow_revision"], "plan": plan}
    )
    report = replay_bundle(store.bundle(project_id), tmp_path / "text-replay")
    assert report["outcome"] == "pass"
    assert accepted["source"]["sha256"] == hashlib.sha256(text.encode()).hexdigest()
    plan["explanation"]["observations"][0]["quote"] = "This was not supplied."
    with pytest.raises(ValueError, match="literal quote"):
        store.update(
            project_id,
            {"revision": 1, "workflow_revision": accepted["workflow_revision"], "plan": plan},
        )


def _fake_native(plan, output, *, binding, node_ids):
    output.mkdir(parents=True)
    result = {
        "binding": binding,
        "step_structure": "flat_named_bodies",
        "checks": {gate: {"status": "PASS"} for gate in ["native_validity", "step_exchange"]},
        "step_path": "assembly.step",
        "preview_path": "native-preview.json",
        "report_path": "native-report.json",
    }
    files = {
        "assembly.step": b"unit publication test, not CAD evidence",
        "native-preview.json": b"{}",
        "native-report.json": b"{}",
        "assembly.json": b"{}",
    }
    for name, raw in files.items():
        (output / name).write_bytes(raw)
    result["artifacts"] = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    return result


def test_native_publication_rechecks_confirmation_and_keeps_old_revision_immutable(
    workspace, monkeypatch
):
    store, project_id = workspace
    accept(store, project_id)
    project = confirm(store, project_id)

    def changing_build(plan, output, **kwargs):
        action(
            store,
            project_id,
            "request",
            request_id="during-build",
            node_id="top",
            text="Change the width after reviewing this model.",
        )
        return _fake_native(plan, output, **kwargs)

    monkeypatch.setattr("open_assembly.decomposition_native.build_native", changing_build)
    command = {
        "revision": 1,
        "workflow_revision": project["workflow_revision"],
        "node_id": "worktable",
        "review_digest": project["workflow"]["scopes"]["worktable"]["review_digest"],
    }
    with pytest.raises(RevisionConflict, match="retained as stale"):
        DecompositionWorkflow(store).build(project_id, command)
    current = store.get(project_id)
    assert current["workflow"]["cad"]["assembly"] is None
    assert not current["workflow"]["cad"]["parts"]
    assert list(current["workflow"]["builds"].values())[0]["status"] == "stale"
    assert current["revision"] == 1


def test_native_downloads_verify_registered_bytes(workspace, monkeypatch):
    store, project_id = workspace
    accept(store, project_id)
    project = confirm(store, project_id)
    monkeypatch.setattr("open_assembly.decomposition_native.build_native", _fake_native)
    result = DecompositionWorkflow(store).build(
        project_id,
        {
            "revision": 1,
            "workflow_revision": project["workflow_revision"],
            "node_id": "worktable",
            "review_digest": project["workflow"]["scopes"]["worktable"]["review_digest"],
        },
    )
    build_id = result["workflow"]["cad"]["assembly"]
    assert build_id and all(
        part["cad_build_id"] == build_id for part in result["workflow"]["parts"]
    )
    path = DecompositionWorkflow(store).artifact(project_id, build_id, "assembly.step")
    path.write_text("changed")
    with pytest.raises(ValueError, match="integrity"):
        DecompositionWorkflow(store).artifact(project_id, build_id, "assembly.step")


def test_real_http_designed_example_requires_proposal_review_and_never_confirms_parts(tmp_path):
    with TestClient(
        create_app(ProjectStore(tmp_path)), base_url="http://127.0.0.1", client=("127.0.0.1", 50000)
    ) as client:
        blocked = client.get(
            "/api/decomposition-anatomy-example", headers={"Origin": "https://elsewhere.example"}
        )
        assert blocked.status_code == 403
        response = client.get("/api/decomposition-anatomy-example")
        assert response.status_code == 200
        project = response.json()
        assert project["plan"] is None and project["workflow"]["example_case"] == "inspection-rig"
        path = f"/api/decompositions/{project['id']}/workflow/"
        binding = {"revision": 0, "workflow_revision": project["workflow_revision"]}
        assert client.post(path + "decompose-example", json=binding).status_code == 422
        response = client.post(
            path + "approve-proposal",
            json={**binding, "proposal_digest": project["workflow"]["proposal"]["digest"]},
        )
        project = response.json()
        assert response.status_code == 200
        response = client.post(
            path + "decompose-example",
            json={"revision": 0, "workflow_revision": project["workflow_revision"]},
        )
        assert response.status_code == 200
        decomposed = response.json()
        assert len(decomposed["workflow"]["parts"]) == 50
        assert decomposed["analysis"]["coverage"]["parameter_count"] == 617
        assert not decomposed["workflow"]["approvals"]
        assert decomposed["workflow"]["cad"]["assembly"] is None
        assert len(client.get(f"/api/decompositions/{project['id']}").json()["plan"]["nodes"]) == 57


def test_intake_types_and_blank_inputs_are_rejected_without_creating_projects(tmp_path):
    store = DecompositionStore(tmp_path)
    for payload in [
        {"rights": "Own input"},
        {"rights": "Own input", "description": "  "},
        {"rights": "Own input", "description": "A fixture", "workflow": "yes"},
        {"rights": "Own input", "description": "A fixture", "python": "/untrusted"},
    ]:
        with pytest.raises(ValueError):
            store.request("POST", "/api/decompositions", payload)
    assert store.list() == []


def test_pending_shared_request_cannot_be_bypassed_by_renaming_occurrences(workspace):
    store, project_id = workspace
    accept(store, project_id)
    confirm(store, project_id)
    captured = action(
        store,
        project_id,
        "request",
        request_id="pending-leg",
        node_id="leg-front-left",
        text="Make the legs thicker.",
    )
    plan = copy.deepcopy(captured["plan"])
    old_id, new_id = "leg-front-left", "renamed-leg"
    next(node for node in plan["nodes"] if node["id"] == old_id)["id"] = new_id
    explanation = plan["explanation"]
    explanation["nodes"][new_id] = explanation["nodes"].pop(old_id)
    explanation["parameters"] = {
        key.replace(f"node/{old_id}/", f"node/{new_id}/"): value
        for key, value in explanation["parameters"].items()
    }
    with pytest.raises(ValueError, match="Preserve the IDs affected by pending requests"):
        store.update(
            project_id,
            {"revision": 1, "workflow_revision": captured["workflow_revision"], "plan": plan},
        )
    current = store.get(project_id)
    assert current == captured
    assert not current["workflow"]["scopes"]["worktable"]["can_build"]
