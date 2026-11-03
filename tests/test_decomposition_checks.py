import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from open_assembly.cli import main
from open_assembly.decomposition import DecompositionStore
from open_assembly.decomposition_checks import check_action, reconcile_checks
from open_assembly.decomposition_workflow import DecompositionWorkflow
from open_assembly.project import ProjectStore, RevisionConflict
from open_assembly.server import create_app

CASE = Path(__file__).resolve().parents[1] / "examples/decomposition/worktable"


@pytest.fixture
def workspace(tmp_path):
    store = DecompositionStore(tmp_path)
    project = store.create(
        (CASE / "reference.png").read_bytes(),
        "Check fixture",
        "Original repository MIT fixture",
        description="A proposed table from a dimensioned drawing.",
        workflow=True,
    )
    manager = DecompositionWorkflow(store)
    project = manager.mutate(
        project["id"],
        "proposal",
        {
            "revision": 0,
            "workflow_revision": 0,
            "proposal": {
                "summary": "One top and four separate square legs.",
                "parts": [
                    {"id": "table", "label": "Table", "description": "Proposed physical parts."}
                ],
            },
        },
    )
    project = manager.mutate(
        project["id"],
        "approve-proposal",
        {
            "revision": 0,
            "workflow_revision": project["workflow_revision"],
            "proposal_digest": project["workflow"]["proposal"]["digest"],
        },
    )
    project = store.update(
        project["id"],
        {
            "revision": 0,
            "workflow_revision": project["workflow_revision"],
            "plan": json.loads((CASE / "plan.json").read_text()),
        },
    )
    return store, project["id"]


def payload(project, node="top", **extra):
    return {
        "revision": project["revision"],
        "workflow_revision": project["workflow_revision"],
        "node_id": node,
        "review_digest": project["workflow"]["scopes"][node]["review_digest"],
        **extra,
    }


def action(workspace, name="check", node="top", **extra):
    store, project_id = workspace
    return check_action(store, project_id, name, payload(store.get(project_id), node, **extra))


def range_rule(**extra):
    return {
        "kind": "parameter_range",
        "id": "top-width",
        "address": "shape/top-definition/top-box/dimensions/0",
        "max": 410,
        "unit": "mm",
        "quote": "Keep the top within 410 mm.",
        **extra,
    }


def report(project, node="top"):
    return project["workflow"]["checks"][node]["report"]


def test_structural_checks_do_not_claim_intent_or_create_approval(workspace):
    store, project_id = workspace
    before = store.get(project_id)
    after = action(workspace)
    checked = report(after)
    assert checked["outcome"] == "pass" and checked["ci_exit_code"] == 0
    outcomes = {item["kind"]: item["outcome"] for item in checked["results"]}
    assert outcomes["source_program_integrity"] == outcomes["mesh_integrity"] == "pass"
    assert (
        outcomes["native_readback"]
        == outcomes["user_intent"]
        == outcomes["manufacturing"]
        == "unchecked"
    )
    assert (
        checked["binding"]["review_digest"] == before["workflow"]["scopes"]["top"]["review_digest"]
    )
    assert after["revision"] == before["revision"]
    assert after["workflow_revision"] == before["workflow_revision"] + 1
    for key in ["approvals", "approval_history", "cad", "parts"]:
        assert before["workflow"][key] == after["workflow"][key]


