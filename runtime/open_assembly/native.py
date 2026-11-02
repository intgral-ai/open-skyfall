import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import Field

from .context import ContextModel, Identifier
from .document import (
    NATIVE_SOURCE_SHA256,
    HookTop,
    NativeAssemblyDocument,
    NativeInputEvidence,
    NativeParameters,
    NativePartDefinition,
    Occurrence,
)

RESOURCE_DIR = Path(__file__).parent / "native_resources"
WORKER = Path(__file__).with_name("native_worker.py")
SCOPE_LIMITS = [
    "This edits an existing CAD reconstruction; it does not reconstruct the current image.",
    "Millimetres are a working assumption for the original unitless scan.",
    "The tongue, tie loop and underside clip are approximate.",
    "Small rounds, clip nub, leg draft, ejector dimples, rim blends and channel fillets are omitted.",
    "Metric comparisons do not prove full geometric identity or source accuracy.",
    "Captured text is recorded; only the explicit hook_top proposal is executed and checked.",
    "No manufacturing, tolerance or factory-intent acceptance is asserted.",
]


class NativeExampleCommand(ContextModel):
    case_id: Literal["wiring-cover"]


class NativeEditCommand(ContextModel):
    request_id: Identifier
    hook_top: HookTop


class NativeExecution(ContextModel):
    id: str
    request_id: str | None
    command: NativeParameters
    base_revision: int
    output_revision: int
    context_revision: int
    base_step_sha256: str | None
    build_id: str
    case_id: Literal["wiring-cover"] = "wiring-cover"
    source_sha256: Literal[NATIVE_SOURCE_SHA256] = NATIVE_SOURCE_SHA256
    status: Literal["queued", "building", "accepted", "failed", "stale"] = "queued"
    status_version: int = Field(default=1, ge=1)
    created_at: str
    updated_at: str
    output_step_sha256: str | None = None
    error: dict[str, str] | None = None


def registered_source():
    source = RESOURCE_DIR / "wiring_cover.py.txt"
    if hashlib.sha256(source.read_bytes()).hexdigest() != NATIVE_SOURCE_SHA256:
        raise ValueError("Registered native source hash mismatch")
    return source


def runtime_python():
    value = os.environ.get("OPEN_ASSEMBLY_SMLIB_PYTHON")
    if not value:
        raise ValueError("Set OPEN_ASSEMBLY_SMLIB_PYTHON to an installed smlibpy Python runtime")
    path = Path(value).expanduser().absolute()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError("OPEN_ASSEMBLY_SMLIB_PYTHON is not an executable Python runtime")
    return path


