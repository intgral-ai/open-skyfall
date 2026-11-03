import hashlib
import importlib.metadata
import json
import math
import os
import platform
import sys
import traceback
from pathlib import Path

import numpy as np

PALETTE = ["#9caeb1", "#c3b59f", "#a4b3a0", "#a6abc1", "#bca3a1", "#a8b8c8"]
BOUND_TOLERANCE = 1e-6


def json_bytes(value):
    return (
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )
        + "\n"
    ).encode()


def write_json(path, value):
    path.write_bytes(json_bytes(value))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_identity():
    import smlibpy
    import smlibpy._core as core

    binary = Path(core.__file__)
    executable = Path(sys.executable).resolve()
    return {
        "python": sys.version,
        "python_executable": str(Path(sys.executable).absolute()),
        "python_binary_path": str(executable),
        "python_sha256": sha256(executable),
        "platform": platform.platform(),
        "smlibpy": importlib.metadata.version("smlibpy"),
        "package_path": smlibpy.__file__,
        "binary_path": str(binary),
        "binary_sha256": sha256(binary),
        "pid": os.getpid(),
        "foreign_construction_modules_loaded": sorted(
            {
                name.split(".")[0]
                for name in sys.modules
                if name.split(".")[0] in {"OCP", "build123d", "cadquery", "cadgen"}
            }
        ),
    }


def metrics(part):
    box = part.bbox()
    return {
        "valid": bool(part.is_valid()),
        "solid_count": len(part.solids()),
        "face_count": len(part.faces()),
        "volume": float(part.volume),
        "bounds": [list(box.min.to_tuple()), list(box.max.to_tuple())],
    }


def require_solid(measured, label):
    if (
        not measured["valid"]
        or measured["solid_count"] != 1
        or not math.isfinite(measured["volume"])
        or measured["volume"] <= 0
        or not np.isfinite(measured["bounds"]).all()
    ):
        raise ValueError(f"{label} must be one valid connected positive-volume solid: {measured}")


def compare(actual, observed):
    require_solid(observed, "Readback")
    return math.isclose(actual["volume"], observed["volume"], rel_tol=1e-6, abs_tol=1e-9) and bool(
        np.allclose(actual["bounds"], observed["bounds"], rtol=0, atol=BOUND_TOLERANCE)
    )


def pose_matrix(pose):
    x, y, z = np.radians(pose["rotation"])
    sx, cx, sy, cy, sz, cz = (
        math.sin(x),
        math.cos(x),
        math.sin(y),
        math.cos(y),
        math.sin(z),
        math.cos(z),
    )
    matrix = np.array(
        [
            [cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx, 0],
            [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx, 0],
            [-sy, cy * sx, cy * cx, 0],
            [0, 0, 0, 1],
        ],
        dtype=float,
    )
    matrix[:3, 3] = pose["position"]
    return matrix


def receipt(data, input_path):
    runtime = runtime_identity()
    if sys.version_info[:2] != (3, 12):
        raise ValueError("Native construction requires the isolated Python 3.12 smlibpy runtime")
    if runtime["foreign_construction_modules_loaded"]:
        raise ValueError("Foreign construction kernel loaded into native process")
    return {
        "binding": data["binding"],
        "runtime": runtime,
        "runner_sha256": sha256(Path(__file__)),
        "input_sha256": sha256(input_path),
    }


def validate_occurrences(data):
    nodes = {node["id"]: node for node in data["plan"]["nodes"]}
    matrices = {}

    def world(node):
        if node["id"] not in matrices:
            local = pose_matrix(node)
            matrices[node["id"]] = (
                world(nodes[node["parent_id"]]) @ local if node["parent_id"] else local
            )
        return matrices[node["id"]]

    ids = [item["id"] for item in data["occurrences"]]
    if (
        not ids
        or len(ids) != len(set(ids))
        or set(ids) != set(data["binding"]["part_ids"])
        or set(ids) != set(data["binding"]["review_digests"])
    ):
        raise ValueError("Native input does not match its exact reviewed physical part set")
    for occurrence in data["occurrences"]:
        node = nodes.get(occurrence["id"])
        if (
            node is None
            or node["definition_id"] is None
            or any(occurrence.get(key) != value for key, value in node.items())
            or not np.allclose(occurrence["world_transform"], world(node), rtol=0, atol=1e-9)
        ):
            raise ValueError("Native occurrence or composed transform differs from the bound Plan")


