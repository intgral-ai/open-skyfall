import hashlib
import inspect
import json
from pathlib import Path

import build123d as cad
import numpy as np
import trimesh
from OCP.gp import gp_Trsf

from .document import AssemblyDocument, Recipe


def build_shape(recipe: Recipe):
    p = recipe.parameters
    if recipe.kind in {"plate", "box"}:
        shape = cad.Box(p["length"], p["width"], p["height"])
        for hole in recipe.holes:
            shape = shape - cad.Cylinder(hole.diameter / 2, p["height"] + 2).translate(
                (hole.x, hole.y, 0)
            )
    else:
        shape = cad.Cylinder(p["outer_diameter"] / 2, p["height"])
        if recipe.kind == "sleeve":
            shape = shape - cad.Cylinder(p["inner_diameter"] / 2, p["height"] + 2)
    if not shape.is_valid or len(shape.solids()) != 1 or shape.volume <= 0:
        raise ValueError("Recipe did not produce one valid solid")
    return shape


def place_shape(shape, matrix):
    transform = gp_Trsf()
    transform.SetValues(*[float(v) for row in matrix[:3] for v in row])
    return shape.moved(cad.Location(transform))


def export_instances(shapes, occurrences, path, name):
    """One STEP product per definition, with named occurrence references."""
    from OCP.BRep import BRep_Builder
    from OCP.gp import gp_Trsf
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.Interface import Interface_Static
    from OCP.STEPCAFControl import STEPCAFControl_Controller, STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_StepModelType
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS_Compound
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    xde = TDocStd_Document(TCollection_ExtendedString("BinXCAF"))
    tool = XCAFDoc_DocumentTool.ShapeTool_s(xde.Main())
    compound = TopoDS_Compound()
    BRep_Builder().MakeCompound(compound)
    root = tool.AddShape(compound, False)
    TDataStd_Name.Set_s(root, TCollection_ExtendedString(name))
    labels = {}
    for definition_id, shape in shapes.items():
        label = tool.AddShape(shape.wrapped, False)
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(definition_id))
        labels[definition_id] = label
    for occurrence in occurrences:
        transform = gp_Trsf()
        transform.SetValues(*[float(v) for row in occurrence["transform"][:3] for v in row])
        label = tool.AddComponent(
            root, labels[occurrence["definition_id"]], TopLoc_Location(transform)
        )
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(occurrence["id"]))
    tool.UpdateAssemblies()
    STEPCAFControl_Controller.Init_s()
    Interface_Static.SetCVal_s("write.step.schema", "AP242DIS")
    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    if not writer.Transfer(xde, STEPControl_StepModelType.STEPControl_AsIs):
        raise ValueError("STEP assembly transfer failed")
    if writer.Write(str(path)) != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise ValueError("STEP assembly write failed")


def mesh_payload(shape) -> dict:
    vertices, triangles = shape.tessellate(0.03, angular_tolerance=0.08)
    return {
        "vertices": [[float(v.X), float(v.Y), float(v.Z)] for v in vertices],
        "triangles": [list(map(int, f)) for f in triangles],
    }


def generate_source(document: AssemblyDocument) -> str:
    """Readable standalone source. Only validated numeric recipes become code."""
    lines = [
        '"""Editable millimeter model. Requires build123d 0.13.0."""',
        "from pathlib import Path",
        "from build123d import Box, Cylinder",
        "",
        "OUTPUT = Path(__file__).resolve().parent",
        "parts = {}",
        "",
        inspect.getsource(export_instances),
    ]
    for definition in document.definitions:
        recipe = definition.recipe
        p = repr(recipe.parameters)
        lines += ["", f"p = {p}"]
        if recipe.kind in {"plate", "box"}:
            lines += ['shape = Box(p["length"], p["width"], p["height"])']
            for h in recipe.holes:
                lines += [
                    f'shape = shape - Cylinder({h.diameter!r} / 2, p["height"] + 2).translate(({h.x!r}, {h.y!r}, 0))'
                ]
        else:
            lines += ['shape = Cylinder(p["outer_diameter"] / 2, p["height"])']
            if recipe.kind == "sleeve":
                lines += ['shape = shape - Cylinder(p["inner_diameter"] / 2, p["height"] + 2)']
        lines += [f"parts[{definition.id!r}] = shape"]
    occurrences = [
        {"id": o.id, "definition_id": o.definition_id, "transform": document.global_transform(o.id)}
        for o in document.occurrences
    ]
    lines += [
        f"occurrences = {occurrences!r}",
        f'export_instances(parts, occurrences, OUTPUT / "assembly.step", {document.name!r})',
        "",
    ]
    return "\n".join(lines)


