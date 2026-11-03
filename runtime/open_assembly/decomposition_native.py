import hashlib
import json
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .decomposition import Plan, _json_bytes, pose_matrix
from .native import runtime_python

RUNNER = Path(__file__).parent / "native_resources" / "decomposition.py"
DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path, value):
    path.write_bytes(_json_bytes(value))


def _selection(plan, node_ids):
    nodes = {node.id: node for node in plan.nodes}
    requested = set(nodes) if node_ids is None else set(node_ids)
    if not requested or not requested <= nodes.keys():
        raise ValueError("Native selection must contain existing nodes")
    selected = []
    matrices = {}

    def world(node):
        if node.id not in matrices:
            local = pose_matrix(node)
            matrices[node.id] = world(nodes[node.parent_id]) @ local if node.parent_id else local
        return matrices[node.id]

    for node in plan.nodes:
        if node.definition_id is None:
            continue
        ancestor = node
        while ancestor.id not in requested and ancestor.parent_id:
            ancestor = nodes[ancestor.parent_id]
        if ancestor.id in requested:
            selected.append(
                {
                    **node.model_dump(mode="json"),
                    "world_transform": world(node).tolist(),
                }
            )
    if not selected:
        raise ValueError("Native selection contains no physical parts")
    return selected


def _validate_binding(plan, binding, occurrences):
    if not isinstance(binding, dict):
        raise ValueError("Native build requires an immutable source/revision/approval binding")
    binding_snapshot = json.loads(_json_bytes(binding))
    required = {
        "project_id",
        "revision",
        "source_sha256",
        "program_sha256",
        "plan_sha256",
        "brief_sha256",
        "review_digests",
        "scope_digest",
        "part_ids",
    }
    if not required <= binding_snapshot.keys():
        raise ValueError("Native binding lacks source, revision or approval identities")
    if (
        not isinstance(binding_snapshot["project_id"], str)
        or not binding_snapshot["project_id"].strip()
    ):
        raise ValueError("Native binding needs a project ID")
    if type(binding_snapshot["revision"]) is not int or binding_snapshot["revision"] < 1:
        raise ValueError("Native binding needs a positive concept revision")
    for key in ("source_sha256", "program_sha256", "plan_sha256", "scope_digest"):
        if not isinstance(binding_snapshot[key], str) or not DIGEST.fullmatch(
            binding_snapshot[key]
        ):
            raise ValueError(f"Native binding has an invalid {key}")
    brief = binding_snapshot["brief_sha256"]
    if brief is not None and (not isinstance(brief, str) or not DIGEST.fullmatch(brief)):
        raise ValueError("Native binding has an invalid brief_sha256")
    if binding_snapshot["source_sha256"] != plan.source_sha256:
        raise ValueError("Native binding and Plan reference different sources")
    if (
        binding_snapshot["plan_sha256"]
        != hashlib.sha256(_json_bytes(plan.model_dump(mode="json"))).hexdigest()
    ):
        raise ValueError("Native binding Plan hash mismatch")
    parts = binding_snapshot["part_ids"]
    actual = {item["id"] for item in occurrences}
    if (
        not isinstance(parts, list)
        or any(not isinstance(part, str) for part in parts)
        or len(parts) != len(set(parts))
        or set(parts) != actual
    ):
        raise ValueError("Native binding part_ids must match the exact selected physical parts")
    reviews = binding_snapshot["review_digests"]
    if (
        not isinstance(reviews, dict)
        or set(reviews) != actual
        or any(
            not isinstance(digest, str) or not DIGEST.fullmatch(digest)
            for digest in reviews.values()
        )
    ):
        raise ValueError("Native binding needs one exact review digest per selected part")
    return binding_snapshot