def build_definition(data, input_path, output, definition_id):
    from smlibpy import Box, Cone, Cylinder, Location, Sphere, export_step, load, read_step, save

    directory = output / "definitions" / definition_id
    directory.mkdir(parents=True, exist_ok=True)
    definition = next(item for item in data["plan"]["definitions"] if item["id"] == definition_id)
    base = receipt(data, input_path)
    stages = []
    part = None
    try:
        for index, shape in enumerate(definition["shapes"]):
            dimensions = shape["dimensions"]
            kind = shape["kind"]
            shape_id = shape.get("id") or f"shape-{index + 1}"
            if kind == "box":
                primitive = Box(*dimensions)
            elif kind == "cylinder":
                primitive = Cylinder(*dimensions)
            elif kind == "sphere":
                primitive = Sphere(*dimensions)
            elif kind == "shell":
                lower, upper, height, wall = dimensions
                outer = Cone(lower, upper, height)
                inner = Cone(lower - wall, upper - wall, height)
                stages.extend(
                    [
                        {
                            "id": f"{shape_id}/outer",
                            "operation": "create_cone",
                            "dimensions": [lower, upper, height],
                            "metrics": metrics(outer),
                        },
                        {
                            "id": f"{shape_id}/inner",
                            "operation": "create_cone",
                            "dimensions": [lower - wall, upper - wall, height],
                            "metrics": metrics(inner),
                        },
                    ]
                )
                primitive = outer - inner
            else:
                raise ValueError("Unsupported native primitive")
            stages.append(
                {
                    "id": f"{shape_id}/create",
                    "operation": "subtract_shell" if kind == "shell" else "create_primitive",
                    "kind": kind,
                    "dimensions": dimensions,
                    "metrics": metrics(primitive),
                }
            )
            primitive = primitive.moved(Location(pose_matrix(shape)))
            stages.append(
                {
                    "id": f"{shape_id}/pose",
                    "operation": "shape_transform",
                    "transform": pose_matrix(shape).tolist(),
                    "metrics": metrics(primitive),
                }
            )
            operation = "initialize_definition" if part is None else "fuse_definition"
            part = primitive if part is None else part + primitive
            stages.append(
                {"id": f"{shape_id}/union", "operation": operation, "metrics": metrics(part)}
            )
        part = part.named(definition_id)
        measured = metrics(part)
        require_solid(measured, f"Definition {definition_id}")
        save(part, directory / "part.smb", ascii=True)
        export_step(part, directory / "part.step", unit="mm", name=definition_id)
        bodies = list(read_step(directory / "part.step", heal=False).bodies)
        if len(bodies) != 1 or bodies[0].name != definition_id:
            raise ValueError("Definition STEP readback lost its exact body identity")
        readback = metrics(bodies[0])
        native_readback = metrics(load(directory / "part.smb"))
        if not compare(measured, readback) or not compare(measured, native_readback):
            raise ValueError("Definition native/STEP readback changed geometry")
        write_json(
            directory / "report.json",
            {
                **base,
                "id": definition_id,
                "status": "complete",
                "metrics": measured,
                "step_readback": readback,
                "native_readback": native_readback,
                "stages": stages,
                "smb_path": f"definitions/{definition_id}/part.smb",
                "step_path": f"definitions/{definition_id}/part.step",
                "artifacts": {
                    "part.smb": sha256(directory / "part.smb"),
                    "part.step": sha256(directory / "part.step"),
                },
                "manufacturing": {
                    "status": "UNCHECKED",
                    "proposal": definition.get("manufacturing"),
                },
                "source_fidelity": {"status": "UNCHECKED"},
            },
        )
    except Exception as error:
        write_json(
            directory / "failure.json",
            {
                **base,
                "id": definition_id,
                "status": "failed",
                "error": str(error),
                "stages": stages,
            },
        )
        raise


