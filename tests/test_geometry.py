import json
import subprocess
import sys

import build123d as cad
import numpy as np
import pytest
from open_assembly.document import (
    AssemblyDocument,
    InputEvidence,
    Occurrence,
    PartDefinition,
    Recipe,
)
from open_assembly.fixtures import create_demo
from open_assembly.geometry import build_assembly, build_shape, generate_source, mesh_payload
from specify_core import api


def test_single_part_uses_step_product_identity_not_display_name(tmp_path):
    document = AssemblyDocument(
        name="Long cylinder display name",
        input=InputEvidence(name="cylinder", sha256="test", kind="recipe", units="mm"),
        definitions=[
            PartDefinition(
                id="shaft",
                label="Shaft",
                recipe=Recipe(kind="cylinder", parameters={"outer_diameter": 4, "height": 500}),
            )
        ],
        occurrences=[Occurrence(id="shaft_1", definition_id="shaft")],
    )
    result = build_assembly(document, tmp_path / "out")
    assert result["validation"]["valid"]
    assert result["validation"]["independent_step"]["valid"]
    assert api.parts(tmp_path / "out/assembly.step")[0]["product_id"] == "shaft"


def test_step_roundtrip_repeated_definitions_and_independent_parser(tmp_path):
    fixture = create_demo(tmp_path / "fixture", 0)
    document = fixture["document"]
    output = tmp_path / "result"
    result = build_assembly(document, output)
    validation = result["validation"]
    assert validation["valid"] is True
    assert validation["roundtrip_valid"] is True
    assert validation["solid_count"] == validation["expected_solid_count"] == 4
    assert all(row["volume_mm3"] == 0 for row in validation["overlap"])
    actual = cad.import_step(output / "assembly.step")
    expected = fixture["metadata"]["expected_volumes_mm3"]
    assert sorted(s.volume for s in actual.solids()) == pytest.approx(
        sorted([expected["base"], expected["spacer"], expected["spacer"], expected["pin"]]),
        rel=1e-8,
    )
    independent_parts = {part["name"]: part for part in api.parts(output / "assembly.step")}
    assert set(independent_parts) == {"base", "spacer", "pin"}
    assert independent_parts["spacer"]["instances"] == 2
    assert sum(part["instances"] for part in independent_parts.values()) == 4
    for definition_id, part in independent_parts.items():
        reference = [
            np.asarray(o.transform)[:3]
            for o in document.occurrences
            if o.definition_id == definition_id
        ]
        for placement in part["placements"]:
            assert any(np.allclose(placement, matrix, atol=1e-7) for matrix in reference)
    preview = json.loads((output / "preview.json").read_text())
    assert len(preview["parts"]) == 4
    assert all(len(p["vertices"]) > 8 and p["triangles"] for p in preview["parts"])
    assert set(result["artifacts"]) >= {
        "assembly.step",
        "source.py",
        "document.json",
        "preview.json",
        "validation.json",
        "parts/spacer.step",
    }


def test_standalone_source_rebuild_and_two_dimension_edits(tmp_path):
    document = create_demo(tmp_path / "fixture")["document"]
    source = generate_source(document)
    path = tmp_path / "source.py"
    path.write_text(source)
    subprocess.run([sys.executable, str(path)], check=True, capture_output=True, timeout=30)
    initial = cad.import_step(tmp_path / "assembly.step")
    source = source.replace("'length': 70.0", "'length': 77.0").replace(
        "'height': 18.0", "'height': 19.8"
    )
    assert source != path.read_text()
    path.write_text(source)
    subprocess.run([sys.executable, str(path)], check=True, capture_output=True, timeout=30)
    changed = cad.import_step(tmp_path / "assembly.step")
    assert changed.is_valid and len(changed.solids()) == 4
    assert changed.bounding_box().size.X == pytest.approx(77)
    assert changed.volume > initial.volume
    expected_pin = np.pi * 1.5**2 * 19.8
    assert any(s.volume == pytest.approx(expected_pin) for s in changed.solids())
    assert {p["name"]: p["instances"] for p in api.parts(tmp_path / "assembly.step")} == {
        "base": 1,
        "spacer": 2,
        "pin": 1,
    }


def test_parent_transforms_and_overlap_failure(tmp_path):
    shape = Recipe(kind="box", parameters=dict(length=20, width=10, height=5))
    parent = np.eye(4)
    parent[:3, 3] = [10, 2, 0]
    child = np.eye(4)
    child[:3, 3] = [30, 0, 0]
    document = AssemblyDocument(
        input=InputEvidence(name="test", sha256="test", kind="recipe", units="mm"),
        definitions=[PartDefinition(id="box", label="box", recipe=shape)],
        occurrences=[
            Occurrence(id="parent", definition_id="box", transform=parent.tolist()),
            Occurrence(
                id="child", definition_id="box", parent_id="parent", transform=child.tolist()
            ),
        ],
    )
    result = build_assembly(document, tmp_path / "separated")
    assert result["validation"]["valid"]
    preview = json.loads((tmp_path / "separated" / "preview.json").read_text())
    assert np.asarray(preview["parts"][1]["transform"])[:3, 3] == pytest.approx([40, 2, 0])
    document.occurrences[1].transform = np.eye(4).tolist()
    result = build_assembly(document, tmp_path / "overlap")
    assert result["validation"]["valid"] is False
    assert result["validation"]["overlap"][0]["fraction_of_smaller"] == pytest.approx(1)


def test_failed_fit_cannot_be_validated(tmp_path):
    document = create_demo(tmp_path / "fixture")["document"]
    document.definitions[0].evidence["fit"] = {"valid": False, "max_mm": 5}
    assert build_assembly(document, tmp_path / "result")["validation"]["valid"] is False


def test_analytic_solids_and_tessellation():
    recipe = Recipe(kind="sleeve", parameters=dict(outer_diameter=12, inner_diameter=6, height=22))
    shape = build_shape(recipe)
    assert shape.is_valid and len(shape.solids()) == 1
    assert shape.volume == pytest.approx(np.pi * (36 - 9) * 22)
    payload = mesh_payload(shape)
    assert np.asarray(payload["vertices"]).shape[1] == 3
    assert max(max(t) for t in payload["triangles"]) < len(payload["vertices"])
