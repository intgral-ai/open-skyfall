"""Build a verified native case for the repository's read-only STEP viewer."""

import argparse
import hashlib
import importlib.metadata
import json
import math
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import smlibpy
import smlibpy._core as core
from model import build
from smlibpy import export_step, read_step, save

PDF_SHA256 = "b3d0aed75980fa561695d4ea7432dfd6fb71455f380ef01b8d1cbe5c3ca82919"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def metrics(shape):
    box = shape.bbox()
    return {
        "valid": bool(shape.is_valid()),
        "solids": len(shape.solids()),
        "volume_mm3": float(shape.volume),
        "bounds": [list(box.min.to_tuple()), list(box.max.to_tuple())],
    }


def bounds(parts):
    boxes = [metrics(p)["bounds"] for p in parts]
    return [
        [min(b[0][axis] for b in boxes) for axis in range(3)],
        [max(b[1][axis] for b in boxes) for axis in range(3)],
    ]


def overlap_volume(a, b):
    # The public intersection wrapper in 0.3.4 can reject a correctly empty
    # common result for nested bounding boxes. Measure removed native volume.
    # An independent OCCT Common check below the build verifies this separately.
    return float(a.volume) - float((a - b).volume)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if digest(args.pdf) != PDF_SHA256:
        parser.error("PDF differs from the inspected source; review it before rebuilding")
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        parser.error("Output must be empty; use a new directory for each build")
    out.mkdir(parents=True, exist_ok=True)
    for folder in ["parts", "native", "checkpoints", "source", "context"]:
        (out / folder).mkdir()
    source = Path(__file__).resolve().parent
    for name in ["model.py", "build.py", "inspect_step.py", "README.md"]:
        shutil.copyfile(source / name, out / "source" / name)
    shutil.copyfile(args.pdf, out / "context" / "source.pdf")
    print("Building unique smlibpy definitions", flush=True)
    definitions, occurrences = build()
    definition_metrics = {}
    meshes = {}
    for id, definition in definitions.items():
        measured = metrics(definition.shape)
        if not measured["valid"] or measured["solids"] != 1 or measured["volume_mm3"] <= 0:
            raise ValueError(f"Invalid physical definition: {id}: {measured}")
        definition_metrics[id] = measured
        for label, state in definition.states:
            checkpoint = metrics(state)
            if (
                not checkpoint["valid"]
                or checkpoint["solids"] != 1
                or checkpoint["volume_mm3"] <= 0
            ):
                raise ValueError(f"Invalid native construction checkpoint: {id}: {label}")
        export_step(definition.shape, out / "parts" / f"{id}.step", unit="mm", name=id)
        save(definition.shape, out / "native" / f"{id}.smb", ascii=True)
        mesh = definition.shape.mesh(tolerance=0.04, angle=12)
        meshes[id] = {
            "vertices": mesh.vertices.tolist(),
            "triangles": mesh.triangles.astype(int).tolist(),
        }
        print(f"  {id}: {measured['volume_mm3']:.3f} mm3", flush=True)

    def preview_entry(occurrence, shape=None):
        definition = definitions[occurrence.definition_id]
        if shape is None:
            mesh = meshes[definition.id]
        else:
            tessellation = shape.mesh(tolerance=0.04, angle=12)
            mesh = {
                "vertices": tessellation.vertices.tolist(),
                "triangles": tessellation.triangles.astype(int).tolist(),
            }
        x, y, z = occurrence.position
        return {
            "id": occurrence.id,
            "definition_id": definition.id,
            "label": occurrence.label,
            **mesh,
            "transform": [[1, 0, 0, x], [0, 1, 0, y], [0, 0, 1, z], [0, 0, 0, 1]],
            "color": definition.color,
            "opacity": definition.opacity,
            "explode_vector": list(occurrence.explode),
        }

    world = [
        definitions[o.definition_id]
        .shape.translate(o.position)
        .named(o.id)
        .colored(definitions[o.definition_id].color)
        for o in occurrences
    ]
    print(f"Exporting {len(world)} placed native bodies", flush=True)
    export_step(world, out / "assembly.step", unit="mm", name="G2R-1-S_P2RF-05-E_demo")
    final_preview = {"parts": [preview_entry(o) for o in occurrences], "bounds": bounds(world)}
    write(out / "preview.json", final_preview)
    print("Reading exported STEP through smlibpy", flush=True)
    readback = list(read_step(out / "assembly.step", heal=False).bodies)
    observed = {part.name: metrics(part) for part in readback}
    placed_metrics = {o.id: metrics(part) for o, part in zip(occurrences, world)}
    roundtrip = len(observed) == len(world) and all(
        id in observed
        and observed[id]["valid"]
        and observed[id]["solids"] == 1
        and math.isclose(m["volume_mm3"], observed[id]["volume_mm3"], rel_tol=1e-6)
        and all(
            abs(a - b) < 1e-6
            for row_a, row_b in zip(m["bounds"], observed[id]["bounds"])
            for a, b in zip(row_a, row_b)
        )
        for id, m in placed_metrics.items()
    )
    print("Checking pairwise body interference", flush=True)
    intersections = []
    for i, a in enumerate(world):
        box_a = placed_metrics[occurrences[i].id]["bounds"]
        for j in range(i + 1, len(world)):
            box_b = placed_metrics[occurrences[j].id]["bounds"]
            if not all(
                min(box_a[1][k], box_b[1][k]) - max(box_a[0][k], box_b[0][k]) > 1e-6
                for k in range(3)
            ):
                continue
            volume = overlap_volume(a, world[j])
            if volume > 1e-5:
                intersections.append(
                    {"a": occurrences[i].id, "b": occurrences[j].id, "volume_mm3": volume}
                )

    # Check source dimensions on built shapes, not by restating parameters.
    def size(shape):
        b = metrics(shape)["bounds"]
        return [b[1][i] - b[0][i] for i in range(3)]

    relay_envelope = bounds([definitions[id].shape for id in ["relay_base", "cover", "nameplate"]])
    relay_size = [relay_envelope[1][i] - relay_envelope[0][i] for i in range(3)]
    socket_size = size(definitions["socket_body"].shape)
    # Witness volumes prove the mounting holes and blade slots are empty.
    from smlibpy import Box, Cylinder

    mounting_witnesses = [
        overlap_volume(
            definitions["socket_body"].shape, Cylinder(d / 2 - 0.02, 24).translate(0, y, 12.5)
        )
        for y, d in [(19.75, 3.2), (-19.75, 3.5)]
    ]
    pin_witnesses = [
        overlap_volume(
            definitions["socket_body"].shape,
            Box(4.75 if i < 3 else 1.2, 0.5, 4.9).translate(x, y, 22.95),
        )
        for i, (x, y) in enumerate([(0, -10.4), (0, -5.2), (0, 0), (-3.75, 12.3), (3.75, 12.3)])
    ]
    runtime = {
        "python": sys.version,
        "executable": str(Path(sys.executable).absolute()),
        "smlibpy": importlib.metadata.version("smlibpy"),
        "package": smlibpy.__file__,
        "native_binary": core.__file__,
        "native_binary_sha256": digest(core.__file__),
        "platform": platform.platform(),
        "kernel_source_revision": "unknown",
        "foreign_construction_modules_loaded": sorted(
            {
                n.split(".")[0]
                for n in sys.modules
                if n.split(".")[0] in {"OCP", "build123d", "cadquery", "cadgen"}
            }
        ),
    }
    checks = {
        "all_native_definitions_valid": all(m["valid"] for m in definition_metrics.values()),
        "smlibpy_step_readback": roundtrip,
        "no_positive_body_interference": not intersections,
        "relay_envelope_13_29_35_5_mm": all(
            abs(a - b) < 1e-6 for a, b in zip(relay_size, [13, 29, 35.5])
        ),
        "socket_envelope_16_85_5_48_mm": all(
            abs(a - b) < 1e-6 for a, b in zip(socket_size, [16, 85.5, 48])
        ),
        "mounting_hole_witnesses_empty": all(abs(v) < 1e-6 for v in mounting_witnesses),
        "pin_interface_witnesses_empty": all(abs(v) < 1e-6 for v in pin_witnesses),
        "smlibpy_only_construction": not runtime["foreign_construction_modules_loaded"],
    }
    report = {
        "valid": all(checks.values()),
        "checks": checks,
        "runtime": runtime,
        "source_pdf_sha256": PDF_SHA256,
        "step_sha256": digest(out / "assembly.step"),
        "units": "mm",
        "unique_definition_count": len(definitions),
        "physical_occurrence_count": len(occurrences),
        "definition_metrics": definition_metrics,
        "placed_metrics": placed_metrics,
        "readback_metrics": observed,
        "intersections": intersections,
        "relay_envelope_mm": relay_size,
        "socket_envelope_mm": socket_size,
        "mounting_hole_witness_volumes_mm3": mounting_witnesses,
        "pin_witness_volumes_mm3": pin_witnesses,
        "step_structure": "Flat named native B-rep bodies; physical hierarchy and repeated-definition placements are in document.json.",
        "accuracy": "Envelope/interface demo. Hidden internals, moulding contours, terminal routing and fit clearances are illustrative. No manufacturing acceptance.",
        "source_hashes": {p.name: digest(p) for p in (out / "source").iterdir()},
    }
    write(out / "native-report.json", report)
    if not report["valid"]:
        raise ValueError(f"Native checks failed: {checks}; see native-report.json")

    stages = []
    cumulative = []
    for occurrence in occurrences:
        definition = definitions[occurrence.definition_id]
        states = definition.states or [(f"Place {occurrence.label}", definition.shape)]
        for label, shape in states:
            index = len(stages)
            preview_name = f"checkpoints/{index + 1:02}.json"
            native_name = f"checkpoints/{index + 1:02}.smb"
            save(shape, out / native_name, ascii=True)
            write(
                out / preview_name,
                {
                    "parts": cumulative + [preview_entry(occurrence, shape)],
                    "bounds": final_preview["bounds"],
                },
            )
            stages.append(
                {
                    "id": f"stage_{index + 1}",
                    "index": index,
                    "label": label,
                    "kind": "part_construction" if len(states) > 1 else "assembly_placement",
                    "occurrence_id": occurrence.id,
                    "preview_artifact": preview_name,
                    "native_artifact": native_name,
                }
            )
        cumulative.append(preview_entry(occurrence))
    write(
        out / "construction.json",
        {
            "backend": "smlibpy",
            "physical_part_count": len(occurrences),
            "stages": stages,
            "final_preview_artifact": "preview.json",
        },
    )
    document = {
        "backend": "smlibpy",
        "units": "mm",
        "name": "G2R relay + P2RF socket · illustrative demo",
        "assembly_groups": [
            {"id": "socket", "label": "P2RF-05-E socket"},
            {"id": "relay", "label": "G2R-1-S relay"},
        ],
        "definitions": [
            {"id": d.id, "label": d.label, "source_artifact": f"parts/{d.id}.step"}
            for d in definitions.values()
        ],
        "occurrences": [
            {
                "id": o.id,
                "definition_id": o.definition_id,
                "parent_id": o.group,
                "label": o.label,
                "transform": preview_entry(o)["transform"],
            }
            for o in occurrences
        ],
    }
    write(out / "document.json", document)
    write(
        out / "context.json",
        {
            "goal": "Use the provided relay datasheet to build G2R-1-S + P2RF-05-E with smlibpy and show parts, explosion, saved construction and final STEP in the repository UI.",
            "source": {"artifact": "context/source.pdf", "sha256": PDF_SHA256, "pages": [6, 8]},
            "observed": [
                "G2R external envelope: 29 max x 13 max x 35.5 max mm; pin projection 5 mm; pin thickness 0.5 mm.",
                "P2RF-05-E: 16 max x 85.5 max x 48 max mm; mounting centres 39.5 +/-0.1 mm; holes 3.2 and 3.5 mm.",
                "Five M3.5 x 7 terminal screws are listed on page 8.",
            ],
            "assumptions": [
                "Maximum envelope dimensions are nominal demo targets, not measured production dimensions.",
                "Relay seating height 25.5 mm inferred for a 61 mm assembled envelope.",
                "Shell thickness, moulding steps, pin origins, all internal mechanisms, retaining hardware and terminal routing are approximate.",
                "Winding is one envelope solid. Screws omit threads. Relay switching and electrical performance are not simulated.",
                "STEP contains flat named bodies; document.json retains the physical hierarchy, unique definitions and placements.",
            ],
        },
    )
    timestamp = datetime.now(timezone.utc).isoformat()
    write(
        out / "case.json",
        {
            "id": "omron-g2r",
            "name": document["name"],
            "revision": 1,
            "updated_at": timestamp,
            "document": document,
            "source": {"kind": "manual", "sha256": PDF_SHA256},
            "context": json.loads((out / "context.json").read_text()),
            "native_report": "native-report.json",
            "independent_report": "inspection.json",
        },
    )
    report["artifact_hashes"] = {
        p.relative_to(out).as_posix(): digest(p)
        for p in out.rglob("*")
        if p.is_file() and p.name != "native-report.json"
    }
    write(out / "native-report.json", report)
    print(
        json.dumps(
            {
                "valid": True,
                "definitions": len(definitions),
                "occurrences": len(occurrences),
                "checkpoints": len(stages),
                "step_sha256": report["step_sha256"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
