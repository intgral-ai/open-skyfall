from pathlib import Path

import build123d as cad
import numpy as np
import pytest
import trimesh
from open_assembly.fixtures import create_demo
from open_assembly.geometry import build_assembly, build_shape, place_shape
from open_assembly.reconstruction import ReconstructionError, inspect_stl
from specify_core import api


@pytest.mark.parametrize("variant", range(10))
def test_ten_real_stl_variants_dimensions_poses_and_step(tmp_path, variant):
    fixture = create_demo(tmp_path / "fixture", variant)
    assert Path(fixture["input"]).stat().st_size > 1000
    document = inspect_stl(fixture["input"], "mm")
    assert len(document.definitions) == 3
    assert len(document.occurrences) == 4
    by_kind = {d.recipe.kind: d for d in document.definitions}
    reference = fixture["metadata"]
    plate = by_kind["plate"].recipe
    dimensions = reference["dimensions"]
    assert sorted([plate.parameters["length"], plate.parameters["width"]]) == pytest.approx(
        sorted([dimensions["base"]["length"], dimensions["base"]["width"]]), abs=0.002
    )
    assert plate.parameters["height"] == pytest.approx(dimensions["base"]["height"], abs=0.002)
    assert len(plate.holes) == 2
    assert sorted(h.diameter for h in plate.holes) == pytest.approx(
        [dimensions["base"]["hole_diameter"]] * 2, abs=0.002
    )
    assert np.linalg.norm(
        [plate.holes[0].x - plate.holes[1].x, plate.holes[0].y - plate.holes[1].y]
    ) == pytest.approx(2 * dimensions["base"]["hole_spacing"], abs=0.002)
    for kind, name in [("sleeve", "spacer"), ("cylinder", "pin")]:
        for key, value in dimensions[name].items():
            assert by_kind[kind].recipe.parameters[key] == pytest.approx(value, abs=0.002)
    assert sorted(o.definition_id for o in document.occurrences).count(by_kind["sleeve"].id) == 2
    reference_doc = fixture["document"]
    reference_by_id = {d.id: d for d in reference_doc.definitions}
    for occurrence in document.occurrences:
        matrix = np.asarray(document.global_transform(occurrence.id))
        expected_occurrence = min(
            reference_doc.occurrences,
            key=lambda o: np.linalg.norm(np.asarray(o.transform)[:3, 3] - matrix[:3, 3]),
        )
        expected = np.asarray(expected_occurrence.transform)
        assert matrix[:3, 3] == pytest.approx(expected[:3, 3], abs=0.002)
        assert abs(matrix[:3, 2] @ expected[:3, 2]) > np.cos(np.deg2rad(0.01))
        if reference_by_id[expected_occurrence.definition_id].recipe.kind == "plate":
            assert abs(matrix[:3, 0] @ expected[:3, 0]) > np.cos(np.deg2rad(0.01))
    result = build_assembly(document, tmp_path / "result")
    assert result["validation"]["valid"]
    assert result["validation"]["roundtrip_valid"]
    assert len(cad.import_step(tmp_path / "result" / "assembly.step").solids()) == 4
    parsed = api.parts(tmp_path / "result" / "assembly.step")
    assert len(parsed) == 3 and sorted(p["instances"] for p in parsed) == [1, 1, 2]
    for definition in document.definitions:
        expected_volume = reference["expected_volumes_mm3"][
            {"plate": "base", "sleeve": "spacer", "cylinder": "pin"}[definition.recipe.kind]
        ]
        assert build_shape(definition.recipe).volume == pytest.approx(expected_volume, rel=2e-5)
        assert definition.evidence["fit"]["valid"]


@pytest.mark.parametrize("units,scale", [("cm", 0.1), ("in", 1 / 25.4)])
def test_declared_scale_is_preserved(tmp_path, units, scale):
    fixture = create_demo(tmp_path / "fixture", 1)
    mesh = trimesh.load_mesh(fixture["input"])
    mesh.apply_scale(scale)
    path = tmp_path / "scaled.stl"
    mesh.export(path)
    document = inspect_stl(path, units)
    plate = next(d for d in document.definitions if d.recipe.kind == "plate")
    assert plate.recipe.parameters["length"] == pytest.approx(73, abs=0.002)
    result = build_assembly(document, tmp_path / "result", reference_mesh=path)
    assert result["validation"]["valid"]
    assert result["validation"]["fit"]["valid"]


def test_reject_dirty_fused_and_unsupported_meshes(tmp_path):
    with pytest.raises(ReconstructionError, match="Declare STL units"):
        inspect_stl(tmp_path / "not-needed.stl", None)
    dirty = trimesh.creation.box()
    dirty.update_faces(np.arange(len(dirty.faces) - 1))
    dirty.export(tmp_path / "dirty.stl")
    with pytest.raises(ReconstructionError, match="closed, manifold"):
        inspect_stl(tmp_path / "dirty.stl", "mm")
    sphere = trimesh.creation.icosphere(subdivisions=2, radius=15)
    sphere.export(tmp_path / "sphere.stl")
    with pytest.raises(ReconstructionError, match="Unsupported solid"):
        inspect_stl(tmp_path / "sphere.stl", "mm")
    fused = cad.Box(40, 30, 5) + cad.Cylinder(5, 20).translate((0, 0, 8))
    cad.export_stl(fused, tmp_path / "fused.stl")
    with pytest.raises(ReconstructionError, match="Unsupported solid"):
        inspect_stl(tmp_path / "fused.stl", "mm")