def surface_fit(reference: trimesh.Trimesh, candidate: trimesh.Trimesh, samples=384) -> dict:
    distances = []
    for source, target in ((reference, candidate), (candidate, reference)):
        points, _ = trimesh.sample.sample_surface(source, samples, seed=1729)
        vertex_indices = np.linspace(
            0, len(source.vertices) - 1, min(len(source.vertices), 2048), dtype=int
        )
        points = np.vstack((points, source.vertices[vertex_indices]))
        result = []
        for start in range(0, len(points), 32):
            _, distance, _ = trimesh.proximity.closest_point_naive(
                target, points[start : start + 32]
            )
            result.extend(distance)
        distances.extend(result)
    diagonal = float(np.linalg.norm(reference.extents))
    relative_volume_error = abs(abs(reference.volume) - abs(candidate.volume)) / abs(
        reference.volume
    )
    p95, maximum = np.percentile(distances, 95), max(distances)
    tolerance = max(0.002, diagonal * 0.001)
    valid = (
        p95 <= tolerance
        and maximum <= max(0.01, diagonal * 0.003)
        and relative_volume_error <= 0.01
    )
    return {
        "valid": bool(valid),
        "p95_mm": float(p95),
        "max_mm": float(maximum),
        "relative_volume_error": float(relative_volume_error),
        "tolerance_mm": tolerance,
        "sampling": {
            "seed": 1729,
            "area_samples_per_direction": samples,
            "vertex_sample_limit": 2048,
        },
    }


def _independent_step_check(path, document):
    try:
        from specify_core import api

        parts = api.parts(path)
        expected_ids = {
            d.id
            for d in document.definitions
            if any(o.definition_id == d.id for o in document.occurrences)
        }
        valid = {p["product_id"] for p in parts} == expected_ids
        valid &= sum(p["instances"] for p in parts) == len(document.occurrences)
        for part in parts:
            expected = [
                np.asarray(document.global_transform(o.id))[:3]
                for o in document.occurrences
                if o.definition_id == part["product_id"]
            ]
            observed = list(part["placements"])
            valid &= len(expected) == len(observed)
            for matrix in expected:
                matches = [
                    i
                    for i, placement in enumerate(observed)
                    if np.allclose(placement, matrix, rtol=0, atol=1e-7)
                ]
                if not matches:
                    valid = False
                else:
                    observed.pop(matches[0])
        return {
            "valid": bool(valid),
            "importer": "Specify pure Rust STEP product parser, not an independent B-rep kernel",
            "parts": parts,
        }
    except Exception as error:
        return {
            "valid": False,
            "importer": "Specify pure Rust STEP product parser",
            "error": str(error),
        }


