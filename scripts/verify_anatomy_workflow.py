import argparse
import base64
import copy
import hashlib
import ipaddress
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


def run(base, output):
    address = urlsplit(base)
    if (
        address.scheme != "http"
        or not ipaddress.ip_address(address.hostname).is_loopback
        or address.path
        or address.query
        or address.fragment
        or address.username
    ):
        raise ValueError("Use an owned loopback HTTP service")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Evidence directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    events = []

    def save(name, data):
        (output / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def request(method, path, payload=None, expected=200, filename=None):
        raw = None if payload is None else json.dumps(payload).encode()
        command = urllib.request.Request(
            base + path, raw, {"Content-Type": "application/json"}, method=method
        )
        try:
            with urllib.request.urlopen(command, timeout=600) as response:
                status, content = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, content = error.code, error.read()
        events.append(
            {
                "method": method,
                "path": path,
                "status": status,
                "request_sha256": hashlib.sha256(raw).hexdigest() if raw else None,
                "response_sha256": hashlib.sha256(content).hexdigest(),
            }
        )
        save("http-transcript.json", events)
        if status != expected:
            raise ValueError(
                f"{method} {path}: expected {expected}, received {status}: {content[:1000]!r}"
            )
        if filename:
            (output / filename).write_bytes(content)
            return content
        return json.loads(content)

    case = Path(__file__).resolve().parents[1] / "examples/decomposition/inspection-rig"
    image = (case / "reference.png").read_bytes()
    plan = json.loads((case / "plan.json").read_text())
    if plan["source_sha256"] != hashlib.sha256(image).hexdigest():
        raise ValueError("The designed example source and Plan disagree")
    project = request(
        "POST",
        "/api/decompositions",
        {
            "name": "Synthetic anatomy verification",
            "rights": "Original repository MIT fixture",
            "description": (case / "brief.txt").read_text(),
            "workflow": True,
            "data_base64": base64.b64encode(image).decode(),
        },
        expected=201,
    )
    path = f"/api/decompositions/{project['id']}"

    def action(name, **payload):
        current = request("GET", path)
        return request(
            "POST",
            path + "/workflow/" + name,
            {
                "revision": current["revision"],
                "workflow_revision": current["workflow_revision"],
                **payload,
            },
        )

    project = action("proposal", proposal=json.loads((case / "proposal.json").read_text()))
    request(
        "PUT",
        path + "/plan",
        {"revision": 0, "workflow_revision": project["workflow_revision"], "plan": plan},
        expected=422,
    )
    project = action("approve-proposal", proposal_digest=project["workflow"]["proposal"]["digest"])
    project = request(
        "PUT",
        path + "/plan",
        {"revision": 0, "workflow_revision": project["workflow_revision"], "plan": plan},
    )
    root = next(node["id"] for node in project["plan"]["nodes"] if node["parent_id"] is None)
    assert len(project["workflow"]["parts"]) == 50 and not project["workflow"]["approvals"]
    request(
        "POST",
        path + "/workflow/build",
        {
            "revision": 1,
            "workflow_revision": project["workflow_revision"],
            "node_id": root,
            "review_digest": project["workflow"]["scopes"][root]["review_digest"],
        },
        expected=422,
    )
    request("GET", path + "/revisions/1/bundle", filename="original-concept.zip")
    project = action(
        "approve",
        node_id=root,
        review_digest=project["workflow"]["scopes"][root]["review_digest"],
        confirmed=True,
    )
    save(
        "simulated-fixture-review.json",
        {
            "scope": root,
            "review_digest": project["workflow"]["scopes"][root]["review_digest"],
            "simulation": True,
            "human_or_factory_acceptance": False,
        },
    )
    original = copy.deepcopy(project)
    original_preview = request("GET", path + "/artifacts/" + project["preview"])
    for index, increment in enumerate([2, 1], start=1):
        text = f"Synthetic test correction {index}: increase only the coupon X size by {increment} mm; preserve all other parts and assembled poses."
        project = action(
            "request", request_id=f"coupon-change-{index}", node_id="test-coupon", text=text
        )
        assert project["workflow"]["requests"][-1]["text"] == text
        assert len(project["workflow"]["approvals"]) == 49
        revised = copy.deepcopy(project["plan"])
        definition = next(item for item in revised["definitions"] if item["id"] == "coupon")
        shape = definition["shapes"][0]
        shape["dimensions"][0] += increment
        basis_id = f"coupon-test-{index}"
        revised["explanation"]["bases"][basis_id] = {
            "kind": "assumed",
            "observations": [],
            "why": text,
        }
        revised["explanation"]["parameters"][f"shape/coupon/{shape['id']}/dimensions/0"] = basis_id
        project = request(
            "PUT",
            path + "/plan",
            {
                "revision": project["revision"],
                "workflow_revision": project["workflow_revision"],
                "request_id": f"coupon-change-{index}",
                "plan": revised,
            },
        )
        assert project["workflow"]["requests"][-1]["status"] == "applied"
        assert len(project["workflow"]["approvals"]) == 49
    assert original["source"] == project["source"]
    revised_preview = request("GET", path + "/artifacts/" + project["preview"])
    def unchanged(preview):
        return {part["id"]: part for part in preview["parts"] if part["id"] != "test-coupon"}
    assert unchanged(original_preview) == unchanged(revised_preview)
    project = action(
        "approve",
        node_id="test-coupon",
        review_digest=project["workflow"]["scopes"]["test-coupon"]["review_digest"],
        confirmed=True,
    )
    project = action(
        "build",
        node_id="test-coupon",
        review_digest=project["workflow"]["scopes"]["test-coupon"]["review_digest"],
    )
    assert (
        project["workflow"]["cad"]["parts"]["test-coupon"]
        and project["workflow"]["cad"]["assembly"] is None
    )
    project = action(
        "build", node_id=root, review_digest=project["workflow"]["scopes"][root]["review_digest"]
    )
    save("accepted-native-project.json", project)
    build_id = project["workflow"]["cad"]["assembly"]
    build = project["workflow"]["builds"][build_id]
    assert build["status"] == "ready" and len(build["occurrences"]) == 50
    assert len(build["definitions"]) == 26
    assert build["checks"]["native_validity"]["status"] == "PASS"
    assert build["checks"]["step_exchange"]["status"] == "PASS"
    artifacts = path + f"/workflow/builds/{build_id}/artifacts/"
    for name in [
        "assembly.step",
        "assembly.json",
        "native-report.json",
        "native-preview.json",
        "native-trace.json",
    ]:
        raw = request("GET", artifacts + name, filename=name)
        assert hashlib.sha256(raw).hexdigest() == build["artifacts"][name]
    replay = subprocess.run(
        [
            sys.executable,
            "-c",
            "from open_assembly.cli import main;main()",
            "replay",
            str(output / "original-concept.zip"),
            "--out",
            str(output / "original-replay"),
        ],
        capture_output=True,
        text=True,
    )
    (output / "replay.stdout.log").write_text(replay.stdout)
    (output / "replay.stderr.log").write_text(replay.stderr)
    assert replay.returncode == 0, replay.stderr
    from build123d import import_step

    imported = import_step(output / "assembly.step")
    assert imported.is_valid and len(imported.solids()) == 50
    independent = {
        "reader": "build123d/OCP read-only import",
        "valid": imported.is_valid,
        "solid_count": len(imported.solids()),
        "volume_mm3": imported.volume,
        "step_sha256": hashlib.sha256((output / "assembly.step").read_bytes()).hexdigest(),
    }
    expected_volume = sum(part["metrics"]["volume"] for part in build["occurrences"])
    assert abs(imported.volume - expected_volume) <= expected_volume * 1e-6
    save("independent-step-import.json", independent)
    result = {
        "outcome": "pass",
        "project_id": project["id"],
        "viewer_url": base + "/?project=" + project["id"],
        "source_sha256": project["source"]["sha256"],
        "part_count": 50,
        "unique_definitions": 26,
        "concept_revision": project["revision"],
        "literal_iterations": 2,
        "unchanged_parts_preserved": 49,
        "native_build_id": build_id,
        "native_kernel": build["runtime"]["smlibpy"],
        "step_structure": build["step_structure"],
        "independent_import": independent,
        "review_decisions": "simulated for the original designed test fixture only",
        "browser": "not_run_by_this_script",
        "host_delivery_source_fidelity_manufacturing": "not_established",
    }
    save("result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Exercise the original designed fixture through real staged APIs, native build, replay and independent STEP import. Review actions are simulated test data."
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--simulate-fixture-review", action="store_true", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.base_url.rstrip("/"), args.out), indent=2))