def test_literal_context_limits_fail_and_history_is_bound(workspace):
    text = "  Keep the top within 410 mm.\nThe surface is a separate piece.  "
    saved = action(workspace, "check-context", text=text, rules=[range_rule()])
    entry = saved["workflow"]["checks"]["top"]
    assert entry["context"] == {"text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()}
    first = action(workspace)
    assert report(first)["outcome"] == "pass"
    measured = next(item for item in report(first)["results"] if item["id"] == "top-width")
    assert measured["actual"] == 400 and measured["unit"] == "mm"
    updated = action(
        workspace,
        "check-context",
        text="Keep the top within 399 mm.",
        rules=[range_rule(max=399, quote="Keep the top within 399 mm.")],
    )
    assert report(updated)["status"] == "stale"
    second = action(workspace)
    assert report(second)["outcome"] == "fail" and report(second)["ci_exit_code"] == 1
    assert second["workflow"]["checks"]["top"]["history"][-1]["id"] == report(first)["id"]
    assert (
        report(second)["binding"]["criteria_digest"] != report(first)["binding"]["criteria_digest"]
    )


def test_manual_requirement_stays_blocked_without_evidence(workspace):
    text = "Check that the finish matches the reference photograph."
    action(
        workspace,
        "check-context",
        text=text,
        rules=[
            {
                "kind": "manual",
                "id": "finish",
                "description": "Compare surface finish with the authorized photograph.",
                "quote": text,
            }
        ],
    )
    current = report(action(workspace))
    assert current["outcome"] == "blocked" and current["ci_exit_code"] == 2
    assert (
        next(item for item in current["results"] if item["id"] == "finish")["outcome"] == "blocked"
    )


def test_native_receipt_change_stales_a_check_without_a_concept_edit(workspace):
    checked = action(workspace)
    old = copy.deepcopy(report(checked))
    assert old["binding"]["native_build_ids"] == {"top": None}
    next(part for part in checked["workflow"]["parts"] if part["node_id"] == "top")[
        "cad_build_id"
    ] = "a" * 32
    reconcile_checks(checked)
    assert report(checked)["status"] == "stale"
    assert checked["revision"] == old["binding"]["revision"]


@pytest.mark.parametrize(
    "rule",
    [
        range_rule(quote="A sentence the user never supplied."),
        range_rule(address="shape/leg-definition/leg-box/dimensions/0"),
        range_rule(min=420, max=410),
        range_rule(max=True),
        range_rule(max=float("inf")),
        range_rule(id="source-program"),
    ],
)
def test_context_refuses_unquoted_invalid_or_out_of_scope_criteria(workspace, rule):
    store, project_id = workspace
    before = store.get(project_id)
    with pytest.raises(ValueError):
        action(workspace, "check-context", text="Keep the top within 410 mm.", rules=[rule])
    assert store.get(project_id) == before


def test_shared_definition_is_readable_without_checking_other_occurrences(workspace):
    rule = range_rule(
        id="leg-width",
        address="shape/leg-definition/leg-box/dimensions/0",
        max=30,
        quote="Leg width must not exceed 30 mm.",
    )
    action(workspace, "check-context", node="leg-front-left", text=rule["quote"], rules=[rule])
    checked = report(action(workspace, node="leg-front-left"), "leg-front-left")
    mesh = next(item for item in checked["results"] if item["kind"] == "mesh_integrity")
    assert mesh["part_ids"] == ["leg-front-left"]
    assert checked["outcome"] == "pass"
    with pytest.raises(ValueError, match="selected physical scope"):
        action(
            workspace,
            "check-context",
            node="leg-front-left",
            text="Keep the top within 410 mm.",
            rules=[range_rule()],
        )


def test_geometry_edit_stales_reports_and_rejects_old_revision(workspace):
    store, project_id = workspace
    checked = action(workspace)
    old_command = payload(checked)
    plan = copy.deepcopy(checked["plan"])
    plan["definitions"][0]["shapes"][0]["dimensions"][0] += 5
    changed = store.update(
        project_id,
        {
            "revision": checked["revision"],
            "workflow_revision": checked["workflow_revision"],
            "plan": plan,
        },
    )
    assert report(changed)["status"] == "stale"
    with pytest.raises(RevisionConflict):
        check_action(store, project_id, "check", old_command)
    fresh = action(workspace)
    assert report(fresh)["status"] == "current"
    assert (
        report(fresh)["binding"]["program_sha256"] != report(checked)["binding"]["program_sha256"]
    )


def test_metric_requirement_is_blocked_for_relative_geometry(workspace):
    store, project_id = workspace
    current = store.get(project_id)
    plan = copy.deepcopy(current["plan"])
    plan["units"] = "relative"
    store.update(
        project_id,
        {
            "revision": current["revision"],
            "workflow_revision": current["workflow_revision"],
            "plan": plan,
        },
    )
    action(workspace, "check-context", text="Keep the top within 410 mm.", rules=[range_rule()])
    checked = report(action(workspace))
    assert checked["outcome"] == "blocked"
    item = next(item for item in checked["results"] if item["id"] == "top-width")
    assert item["unit"] == "relative" and item["expected_unit"] == "mm"


def test_retained_source_and_context_tamper_do_not_pass(workspace):
    store, project_id = workspace
    (store.directory(project_id) / "source.bin").write_bytes(b"changed source")
    checked = report(action(workspace))
    assert checked["outcome"] == "fail"
    manifest = store.get(project_id)
    manifest["workflow"]["checks"]["top"]["context"]["text"] = "Changed without a new digest"
    (store.directory(project_id) / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="recorded digest"):
        action(workspace)


def test_http_and_cli_share_saved_rules_and_ci_exit_codes(workspace, tmp_path, monkeypatch, capsys):
    store, project_id = workspace
    client = TestClient(
        create_app(ProjectStore(tmp_path)), base_url="http://127.0.0.1", client=("127.0.0.1", 50000)
    )
    current = store.get(project_id)
    path = f"/api/decompositions/{project_id}/workflow/"
    saved = client.post(
        path + "check-context",
        json=payload(current, text="Keep the top within 410 mm.", rules=[range_rule()]),
    )
    assert saved.status_code == 200
    checked = client.post(path + "check", json=payload(saved.json()))
    assert checked.status_code == 200 and report(checked.json())["outcome"] == "pass"
    output = tmp_path / "ci/report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "open-skyfall",
            "--workspace",
            str(tmp_path),
            "check-parts",
            project_id,
            "--node",
            "top",
            "--out",
            str(output),
        ],
    )
    main()
    assert json.loads(output.read_text())["ci_exit_code"] == 0
    assert json.loads(capsys.readouterr().out)["outcome"] == "pass"
    action(
        workspace,
        "check-context",
        text="Keep the top within 399 mm.",
        rules=[range_rule(max=399, quote="Keep the top within 399 mm.")],
    )
    with pytest.raises(SystemExit) as failure:
        main()
    assert failure.value.code == 1
    assert json.loads(output.read_text())["outcome"] == "fail"
    capsys.readouterr()
    action(
        workspace,
        "check-context",
        text="Review finish.",
        rules=[
            {
                "kind": "manual",
                "id": "finish",
                "description": "Requires a real finish comparison.",
                "quote": "Review finish.",
            }
        ],
    )
    with pytest.raises(SystemExit) as blocked:
        main()
    assert blocked.value.code == 2
    assert json.loads(output.read_text())["outcome"] == "blocked"
