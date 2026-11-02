import hashlib
import importlib.metadata
import importlib.util
import json
import math
import platform
import sys
from pathlib import Path

SOURCE_SHA256 = "7bc71c24414c9c8da0059c7381cbae4e9884d76cd97d0c47986cd373024d621a"
IDENTITY = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
STAGES = (
    "tub",
    "bottom-rounds",
    "corner-cut",
    "cavity",
    "rim-steps",
    "channel",
    "hook",
    "tongue",
    "clip",
    "pocket",
)


def write_json(path, value):
    path.write_text(json.dumps(value, allow_nan=False, indent=2) + "\n")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(part):
    box = part.bbox()
    return {
        "valid": bool(part.is_valid()),
        "solids": len(part.solids()),
        "faces": len(part.faces()),
        "volume": float(part.volume),
        "bounds": [list(box.min.to_tuple()), list(box.max.to_tuple())],
    }


def runtime_identity():
    import smlibpy
    import smlibpy._core as core

    binary = Path(core.__file__)
    return {
        "python": sys.version,
        "python_executable": str(Path(sys.executable).absolute()),
        "python_binary_path": str(Path(sys.executable).resolve()),
        "python_sha256": sha256(Path(sys.executable).resolve()),
        "platform": platform.platform(),
        "smlibpy": importlib.metadata.version("smlibpy"),
        "package_path": smlibpy.__file__,
        "binary_path": str(binary),
        "binary_sha256": sha256(binary),
        "foreign_construction_modules_loaded": sorted(
            {
                name.split(".")[0]
                for name in sys.modules
                if name.split(".")[0] in {"OCP", "build123d", "cadquery", "cadgen"}
            }
        ),
    }


def preview(part, measured):
    mesh = part.mesh(tolerance=0.03, angle=12)
    return {
        "parts": [
            {
                "id": "wiring_cover_1",
                "definition_id": "wiring_cover",
                "label": "Wiring cover",
                "vertices": mesh.vertices.tolist(),
                "triangles": mesh.triangles.astype(int).tolist(),
                "transform": IDENTITY,
            }
        ],
        "bounds": measured["bounds"],
    }


def matching_readback(actual, observed):
    return (
        observed["valid"]
        and observed["solids"] == 1
        and observed["faces"] == actual["faces"]
        and math.isclose(observed["volume"], actual["volume"], rel_tol=1e-6)
        and all(
            math.isclose(a, b, rel_tol=0, abs_tol=1e-9)
            for row_a, row_b in zip(actual["bounds"], observed["bounds"])
            for a, b in zip(row_a, row_b)
        )
    )


def main():
    if sys.argv[1:] == ["--capability"]:
        print(json.dumps(runtime_identity()))
        return
    if len(sys.argv) != 2:
        raise ValueError("Run rebuild.py with one output directory")
    inputs = Path(__file__).resolve().parent
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = inputs / "source.py"
    if sha256(source) != SOURCE_SHA256:
        raise ValueError("Trusted native source hash mismatch")
    parameters = json.loads((inputs / "parameters.json").read_text())
    if set(parameters) != {"hook_top"}:
        raise ValueError("Only hook_top is supported")
    height = parameters["hook_top"]
    if type(height) not in (int, float) or not math.isfinite(height) or not 5.55 <= height <= 6.55:
        raise ValueError("hook_top must be a finite number between 5.55 and 6.55 mm")
    from smlibpy import export_step, load, read_step, save

    spec = importlib.util.spec_from_file_location("registered_wiring_cover", source)
    model = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(model)
    model.HOOK_TOP = height
    stages, _ = model.build()
    if tuple(stage[0] for stage in stages) != STAGES:
        raise ValueError("Unexpected native construction stages")
    records = []
    checkpoints = output / "checkpoints"
    checkpoints.mkdir(exist_ok=True)
    for index, (stage_id, part, _, _) in enumerate(stages):
        measured = metrics(part)
        if not measured["valid"] or measured["solids"] != 1:
            raise ValueError(f"Invalid native solid at {stage_id}")
        native_name = f"checkpoints/{index + 1:02}-{stage_id}.smb"
        preview_name = f"checkpoints/{index + 1:02}-{stage_id}.json"
        save(part, output / native_name, ascii=True)
        write_json(output / preview_name, preview(part, measured))
        records.append(
            {
                "id": stage_id,
                "label": stage_id.replace("-", " ").capitalize(),
                "index": index,
                "native_artifact": native_name,
                "preview_artifact": preview_name,
                "metrics": measured,
            }
        )
    final = stages[-1][1].named("wiring_cover")
    measured = metrics(final)
    export_step(final, output / "assembly.step", unit="mm", name="wiring_cover")
    save(final, output / "final.smb", ascii=True)
    write_json(output / "preview.json", preview(final, measured))
    bodies = list(read_step(output / "assembly.step", heal=False).bodies)
    if len(bodies) != 1:
        raise ValueError("Native STEP readback must contain one body")
    step_metrics = metrics(bodies[0])
    native_metrics = metrics(load(output / "final.smb"))
    runtime = runtime_identity()
    checks = {
        "native_solid": measured["valid"] and measured["solids"] == 1,
        "step_readback": matching_readback(measured, step_metrics),
        "native_readback": matching_readback(measured, native_metrics),
        "ten_cumulative_checkpoints": len(records) == 10,
        "smlibpy_only_construction": not runtime["foreign_construction_modules_loaded"],
    }
    if not all(checks.values()):
        raise ValueError(f"Native build checks failed: {checks}")
    write_json(
        output / "construction.json",
        {
            "backend": "smlibpy",
            "physical_part_count": 1,
            "stages": records,
            "final_preview_artifact": "preview.json",
        },
    )
    report = {
        "source_sha256": sha256(source),
        "parameters": parameters,
        "metrics": measured,
        "step_readback": step_metrics,
        "native_readback": native_metrics,
        "stages": records,
        "runtime": runtime,
        "checks": checks,
        "numeric_bounds_tolerance_mm": 1e-9,
    }
    write_json(output / "native-report.json", report)
    print(json.dumps({"valid": True, "stage_count": len(records), "volume": measured["volume"]}))


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