def test_missing_bore_fails_reference_surface_and_volume_gate(tmp_path):
    fixture = create_demo(tmp_path / "fixture")
    document = fixture["document"]
    from open_assembly.document import Recipe

    sleeve = next(d for d in document.definitions if d.id == "spacer")
    sleeve.recipe = Recipe(
        kind="cylinder",
        parameters={
            key: value for key, value in sleeve.recipe.parameters.items() if key != "inner_diameter"
        },
    )
    result = build_assembly(document, tmp_path / "result", reference_mesh=fixture["input"])
    assert result["validation"]["valid"] is False
    assert result["validation"]["fit"]["valid"] is False


def test_asymmetric_holes_and_independently_rotated_repeated_parts(tmp_path):
    from open_assembly.document import Hole, Recipe
    from scipy.spatial.transform import Rotation

    plate = build_shape(
        Recipe(
            kind="plate",
            parameters=dict(length=65, width=42, height=6),
            holes=[Hole(x=-15, y=8, diameter=6), Hole(x=12, y=-7, diameter=9)],
        )
    )
    sleeve = build_shape(
        Recipe(kind="sleeve", parameters=dict(outer_diameter=11, inner_diameter=5, height=17))
    )
    matrices = []
    for angles, position in [
        ([17, 33, 21], [0, 0, 0]),
        ([11, 61, 45], [-45, 0, 0]),
        ([73, 2, 109], [45, 0, 0]),
    ]:
        matrix = np.eye(4)
        matrix[:3, :3] = Rotation.from_euler("xyz", angles, degrees=True).as_matrix()
        matrix[:3, 3] = position
        matrices.append(matrix)
    path = tmp_path / "asymmetric.stl"
    cad.export_stl(
        cad.Compound(
            children=[
                place_shape(shape, matrix.tolist())
                for shape, matrix in zip([plate, sleeve, sleeve], matrices)
            ]
        ),
        path,
        tolerance=0.008,
        angular_tolerance=0.06,
    )
    document = inspect_stl(path, "mm")
    assert len(document.definitions) == 2 and len(document.occurrences) == 3
    result = build_assembly(document, tmp_path / "result", reference_mesh=path)
    assert result["validation"]["valid"]
    assert result["validation"]["fit"]["valid"]
    assert sorted(p["instances"] for p in result["validation"]["independent_step"]["parts"]) == [
        1,
        2,
    ]


def test_rotated_asymmetric_plates_share_editable_definition(tmp_path):
    from open_assembly.document import Hole, Recipe

    def plate(x, y):
        return build_shape(
            Recipe(
                kind="plate",
                parameters=dict(length=40, width=30, height=3),
                holes=[Hole(x=x, y=y, diameter=5)],
            )
        )

    original = plate(8, 4)
    different = plate(7, 4)
    path = tmp_path / "plates.stl"
    cad.export_stl(
        cad.Compound(
            children=[
                original,
                original.rotate(cad.Axis.Z, 180).translate((60, 0, 0)),
                different.translate((120, 0, 0)),
            ]
        ),
        path,
        tolerance=0.008,
        angular_tolerance=0.06,
    )
    document = inspect_stl(path, "mm")
    assert len(document.definitions) == 2
    ids = [o.definition_id for o in document.occurrences]
    assert ids[0] == ids[1] != ids[2]
    result = build_assembly(document, tmp_path / "original", reference_mesh=path)
    assert result["validation"]["fit"]["valid"]

    shared = next(d for d in document.definitions if d.id == ids[0])
    shared.recipe.parameters["height"] = 4
    result = build_assembly(document, tmp_path / "edited")
    assert result["validation"]["valid"]
    solids = cad.import_step(tmp_path / "edited" / "assembly.step").solids()
    assert sorted(s.bounding_box().size.Z for s in solids) == pytest.approx([3, 4, 4], abs=0.002)


def test_slender_cylinder_reconstructs_and_exports(tmp_path):
    path = tmp_path / "shaft.stl"
    cad.export_stl(cad.Cylinder(2, 500), path, tolerance=0.008, angular_tolerance=0.06)
    document = inspect_stl(path, "mm")
    assert len(document.definitions) == 1
    recipe = document.definitions[0].recipe
    assert recipe.kind == "cylinder"
    assert recipe.parameters == pytest.approx({"outer_diameter": 4, "height": 500}, abs=0.002)
    result = build_assembly(document, tmp_path / "result", reference_mesh=path)
    assert result["validation"]["roundtrip_valid"]
    assert result["validation"]["fit"]["valid"]
    assert len(cad.import_step(tmp_path / "result" / "assembly.step").solids()) == 1
