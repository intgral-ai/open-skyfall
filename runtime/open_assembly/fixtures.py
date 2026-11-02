import hashlib
import json
from pathlib import Path

import build123d as cad
import numpy as np
from scipy.spatial.transform import Rotation

from .document import AssemblyDocument, Hole, InputEvidence, Occurrence, PartDefinition, Recipe
from .geometry import build_shape, place_shape


def create_demo(directory, variant=0) -> dict:
    if not isinstance(variant, int) or not 0 <= variant < 10:
        raise ValueError("Fixture variant must be an integer between 0 and 9")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    length, width, thickness = 70 + 3 * variant, 44 + 2 * variant, 5 + 0.2 * variant
    hole_spacing, bore, outer, sleeve_height = (
        20 + variant,
        4 + 0.1 * variant,
        9 + 0.2 * variant,
        12 + 0.5 * variant,
    )
    pin_diameter, pin_height = 3 + 0.05 * variant, 18 + 0.3 * variant
    definitions = [
        PartDefinition(
            id="base",
            label="Drilled rectangular base",
            recipe=Recipe(
                kind="plate",
                parameters=dict(length=length, width=width, height=thickness),
                holes=[
                    Hole(x=-hole_spacing, diameter=outer + 1),
                    Hole(x=hole_spacing, diameter=outer + 1),
                ],
            ),
        ),
        PartDefinition(
            id="spacer",
            label="Repeated sleeve",
            recipe=Recipe(
                kind="sleeve",
                parameters=dict(outer_diameter=outer, inner_diameter=bore, height=sleeve_height),
            ),
        ),
        PartDefinition(
            id="pin",
            label="Alignment pin",
            recipe=Recipe(
                kind="cylinder", parameters=dict(outer_diameter=pin_diameter, height=pin_height)
            ),
        ),
    ]
    rotation = Rotation.from_euler(
        "xyz", [0, 0, 0] if variant < 3 else [variant * 7, variant * 11, variant * 13], degrees=True
    ).as_matrix()
    global_offset = np.array([3 * variant, -2 * variant, variant])
    positions = [
        ("base", [0, 0, 0]),
        ("spacer", [-hole_spacing, 0, thickness / 2 + sleeve_height / 2 + 0.7]),
        ("spacer", [hole_spacing, 0, thickness / 2 + sleeve_height / 2 + 0.7]),
        ("pin", [0, width / 2 + 7, 0]),
    ]
    occurrences = []
    for index, (definition_id, position) in enumerate(positions):
        transform = np.eye(4)
        transform[:3, :3] = rotation
        transform[:3, 3] = rotation @ position + global_offset
        occurrences.append(
            Occurrence(
                id=f"{definition_id}_{index + 1}",
                definition_id=definition_id,
                transform=transform.tolist(),
            )
        )
    shapes = {d.id: build_shape(d.recipe) for d in definitions}
    instances = [place_shape(shapes[o.definition_id], o.transform) for o in occurrences]
    input_path = directory / "input.stl"
    cad.export_stl(
        cad.Compound(children=instances), input_path, tolerance=0.008, angular_tolerance=0.06
    )
    document = AssemblyDocument(
        name=f"Self-authored fixture {variant}",
        input=InputEvidence(
            name="input.stl",
            sha256=hashlib.sha256(input_path.read_bytes()).hexdigest(),
            kind="stl",
            units="mm",
        ),
        definitions=definitions,
        occurrences=occurrences,
    )
    reference = {
        "variant": variant,
        "authorship": "Project-authored analytic fixture, CC0-1.0",
        "units": "mm",
        "definition_count": 3,
        "occurrence_count": 4,
        "dimensions": {
            "base": dict(
                length=length,
                width=width,
                height=thickness,
                hole_spacing=hole_spacing,
                hole_diameter=outer + 1,
            ),
            "spacer": dict(outer_diameter=outer, inner_diameter=bore, height=sleeve_height),
            "pin": dict(outer_diameter=pin_diameter, height=pin_height),
        },
        "expected_volumes_mm3": {
            "base": length * width * thickness - 2 * np.pi * ((outer + 1) / 2) ** 2 * thickness,
            "spacer": np.pi * (outer**2 - bore**2) / 4 * sleeve_height,
            "pin": np.pi * pin_diameter**2 / 4 * pin_height,
        },
        "transforms": {o.id: o.transform for o in occurrences},
    }
    (directory / "reference.json").write_text(json.dumps(reference, indent=2))
    (directory / "ground_truth.json").write_text(document.model_dump_json(indent=2))
    return {
        "input": str(input_path),
        "input_path": str(input_path),
        "document": document,
        "metadata": reference,
    }


def create_cohort(directory, count=10):
    if not isinstance(count, int) or not 1 <= count <= 10:
        raise ValueError("The self-authored development cohort has 1 to 10 variants")
    return [create_demo(Path(directory) / f"case_{index:02d}", index) for index in range(count)]