def build_assembly(document: AssemblyDocument, output_dir, reference_mesh=None) -> dict:
    if not document.definitions or not document.occurrences:
        raise ValueError("Assembly needs at least one definition and occurrence")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "parts").mkdir(exist_ok=True)
    shapes, part_results, payloads = {}, [], {}
    for definition in document.definitions:
        shape = build_shape(definition.recipe)
        shape.label = definition.id
        shapes[definition.id] = shape
        payloads[definition.id] = mesh_payload(shape)
        cad.export_step(shape, output / "parts" / f"{definition.id}.step")
        fit = definition.evidence.get("fit")
        part_results.append(
            {
                "id": definition.id,
                "valid": bool(shape.is_valid),
                "solid_count": len(shape.solids()),
                "volume_mm3": shape.volume,
                "fit": fit,
            }
        )
    instances, previews, world_meshes = [], [], []
    for occurrence in document.occurrences:
        matrix = document.global_transform(occurrence.id)
        placed = place_shape(shapes[occurrence.definition_id], matrix)
        placed.label = occurrence.id
        instances.append(placed)
        payload = payloads[occurrence.definition_id]
        previews.append(
            {
                "id": occurrence.id,
                "definition_id": occurrence.definition_id,
                "label": next(
                    d.label for d in document.definitions if d.id == occurrence.definition_id
                ),
                **payload,
                "transform": matrix,
            }
        )
        mesh = trimesh.Trimesh(
            vertices=payload["vertices"], faces=payload["triangles"], process=False
        )
        mesh.apply_transform(matrix)
        world_meshes.append(mesh)
    assembly = cad.Compound(children=instances, label=document.name)
    export_instances(
        shapes,
        [
            {
                "id": o.id,
                "definition_id": o.definition_id,
                "transform": document.global_transform(o.id),
            }
            for o in document.occurrences
        ],
        output / "assembly.step",
        document.name,
    )
    readback = cad.import_step(output / "assembly.step")
    roundtrip_solids = list(readback.solids())
    expected_volumes = sorted(s.volume for s in instances)
    actual_volumes = sorted(s.volume for s in roundtrip_solids)
    volumes_match = len(actual_volumes) == len(expected_volumes) and np.allclose(
        actual_volumes, expected_volumes, rtol=1e-7, atol=1e-6
    )
    expected_bounds = sorted(
        tuple(list(s.bounding_box().min) + list(s.bounding_box().max)) for s in instances
    )
    actual_bounds = sorted(
        tuple(list(s.bounding_box().min) + list(s.bounding_box().max)) for s in roundtrip_solids
    )
    bounds_match = len(expected_bounds) == len(actual_bounds) and np.allclose(
        expected_bounds, actual_bounds, atol=1e-6
    )
    roundtrip_valid = bool(
        readback.is_valid
        and all(s.is_valid for s in roundtrip_solids)
        and volumes_match
        and bounds_match
    )
    independent = _independent_step_check(output / "assembly.step", document)
    overlap = []
    for i, left in enumerate(instances):
        for j in range(i + 1, len(instances)):
            common = left.intersect(instances[j])
            volume = (
                0
                if common is None
                else sum(abs(s.volume) for s in common)
                if isinstance(common, cad.ShapeList)
                else abs(common.volume)
            )
            fraction = volume / min(left.volume, instances[j].volume)
            overlap.append(
                {
                    "left": document.occurrences[i].id,
                    "right": document.occurrences[j].id,
                    "volume_mm3": float(volume),
                    "fraction_of_smaller": float(fraction),
                    "valid": fraction <= 0.001,
                }
            )
    combined_mesh = trimesh.util.concatenate(world_meshes)
    fit = None
    if reference_mesh is not None:
        reference = (
            reference_mesh
            if isinstance(reference_mesh, trimesh.Trimesh)
            else trimesh.load_mesh(reference_mesh)
        )
        if isinstance(reference, trimesh.Scene):
            reference = reference.to_mesh()
        if not isinstance(reference_mesh, trimesh.Trimesh):
            reference.apply_scale({"mm": 1, "cm": 10, "in": 25.4}.get(document.input.units, 1))
        fit = surface_fit(reference, combined_mesh)
    evidence_valid = all(
        p["fit"] is None or p["fit"].get("valid") is True for p in part_results
    ) and all(
        fit.get("valid") is True for d in document.definitions for fit in d.evidence.get("fits", [])
    )
    valid = bool(
        roundtrip_valid
        and independent["valid"]
        and all(p["valid"] for p in part_results)
        and all(o["valid"] for o in overlap)
        and evidence_valid
        and (fit is None or fit["valid"])
    )
    validation = {
        "valid": valid,
        "solid_count": len(assembly.solids()),
        "expected_solid_count": len(instances),
        "roundtrip_valid": roundtrip_valid,
        "roundtrip_importer": "build123d/OCP native, not independent",
        "roundtrip_volumes_mm3": actual_volumes,
        "roundtrip_bounds_match": bool(bounds_match),
        "independent_step": independent,
        "parts": part_results,
        "overlap": overlap,
        "fit": fit,
        "revision": document.revision,
    }
    (output / "preview.json").write_text(
        json.dumps({"parts": previews, "bounds": combined_mesh.bounds.tolist()})
    )
    (output / "source.py").write_text(generate_source(document))
    (output / "document.json").write_text(document.model_dump_json(indent=2))
    (output / "validation.json").write_text(json.dumps(validation, indent=2))
    artifacts = {}
    for path in sorted(output.rglob("*")):
        if path.is_file():
            artifacts[path.relative_to(output).as_posix()] = {
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size": path.stat().st_size,
            }
    return {"artifacts": artifacts, "validation": validation}