def _run(python, output, mode, definition_id=None):
    command = [
        str(python),
        "-I",
        "-B",
        str(output / "native-runner.py"),
        mode,
        str(output / "native-input.json"),
    ]
    if definition_id is not None:
        command.append(definition_id)
    stem = f"definitions/{definition_id}/process" if definition_id else "assembly-process"
    stdout = output / f"{stem}.stdout.log"
    stderr = output / f"{stem}.stderr.log"
    stdout.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic_ns()
    with stdout.open("wb") as out, stderr.open("wb") as err:
        try:
            result = subprocess.run(
                command, cwd=output, stdout=out, stderr=err, timeout=300, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ValueError(f"Native {mode} failed; diagnostics retained at {stderr}") from error
    if result.returncode:
        raise ValueError(
            f"Native {mode} failed (exit {result.returncode}); diagnostics retained at {stderr}"
        )
    return {
        "command": command,
        "exit_code": result.returncode,
        "started_monotonic_ns": started,
        "finished_monotonic_ns": time.monotonic_ns(),
        "stdout": stdout.relative_to(output).as_posix(),
        "stderr": stderr.relative_to(output).as_posix(),
    }


def build_native(
    plan: Plan, output: Path, *, binding: dict, node_ids: list[str] | None = None
) -> dict:
    """Build reviewed physical solids. The caller owns approval and publication gates."""
    plan = Plan.model_validate(plan.model_dump(mode="json"))
    if plan.units != "mm":
        raise ValueError(
            "Native CAD requires confirmed millimetre units; relative units are unresolved"
        )
    occurrences = _selection(plan, node_ids)
    binding = _validate_binding(plan, binding, occurrences)
    python = runtime_python()
    output = Path(output).absolute()
    if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
        raise ValueError("Native build output must be an empty directory")
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(RUNNER, output / "native-runner.py")
    _write_json(output / "plan.json", plan.model_dump(mode="json"))
    _write_json(output / "binding.json", binding)
    _write_json(
        output / "native-input.json",
        {
            "plan": plan.model_dump(mode="json"),
            "binding": binding,
            "occurrences": occurrences,
            "runner_sha256": _sha256(output / "native-runner.py"),
        },
    )
    definition_ids = sorted({item["definition_id"] for item in occurrences})
    processes = []
    try:
        with ThreadPoolExecutor(max_workers=min(2, len(definition_ids))) as executor:
            futures = [
                executor.submit(_run, python, output, "definition", name) for name in definition_ids
            ]
            errors = []
            for future in futures:
                try:
                    processes.append(future.result())
                except ValueError as error:
                    errors.append(str(error))
            if errors:
                raise ValueError("; ".join(errors))
        processes.append(_run(python, output, "assemble"))
        report_path = output / "native-report.json"
        report = json.loads(report_path.read_text())
        if report.get("binding") != binding:
            raise ValueError("Native report lost its immutable binding")
        if any(
            report.get("checks", {}).get(gate, {}).get("status") != "PASS"
            for gate in ("native_validity", "step_exchange")
        ):
            raise ValueError("Native report lacks verified solids and STEP exchange")
        report["processes"] = processes
        report["parallelism"] = {
            "max_definition_processes": 2,
            "unique_definition_count": len(definition_ids),
        }
        payload_digests = {
            path.relative_to(output).as_posix(): _sha256(path)
            for path in sorted(output.rglob("*"))
            if path.is_file() and path != report_path
        }
        report["artifacts"] = payload_digests
        _write_json(report_path, report)
        artifact_manifest = {**payload_digests, "native-report.json": _sha256(report_path)}
        return {
            **report,
            "artifacts": artifact_manifest,
            "step_path": "assembly.step",
            "preview_path": "native-preview.json",
            "report_path": "native-report.json",
        }
    except Exception as error:
        _write_json(
            output / "native-failure.json",
            {
                "binding": binding,
                "status": "failed",
                "error": str(error),
                "runner_sha256": _sha256(output / "native-runner.py"),
                "input_sha256": _sha256(output / "native-input.json"),
                "processes": processes,
                "source_fidelity": "UNCHECKED",
                "manufacturing": "UNCHECKED",
            },
        )
        raise