def native_cases():
    reason = None
    try:
        registered_source()
        subprocess.run(
            [str(runtime_python()), "-I", "-B", str(WORKER), "--capability"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        reason = str(error)
    return {
        "cases": [
            {
                "case_id": "wiring-cover",
                "name": "Wiring cover",
                "backend": "smlibpy",
                "available": reason is None,
                "unavailable_reason": reason,
                "source_sha256": NATIVE_SOURCE_SHA256,
                "parameters": {
                    "hook_top": {"default": 5.55, "min": 5.55, "max": 6.55, "unit": "mm"}
                },
                "scope_limits": SCOPE_LIMITS,
            }
        ]
    }


def native_document():
    return NativeAssemblyDocument(
        name="Native wiring cover",
        input=NativeInputEvidence(
            name="Registered wiring_cover.py",
            sha256=NATIVE_SOURCE_SHA256,
            assumptions=SCOPE_LIMITS,
        ),
        definitions=[NativePartDefinition()],
        occurrences=[Occurrence(id="wiring_cover_1", definition_id="wiring_cover")],
        assumptions=SCOPE_LIMITS,
    )


def _independent_step(path, native_metrics):
    import build123d as cad
    from specify_core import api

    shape = cad.import_step(path)
    parts = api.parts(path)
    box = shape.bounding_box()
    bounds = [[point.X, point.Y, point.Z] for point in (box.min, box.max)]
    units_mm = bool(re.search(r"SI_UNIT\s*\(\s*\.MILLI\.\s*,\s*\.METRE\.\s*\)", path.read_text()))
    valid = (
        shape.is_valid
        and len(shape.solids()) == 1
        and len(parts) == 1
        and parts[0]["instances"] == 1
        and parts[0]["product_id"] == "wiring_cover"
        and units_mm
        and math.isclose(shape.volume, native_metrics["volume"], rel_tol=1e-6)
        and all(
            math.isclose(a, b, rel_tol=0, abs_tol=1e-5)
            for row_a, row_b in zip(bounds, native_metrics["bounds"])
            for a, b in zip(row_a, row_b)
        )
    )
    return {
        "valid": bool(valid),
        "solid_count": len(shape.solids()),
        "volume_mm3": shape.volume,
        "bounds": bounds,
        "units_mm": units_mm,
        "parts": parts,
        "importer": "OCCT via build123d.import_step, read only; Specify STEP product parser",
    }


def _comparison(before, after, base_revision, old_height, new_height):
    delta = after["metrics"]["volume"] - before["metrics"]["volume"]
    z_delta = after["metrics"]["bounds"][1][2] - before["metrics"]["bounds"][1][2]
    expected = 7.30 * 1.65 * (new_height - old_height)
    protected = []
    for old, new in zip(before["stages"][:6], after["stages"][:6]):
        a, b = old["metrics"], new["metrics"]
        valid = (
            old["id"] == new["id"]
            and a["faces"] == b["faces"]
            and a["solids"] == b["solids"] == 1
            and a["valid"]
            and b["valid"]
            and math.isclose(a["volume"], b["volume"], rel_tol=1e-9)
            and all(
                math.isclose(u, v, rel_tol=0, abs_tol=1e-9)
                for row_a, row_b in zip(a["bounds"], b["bounds"])
                for u, v in zip(row_a, row_b)
            )
        )
        protected.append({"id": old["id"], "valid": bool(valid)})
    bounds = all(
        math.isclose(old, new, rel_tol=0, abs_tol=1e-9)
        for index, (old, new) in enumerate(
            zip(
                [value for row in before["metrics"]["bounds"] for value in row],
                [value for row in after["metrics"]["bounds"] for value in row],
            )
        )
        if index != 5
    )
    return {
        "base_revision": base_revision,
        "hook_top_before": old_height,
        "hook_top_after": new_height,
        "volume_delta_mm3": delta,
        "expected_volume_delta_mm3": expected,
        "z_max_delta_mm": z_delta,
        "protected_stages": protected,
        "numeric_bounds_tolerance_mm": 1e-9,
        "volume_delta_tolerance_mm3": 0.001,
        "valid": len(protected) == 6
        and all(row["valid"] for row in protected)
        and bounds
        and math.isclose(delta, expected, abs_tol=0.001)
        and math.isclose(z_delta, new_height - old_height, rel_tol=0, abs_tol=1e-9),
    }


def build_native(document, output, *, previous=None, base_revision=0):
    source = registered_source()
    python = runtime_python()
    shutil.copyfile(source, output / "source.py")
    shutil.copyfile(WORKER, output / "rebuild.py")
    shutil.copyfile(RESOURCE_DIR / "NOTICE.txt", output / "NOTICE.txt")
    (output / "document.json").write_text(document.model_dump_json(indent=2))
    (output / "parameters.json").write_text(
        document.definitions[0].parameters.model_dump_json(indent=2)
    )
    completed = subprocess.run(
        [str(python), "-I", "-B", str(output / "rebuild.py"), str(output)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    (output / "build.log").write_text(completed.stdout + completed.stderr)
    if completed.returncode:
        raise ValueError(f"Native build failed: {(completed.stderr or completed.stdout)[-2000:]}")
    report = json.loads((output / "native-report.json").read_text())
    if report["source_sha256"] != document.source_sha256 or not all(report["checks"].values()):
        raise ValueError("Native worker rejected source or geometry")
    report["scope_limits"] = SCOPE_LIMITS
    independent = _independent_step(output / "assembly.step", report["metrics"])
    comparison = None
    if previous is not None:
        comparison = _comparison(
            previous,
            report,
            base_revision,
            previous["parameters"]["hook_top"],
            document.definitions[0].parameters.hook_top,
        )
    validation = {
        "backend": "smlibpy",
        "valid": independent["valid"] and (comparison is None or comparison["valid"]),
        "roundtrip_valid": report["checks"]["step_readback"]
        and report["checks"]["native_readback"],
        "solid_count": report["metrics"]["solids"],
        "native": report,
        "independent_step": independent,
        "comparison": comparison,
    }
    provenance = {
        "case_id": document.case_id,
        "source_sha256": document.source_sha256,
        "source_origin": "wiring-cover-claude:6dc1ef6:cases/wiring-cover/model/wiring_cover.py",
        "original_scan_sha256": "9a9b33a0eb30e498d9d8ddc760130fb31a760abc5af03b3d1523b97a02f7bf2a",
        "parameters": report["parameters"],
        "runtime": report["runtime"],
        "runtime_launcher": str(python),
        "scope_limits": SCOPE_LIMITS,
        "construction": "STEP, SMB and final preview exported from the same final native Part",
        "rebuild": "Run the recorded smlibpy Python with -I -B rebuild.py OUTPUT_DIRECTORY",
    }
    for name, value in (("validation.json", validation), ("provenance.json", provenance)):
        (output / name).write_text(json.dumps(value, allow_nan=False, indent=2) + "\n")
    return {"validation": validation}
