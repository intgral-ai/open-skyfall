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
import zipfile
from pathlib import Path
from urllib.parse import urlsplit


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def exercise(base, output):
    parts = urlsplit(base)
    try:
        local = parts.hostname == "localhost" or ipaddress.ip_address(parts.hostname).is_loopback
    except ValueError:
        local = False
    if (
        not local
        or parts.scheme != "http"
        or parts.path not in {"", "/"}
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        raise ValueError("Use an owned loopback HTTP service")
    base = base.rstrip("/")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Evidence directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    events = []

    def request(method, path, payload=None, expected=200, binary=None):
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(
            base + path, data, {"Content-Type": "application/json"}, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as response:
            status, raw = response.code, response.read()
        event = {
            "method": method,
            "path": path,
            "status": status,
            "response_sha256": hashlib.sha256(raw).hexdigest(),
        }
        if data is not None:
            event["request_sha256"] = hashlib.sha256(data).hexdigest()
        events.append(event)
        write_json(output / "http-transcript.json", events)
        if status != expected:
            raise ValueError(
                f"{method} {path} returned {status}, expected {expected}: {raw[:500]!r}"
            )
        if binary:
            (output / binary).write_bytes(raw)
            return raw
        value = json.loads(raw)
        write_json(output / f"response-{len(events):02}.json", value)
        return value

    def replay(bundle, name, expected=0, error_text=None):
        command = [
            sys.executable,
            "-c",
            "from open_assembly.cli import main; main()",
            "replay",
            str(bundle),
            "--out",
            str(output / name),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        (output / f"{name}.stdout.log").write_text(result.stdout)
        (output / f"{name}.stderr.log").write_text(result.stderr)
        if result.returncode != expected or (error_text and error_text not in result.stderr):
            raise ValueError(f"Replay returned {result.returncode}: {result.stderr}")
        return json.loads(result.stdout) if expected == 0 else None

    health = request("GET", "/health")
    if health.get("service") != "open-assembly-cad":
        raise ValueError("Unexpected service identity")
    request("GET", "/api/decomposition-schema")
    case = Path(__file__).resolve().parents[1] / "examples/decomposition/worktable"
    image = (case / "reference.png").read_bytes()
    plan = json.loads((case / "plan.json").read_text())
    if hashlib.sha256(image).hexdigest() != plan["source_sha256"]:
        raise ValueError("The authored plan does not belong to this reference image")
    project = request(
        "POST",
        "/api/decompositions",
        {
            "name": "Explainable worktable",
            "rights": "Original MIT reference illustration",
            "data_base64": base64.b64encode(image).decode(),
        },
        expected=201,
    )
    path = f"/api/decompositions/{project['id']}"
    first = request("PUT", path + "/plan", {"revision": 0, "plan": plan})
    write_json(output / "accepted-r1.json", first)
    preview = request("GET", path + "/artifacts/" + first["preview"])
    if len(preview["parts"]) != 5 or first["analysis"]["coverage"]["status"] != "complete":
        raise ValueError("Worktable did not produce five explained parts")
    by_id = {part["id"]: part for part in preview["parts"]}
    if by_id["top"]["bounds"] != [[-200, -150, 430], [200, 150, 450]]:
        raise ValueError("Top geometry disagrees with the dimensioned reference")
    for name, x, y in [
        ("leg-front-left", -170, -120),
        ("leg-front-right", 170, -120),
        ("leg-back-left", -170, 120),
        ("leg-back-right", 170, 120),
    ]:
        if by_id[name]["bounds"] != [[x - 15, y - 15, 0], [x + 15, y + 15, 430]]:
            raise ValueError(f"{name} geometry disagrees with the dimensioned reference")
    original = request("GET", path + "/revisions/1/bundle", binary="revision-1.zip")
    first_replay = replay(output / "revision-1.zip", "replay-r1")

    changed = copy.deepcopy(plan)
    changed["definitions"][0]["shapes"][0]["dimensions"][0] = 420
    next(node for node in changed["nodes"] if node["id"] == "top")["note"] = (
        "Top width is 420 mm for this E2E correction. The source still states 400 mm; depth, thickness and leg placement stay unchanged."
    )
    changed["explanation"]["bases"]["requested-width"] = {
        "kind": "assumed",
        "observations": ["top-size"],
        "why": "This E2E correction requests width 420 mm. The source still states 400 mm; leg geometry and placements stay fixed.",
    }
    changed["explanation"]["parameters"]["shape/top-definition/top-box/dimensions/0"] = (
        "requested-width"
    )
    second = request("PUT", path + "/plan", {"revision": 1, "plan": changed})
    write_json(output / "accepted-r2.json", second)
    second_preview = request("GET", path + "/artifacts/" + second["preview"])
    after = {part["id"]: part for part in second_preview["parts"]}
    if after.keys() != by_id.keys() or any(
        after[id] != value for id, value in by_id.items() if id != "top"
    ):
        raise ValueError("A top-only correction changed another part")
    if after["top"]["bounds"] != [[-210, -150, 430], [210, 150, 450]]:
        raise ValueError("The requested width did not reach actual top geometry")
    request("PUT", path + "/plan", {"revision": 1, "plan": changed}, expected=409)
    missing = copy.deepcopy(changed)
    missing["explanation"]["parameters"].pop("node/top/position/0")
    request("PUT", path + "/plan", {"revision": 2, "plan": missing}, expected=422)
    wrong_source = copy.deepcopy(changed)
    wrong_source["source_sha256"] = "0" * 64
    request("PUT", path + "/plan", {"revision": 2, "plan": wrong_source}, expected=422)
    current = request("GET", path)
    if current["revision"] != 2 or current["source"]["sha256"] != first["source"]["sha256"]:
        raise ValueError("A rejected proposal changed the accepted source or revision")
    historical = request("GET", path + "/revisions/1")
    if historical["analysis"]["binding"] != first["analysis"]["binding"]:
        raise ValueError("Historical program binding changed")
    again = request("GET", path + "/revisions/1/bundle", binary="revision-1-after-edit.zip")
    if again != original:
        raise ValueError("Historical bundle bytes changed after a later revision")
    replay(output / "revision-1-after-edit.zip", "replay-r1-after-edit")
    request("GET", path + "/bundle", binary="revision-2.zip")
    second_replay = replay(output / "revision-2.zip", "replay-r2")

    with zipfile.ZipFile(output / "revision-2.zip") as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    files["preview.json"] += b"tampered"
    with zipfile.ZipFile(output / "tampered.zip", "w") as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
    replay(output / "tampered.zip", "tamper-refusal", expected=2, error_text="integrity failed")
    for report, revision in [(first_replay, 1), (second_replay, 2)]:
        if report["outcome"] != "pass" or report["binding"]["revision"] != revision:
            raise ValueError("CLI replay did not prove its exact accepted revision")
    report = {
        "outcome": "pass",
        "scope": "authored-plan HTTP and CLI reproduction",
        "project_id": project["id"],
        "viewer_url": base + "/?project=" + project["id"],
        "source_sha256": plan["source_sha256"],
        "part_count": 5,
        "revisions": [first["analysis"]["binding"], second["analysis"]["binding"]],
        "preserved_leg_geometry": True,
        "history_byte_identity": True,
        "negative_controls": [
            "stale revision",
            "missing parameter basis",
            "wrong source image",
            "tampered preview",
        ],
        "browser": "not_run_by_this_script",
        "cold_agent_authoring": "requires_independent_forward_test",
        "source_fidelity_native_cad_manufacturing": "not_established",
    }
    write_json(output / "result.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Exercise the authored worktable plan through real HTTP and CLI replay operations."
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = exercise(args.base_url, args.out.resolve())
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"outcome": "fail", "error": str(exc)}), file=sys.stderr)
        raise SystemExit(2) from exc
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