def assemble(data, input_path, output):
    from smlibpy import Location, export_step, load, read_step

    base = receipt(data, input_path)
    definitions = {}
    reports = {}
    selected = {item["definition_id"] for item in data["occurrences"]}
    for definition_id in sorted(selected):
        directory = output / "definitions" / definition_id
        report = json.loads((directory / "report.json").read_text())
        if (
            report["binding"] != data["binding"]
            or report["input_sha256"] != base["input_sha256"]
            or report["runner_sha256"] != base["runner_sha256"]
            or report["runtime"]["binary_sha256"] != base["runtime"]["binary_sha256"]
        ):
            raise ValueError("Definition receipt does not match the assembly input/runtime")
        for name, digest in report["artifacts"].items():
            if sha256(directory / name) != digest:
                raise ValueError("Definition artifact hash mismatch")
        definitions[definition_id] = load(directory / "part.smb")
        reports[definition_id] = report
    placed = []
    occurrence_reports = []
    preview_parts = []
    for occurrence in data["occurrences"]:
        definition_id = occurrence["definition_id"]
        matrix = np.asarray(occurrence["world_transform"], dtype=float)
        part = definitions[definition_id].moved(Location(matrix)).named(occurrence["id"])
        measured = metrics(part)
        require_solid(measured, f"Occurrence {occurrence['id']}")
        placed.append(part)
        occurrence_reports.append(
            {
                **occurrence,
                "metrics": measured,
                "review_digest": data["binding"]["review_digests"][occurrence["id"]],
            }
        )
        diagonal = float(np.linalg.norm(np.diff(np.asarray(measured["bounds"]), axis=0)))
        mesh = part.mesh(tolerance=max(1e-6, min(0.03, diagonal * 0.001)), angle=12)
        vertices, triangles = np.asarray(mesh.vertices), np.asarray(mesh.triangles, dtype=int)
        if (
            not len(vertices)
            or not len(triangles)
            or not np.isfinite(vertices).all()
            or triangles.min() < 0
            or triangles.max() >= len(vertices)
        ):
            raise ValueError("Native tessellation has invalid or missing triangles")
        color_hash = 2166136261
        for character in occurrence["id"]:
            color_hash = ((color_hash ^ ord(character)) * 16777619) & 0xFFFFFFFF
        preview_parts.append(
            {
                "id": occurrence["id"],
                "definition_id": definition_id,
                "color": PALETTE[color_hash % len(PALETTE)],
                "vertices": vertices.tolist(),
                "triangles": triangles.tolist(),
                "bounds": measured["bounds"],
            }
        )
    export_step(placed, output / "assembly.step", unit="mm", name="assembly")
    readback_bodies = list(read_step(output / "assembly.step", heal=False).bodies)
    by_name = {body.name: body for body in readback_bodies}
    expected_names = {item["id"] for item in occurrence_reports}
    if len(readback_bodies) != len(expected_names) or set(by_name) != expected_names:
        raise ValueError("STEP readback lost exact occurrence names or physical body count")
    for occurrence in occurrence_reports:
        body = by_name[occurrence["id"]]
        readback = metrics(body)
        local_readback = metrics(body.moved(Location(np.linalg.inv(occurrence["world_transform"]))))
        if not compare(occurrence["metrics"], readback) or not compare(
            reports[occurrence["definition_id"]]["metrics"], local_readback
        ):
            raise ValueError(f"STEP readback changed placement/geometry for {occurrence['id']}")
        occurrence["step_readback"] = readback
        occurrence["unplaced_step_readback"] = local_readback
    bounds = np.asarray([item["metrics"]["bounds"] for item in occurrence_reports])
    low, high = bounds[:, 0].min(axis=0), bounds[:, 1].max(axis=0)
    extent = float((high - low).max())
    write_json(
        output / "native-trace.json",
        {
            **base,
            "definition_stages": {key: value["stages"] for key, value in reports.items()},
            "placements": [
                {
                    "id": item["id"],
                    "operation": "place_occurrence",
                    "definition_id": item["definition_id"],
                    "world_transform": item["world_transform"],
                    "metrics": item["metrics"],
                }
                for item in occurrence_reports
            ],
            "step_export": {
                "operation": "export_step",
                "unit": "mm",
                "path": "assembly.step",
                "sha256": sha256(output / "assembly.step"),
                "body_count": len(placed),
                "names": sorted(by_name),
            },
            "step_readback": {
                "operation": "read_step",
                "heal": False,
                "occurrences": [
                    {"id": item["id"], "metrics": item["step_readback"]}
                    for item in occurrence_reports
                ],
            },
        },
    )
    write_json(
        output / "native-preview.json",
        {
            "binding": data["binding"],
            "backend": "smlibpy",
            "parts": preview_parts,
            "normalization": {"center": ((low + high) / 2).tolist(), "scale": 4 / extent},
            "coordinates": "Right-handed Z-up; raw vertices retain millimetres and assembly placements",
        },
    )
    write_json(
        output / "assembly.json",
        {
            "binding": data["binding"],
            "units": "mm",
            "step_structure": "flat_named_bodies",
            "physical_tree": data["plan"]["nodes"],
            "definitions": data["plan"]["definitions"],
            "occurrences": occurrence_reports,
            "selected_part_ids": data["binding"]["part_ids"],
            "native_mates": False,
        },
    )
    write_json(
        output / "native-report.json",
        {
            **base,
            "step_structure": "flat_named_bodies",
            "definitions": reports,
            "occurrences": occurrence_reports,
            "checks": {
                "native_validity": {"status": "PASS", "physical_part_count": len(placed)},
                "step_exchange": {
                    "status": "PASS",
                    "heal": False,
                    "names": sorted(by_name),
                    "bounds_tolerance_mm": BOUND_TOLERANCE,
                    "volume_relative_tolerance": 1e-6,
                },
                "source_fidelity": {"status": "UNCHECKED"},
                "manufacturing": {"status": "UNCHECKED"},
            },
            "step_path": "assembly.step",
            "preview_path": "native-preview.json",
            "report_path": "native-report.json",
        },
    )


def main():
    if len(sys.argv) not in {3, 4} or sys.argv[1] not in {"definition", "assemble"}:
        raise ValueError("Expected trusted runner mode and immutable input path")
    mode = sys.argv[1]
    input_path = Path(sys.argv[2]).resolve()
    output = input_path.parent
    data = json.loads(input_path.read_text())
    if data["runner_sha256"] != sha256(Path(__file__)):
        raise ValueError("Trusted native runner hash mismatch")
    if (
        data["plan"]["units"] != "mm"
        or data["plan"]["source_sha256"] != data["binding"]["source_sha256"]
        or hashlib.sha256(json_bytes(data["plan"])).hexdigest() != data["binding"]["plan_sha256"]
    ):
        raise ValueError("Native input source, Plan hash or millimetre binding mismatch")
    validate_occurrences(data)
    if mode == "definition" and len(sys.argv) == 4:
        if sys.argv[3] not in {item["definition_id"] for item in data["occurrences"]}:
            raise ValueError("Native definition is outside the reviewed physical part set")
        build_definition(data, input_path, output, sys.argv[3])
    elif mode == "assemble" and len(sys.argv) == 3:
        assemble(data, input_path, output)
    else:
        raise ValueError("Invalid trusted runner invocation")


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
