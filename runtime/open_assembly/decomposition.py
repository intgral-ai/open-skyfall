import base64
import fcntl
import hashlib
import json
import math
import os
import platform
import re
import tempfile
import uuid
import zipfile
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
import trimesh
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from .project import RevisionConflict, _atomic_json

Number = Annotated[float, Field(allow_inf_nan=False, ge=-1e5, le=1e5)]
Vector = tuple[Number, Number, Number]
Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
PALETTE = ["#9caeb1", "#c3b59f", "#a4b3a0", "#a6abc1", "#bca3a1", "#a8b8c8"]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Pose(Record):
    position: Vector = (0.0, 0.0, 0.0)
    rotation: Vector = (0.0, 0.0, 0.0)


class Primitive(Pose):
    id: Identifier | None = None
    kind: Literal["box", "cylinder", "sphere", "shell"]
    # box: xyz; cylinder: radius,height; sphere: radius; shell: lower,upper,height,wall
    dimensions: list[Annotated[float, Field(ge=1e-4, le=1e4, allow_inf_nan=False)]] = Field(
        min_length=1, max_length=4
    )

    @model_validator(mode="after")
    def dimensions_match(self):
        if len(self.dimensions) != {"box": 3, "cylinder": 2, "sphere": 1, "shell": 4}[self.kind]:
            raise ValueError("Primitive dimensions do not match its kind")
        if self.kind == "shell" and self.dimensions[3] >= min(self.dimensions[:2]):
            raise ValueError("Shell wall must be thinner than both radii")
        return self


class ManufacturingIntent(Record):
    process: Literal["unspecified", "machining", "sheet_metal", "additive", "purchased"]
    material: str = Field(min_length=1, max_length=150)
    notes: list[str] = Field(default_factory=list, max_length=20)
    critical_features: list[str] = Field(default_factory=list, max_length=20)


class Definition(Record):
    id: Identifier
    shapes: list[Primitive] = Field(min_length=1, max_length=8)
    manufacturing: ManufacturingIntent | None = None


class Node(Pose):
    id: Identifier
    label: str = Field(min_length=1, max_length=100)
    parent_id: Identifier | None = None
    definition_id: Identifier | None = None
    evidence: Literal["visible", "inferred", "unknown"]
    note: str = Field(min_length=1, max_length=500)


class Observation(Record):
    id: Identifier
    region: tuple[
        Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)],
        Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)],
        Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)],
        Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)],
    ]
    statement: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def nonempty(self):
        if self.region[0] >= self.region[2] or self.region[1] >= self.region[3]:
            raise ValueError("Observation regions need positive width and height")
        if not self.statement.strip():
            raise ValueError("An observation needs a concrete statement")
        return self


class TextObservation(Record):
    kind: Literal["text"]
    id: Identifier
    quote: str = Field(min_length=1, max_length=1000)
    statement: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def nonempty(self):
        if not self.quote.strip() or not self.statement.strip():
            raise ValueError("Text observations need a literal quote and statement")
        return self


class Basis(Record):
    kind: Literal["observed", "estimated", "assumed", "unknown"]
    observations: list[Identifier] = Field(default_factory=list, max_length=128)
    why: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def supported(self):
        if not self.why.strip():
            raise ValueError("A basis needs a concrete reason")
        if self.kind in {"observed", "estimated"} and not self.observations:
            raise ValueError("Observed and estimated bases need source observations")
        return self


class NodeBasis(Record):
    part: Identifier
    placement: Identifier


class Explanation(Record):
    observations: list[Observation | TextObservation] = Field(min_length=1, max_length=128)
    bases: dict[Identifier, Basis] = Field(min_length=1, max_length=256)
    parameters: dict[str, Identifier] = Field(max_length=3000)
    shapes: dict[str, Identifier] = Field(max_length=256)
    nodes: dict[Identifier, NodeBasis] = Field(max_length=64)
    scale: Identifier


class Plan(Record):
    schema_version: Literal[1, 2] = 1
    explanation: Explanation | None = None
    source_sha256: Digest
    units: Literal["relative", "mm"] = "relative"
    scale_note: str = Field(min_length=1, max_length=500)
    assumptions: list[str] = Field(min_length=1, max_length=20)
    definitions: list[Definition] = Field(min_length=1, max_length=32)
    nodes: list[Node] = Field(min_length=2, max_length=64)

    @model_validator(mode="after")
    def hierarchy(self):
        nodes = {node.id: node for node in self.nodes}
        definitions = {item.id: item for item in self.definitions}
        if len(nodes) != len(self.nodes) or len(definitions) != len(self.definitions):
            raise ValueError("Node and definition IDs must be unique")
        roots = [node for node in self.nodes if node.parent_id is None]
        if len(roots) != 1 or roots[0].definition_id:
            raise ValueError("Exactly one assembly root is required")
        used = set()
        for node in self.nodes:
            if node.definition_id:
                if node.definition_id not in definitions:
                    raise ValueError("Unknown part definition")
                used.add(node.definition_id)
            elif not any(child.parent_id == node.id for child in self.nodes):
                raise ValueError("Every leaf must reference geometry")
            if node.parent_id and (
                node.parent_id not in nodes or nodes[node.parent_id].definition_id
            ):
                raise ValueError("Parent must be an existing assembly")
        for node in self.nodes:
            seen = {node.id}
            parent = node.parent_id
            while parent:
                if parent in seen:
                    raise ValueError("Hierarchy contains a cycle")
                seen.add(parent)
                parent = nodes[parent].parent_id
        if used != set(definitions):
            raise ValueError("Every definition must be used")
        if any(len(note) > 500 or not note.strip() for note in self.assumptions):
            raise ValueError("Assumptions must contain 1–500 characters")
        if self.schema_version == 1:
            if self.explanation is not None:
                raise ValueError("Explanations require schema_version 2")
            return self
        explanation = self.explanation
        if explanation is None:
            raise ValueError("Version 2 requires an explanation")
        for definition in self.definitions:
            ids = [shape.id for shape in definition.shapes]
            if None in ids or len(ids) != len(set(ids)):
                raise ValueError("Version 2 shapes need unique stable IDs within each definition")
        observations = {item.id for item in explanation.observations}
        if len(observations) != len(explanation.observations):
            raise ValueError("Observation IDs must be unique")
        for basis in explanation.bases.values():
            if not set(basis.observations) <= observations:
                raise ValueError("Basis references an unknown observation")
        if set(explanation.parameters) != set(parameter_values(self)):
            raise ValueError(
                "Parameter evidence must cover every dimension and pose component exactly"
            )
        expected_shapes = {
            f"{item.id}/{shape.id}" for item in self.definitions for shape in item.shapes
        }
        if set(explanation.shapes) != expected_shapes or set(explanation.nodes) != set(nodes):
            raise ValueError("Every shape and node needs its own explanation reference")
        refs = [explanation.scale, *explanation.parameters.values(), *explanation.shapes.values()]
        refs += [ref for node in explanation.nodes.values() for ref in [node.part, node.placement]]
        if not set(refs) <= set(explanation.bases):
            raise ValueError("Explanation references an unknown basis")
        return self


def parameter_values(plan):
    values = {}
    for definition in plan.definitions:
        for index, shape in enumerate(definition.shapes):
            prefix = f"shape/{definition.id}/{shape.id or f'shape-{index + 1}'}"
            for field in ["dimensions", "position", "rotation"]:
                values.update(
                    {
                        f"{prefix}/{field}/{i}": value
                        for i, value in enumerate(getattr(shape, field))
                    }
                )
    for node in plan.nodes:
        for field in ["position", "rotation"]:
            values.update(
                {
                    f"node/{node.id}/{field}/{i}": value
                    for i, value in enumerate(getattr(node, field))
                }
            )
    return values


class PlanUpdate(Record):
    revision: StrictInt = Field(ge=0)
    plan: Plan
    request_id: Identifier | None = None
    workflow_revision: StrictInt | None = Field(default=None, ge=0)


class InputCommand(Record):
    name: str = Field(default="Untitled object", min_length=1, max_length=100)
    rights: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=20000)
    data_base64: str = Field(default="", max_length=14 * 1024 * 1024)
    workflow: StrictBool = False


def pose_matrix(pose):
    matrix = trimesh.transformations.euler_matrix(*map(math.radians, pose.rotation), axes="sxyz")
    matrix[:3, 3] = pose.position
    return matrix


def _mesh_summary(mesh):
    areas = np.asarray(mesh.area_faces)
    return {
        "vertices": len(mesh.vertices),
        "triangles": len(mesh.faces),
        "bounds": mesh.bounds.tolist(),
        "finite": bool(np.isfinite(mesh.vertices).all()),
        "indexed": bool(
            len(mesh.faces) and (mesh.faces >= 0).all() and (mesh.faces < len(mesh.vertices)).all()
        ),
        "nondegenerate": bool(len(areas) and np.isfinite(areas).all() and (areas > 0).all()),
        "closed_mesh": bool(mesh.is_watertight),
    }


def build_preview(plan, *, trace=None):
    def record(operation, id, **fields):
        if trace is not None:
            trace.append({"id": id, "operation": operation, **fields})

    definitions = {}
    for definition in plan.definitions:
        shapes = []
        for index, shape in enumerate(definition.shapes):
            shape_id = shape.id or f"shape-{index + 1}"
            d = shape.dimensions
            if shape.kind == "box":
                mesh = trimesh.creation.box(extents=d)
            elif shape.kind == "sphere":
                mesh = trimesh.creation.icosphere(subdivisions=2, radius=d[0])
            elif shape.kind == "cylinder":
                mesh = trimesh.creation.cylinder(radius=d[0], height=d[1], sections=48)
            else:
                lower, upper, height, wall = d
                mesh = trimesh.creation.revolve(
                    [
                        [lower, -height / 2],
                        [upper, height / 2],
                        [upper - wall, height / 2],
                        [lower - wall, -height / 2],
                        [lower, -height / 2],
                    ],
                    sections=48,
                )
            record(
                "create_shape",
                f"shape/{definition.id}/{shape_id}/create",
                definition_id=definition.id,
                shape_id=shape_id,
                parameters={
                    "kind": shape.kind,
                    "dimensions": list(d),
                    "radial_sections": 48 if shape.kind in {"cylinder", "shell"} else None,
                    "sphere_subdivisions": 2 if shape.kind == "sphere" else None,
                },
                outputs=_mesh_summary(mesh) if trace is not None else {},
            )
            mesh.apply_transform(pose_matrix(shape))
            record(
                "shape_transform",
                f"shape/{definition.id}/{shape_id}/pose",
                definition_id=definition.id,
                shape_id=shape_id,
                parameters={"position": list(shape.position), "rotation": list(shape.rotation)},
                world_transform=pose_matrix(shape).tolist(),
                outputs=_mesh_summary(mesh) if trace is not None else {},
            )
            shapes.append(mesh)
        definitions[definition.id] = trimesh.util.concatenate(shapes)
        record(
            "concatenate_definition",
            f"definition/{definition.id}",
            definition_id=definition.id,
            parameters={"shape_count": len(shapes)},
            outputs=_mesh_summary(definitions[definition.id]) if trace is not None else {},
        )
    nodes = {node.id: node for node in plan.nodes}
    matrices = {}

    def world(node):
        if node.id not in matrices:
            local = pose_matrix(node)
            matrices[node.id] = world(nodes[node.parent_id]) @ local if node.parent_id else local
        return matrices[node.id]

    parts = []
    for node in plan.nodes:
        if not node.definition_id:
            continue
        mesh = definitions[node.definition_id].copy()
        mesh.apply_transform(world(node))
        record(
            "place_occurrence",
            f"node/{node.id}",
            node_id=node.id,
            definition_id=node.definition_id,
            parameters={
                "parent_id": node.parent_id,
                "position": list(node.position),
                "rotation": list(node.rotation),
            },
            world_transform=world(node).tolist(),
            outputs=_mesh_summary(mesh) if trace is not None else {},
        )
        color_hash = 2166136261
        for character in node.id:
            color_hash = ((color_hash ^ ord(character)) * 16777619) & 0xFFFFFFFF
        color = PALETTE[color_hash % len(PALETTE)]
        parts.append(
            {
                "id": node.id,
                "definition_id": node.definition_id,
                "color": color,
                "vertices": mesh.vertices.tolist(),
                "triangles": mesh.faces.tolist(),
                "bounds": mesh.bounds.tolist(),
            }
        )
    bounds = np.array([part["bounds"] for part in parts])
    low, high = bounds[:, 0].min(axis=0), bounds[:, 1].max(axis=0)
    extent = float((high - low).max())
    if not math.isfinite(extent) or extent < 1e-6:
        raise ValueError("Assembly has no usable extent")
    result = {
        "parts": parts,
        "normalization": {"center": ((low + high) / 2).tolist(), "scale": 4 / extent},
        "coordinates": "Right-handed Z-up; raw vertices retain plan units and placements",
    }
    record(
        "normalize_view",
        "scene/normalization",
        parameters=result["normalization"],
        outputs={"part_count": len(parts), "raw_bounds": [low.tolist(), high.tolist()]},
    )
    return result


class SourceBinding(Record):
    sha256: Digest
    reference_sha256: Digest
    reference_size: tuple[
        Annotated[StrictInt, Field(ge=1, le=1600)], Annotated[StrictInt, Field(ge=1, le=1600)]
    ]
    rights: str = Field(min_length=1, max_length=500)


class TextSourceBinding(Record):
    kind: Literal["text"]
    sha256: Digest
    rights: str = Field(min_length=1, max_length=500)


class BriefBinding(Record):
    text: str = Field(min_length=1, max_length=20000)
    sha256: Digest

    @model_validator(mode="after")
    def integrity(self):
        if _digest(self.text.encode()) != self.sha256:
            raise ValueError("Brief text does not match its hash")
        return self


class ConceptProgram(Record):
    format: Literal["open-skyfall-concept/1"] = "open-skyfall-concept/1"
    project_id: str = Field(pattern=r"^(?:[0-9a-f]{32}|example)$")
    revision: StrictInt = Field(ge=1)
    source: SourceBinding | TextSourceBinding
    brief: BriefBinding | None = None
    runtime: dict[str, str]
    plan: Plan

    @model_validator(mode="after")
    def same_source(self):
        if self.plan.source_sha256 != self.source.sha256:
            raise ValueError("Program and Plan reference different sources")
        if self.plan.explanation:
            for observation in self.plan.explanation.observations:
                if isinstance(observation, TextObservation):
                    if self.brief is None or observation.quote not in self.brief.text:
                        raise ValueError("Text observation is not a literal quote from the brief")
                elif isinstance(self.source, TextSourceBinding):
                    raise ValueError("Text-only input has no image regions")
        return self


def _json_bytes(value):
    return (
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )
        + "\n"
    ).encode()


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def runtime_profile():
    return {
        "recipe": "concept-mesh/2",
        "engine_sha256": _digest(Path(__file__).read_bytes()),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "trimesh": trimesh.__version__,
    }


def _analysis(program, preview, trace):
    explanation = program.plan.explanation
    count = len(parameter_values(program.plan))
    complete = explanation is not None
    kinds = {kind: 0 for kind in ["observed", "estimated", "assumed", "unknown"]}
    if explanation:
        for ref in explanation.parameters.values():
            kinds[explanation.bases[ref].kind] += 1
    mesh_steps = [step for step in trace if step["operation"] == "place_occurrence"]
    valid_mesh = all(
        step["outputs"]["finite"]
        and step["outputs"]["indexed"]
        and step["outputs"]["nondegenerate"]
        for step in mesh_steps
    )
    if not valid_mesh or len(mesh_steps) != len(preview["parts"]):
        raise ValueError("Generated part meshes contain invalid or degenerate geometry")
    checks = [
        {
            "scope": "source_integrity",
            "outcome": "pass",
            "detail": "Original and reference bytes match their recorded hashes."
            if isinstance(program.source, SourceBinding)
            else "Literal UTF-8 brief bytes match their recorded hash; no image was supplied.",
        },
        {
            "scope": "hierarchy",
            "outcome": "pass",
            "detail": "One assembly root, valid reusable definitions and acyclic parent-relative placements.",
        },
        {
            "scope": "explanation_coverage",
            "outcome": "pass" if complete else "unchecked",
            "detail": f"All {count} parameter components have explicit bases; their truth is not certified."
            if complete
            else "Legacy plan has no complete parameter evidence.",
        },
        {
            "scope": "mesh",
            "outcome": "pass",
            "detail": f"{len(mesh_steps)} independently placed meshes have finite vertices and nondegenerate indexed triangles. Concatenation is not solid union.",
        },
        {
            "scope": "replay",
            "outcome": "unchecked",
            "detail": "Run the exported bundle in a fresh output directory for a separate reproduction receipt.",
        },
        {
            "scope": "source_fidelity",
            "outcome": "unchecked",
            "detail": "A source region and a replay do not establish geometric fidelity to the image.",
        },
        {
            "scope": "native_cad",
            "outcome": "unchecked",
            "detail": "Concept meshes do not establish native CAD construction or STEP validity.",
        },
        {
            "scope": "manufacturing",
            "outcome": "unchecked",
            "detail": "Manufacturing requirements and acceptance were not evaluated.",
        },
    ]
    return {
        "binding": {
            "project_id": program.project_id,
            "revision": program.revision,
            "program_sha256": _digest(_json_bytes(program.model_dump(mode="json"))),
            "runtime": program.runtime,
        },
        "coverage": {
            "status": "complete" if complete else "incomplete",
            "parameter_count": count,
            "explained": count if complete else 0,
            "kinds": kinds,
        },
        "checks": checks,
        "trace": trace,
    }


REPLAY_SCRIPT = """import argparse
import json
from pathlib import Path
from open_assembly.decomposition import replay_bundle

parser = argparse.ArgumentParser()
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
report = replay_bundle(Path(__file__).parent, args.out)
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["outcome"] == "pass" else 2)
"""


def _check_source(program, source, reference):
    if _digest(source) != program.source.sha256:
        raise ValueError("Program source bytes do not match their binding")
    if isinstance(program.source, TextSourceBinding):
        if reference is not None or not program.brief or source.decode() != program.brief.text:
            raise ValueError("Text source must retain the literal brief without a fake image")
    elif reference is None or _digest(reference) != program.source.reference_sha256:
        raise ValueError("Program reference bytes do not match their binding")
    else:
        with Image.open(BytesIO(reference)) as image:
            if tuple(image.size) != program.source.reference_size:
                raise ValueError("Reference image dimensions do not match the program")


def _revision_files(program, source, reference):
    _check_source(program, source, reference)
    trace = []
    preview = build_preview(program.plan, trace=trace)
    analysis = _analysis(program, preview, trace)
    files = {
        "program.json": _json_bytes(program.model_dump(mode="json")),
        "preview.json": _json_bytes(preview),
        "trace.json": _json_bytes(trace),
        "checks.json": _json_bytes(analysis),
        "source.bin": source,
        "replay.py": REPLAY_SCRIPT.encode(),
    }
    if reference is not None:
        files["reference.png"] = reference
    manifest = {
        "format": "open-skyfall-bundle/1",
        "binding": analysis["binding"],
        "files": {name: {"sha256": _digest(raw), "bytes": len(raw)} for name, raw in files.items()},
    }
    files["bundle-manifest.json"] = _json_bytes(manifest)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in files.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw)
    files["bundle.zip"] = buffer.getvalue()
    return files, analysis


BUNDLE_NAMES = {
    "program.json",
    "preview.json",
    "trace.json",
    "checks.json",
    "source.bin",
    "reference.png",
    "replay.py",
    "bundle-manifest.json",
}
MAX_BUNDLE_BYTES = 80 * 1024 * 1024


class ProgramBinding(Record):
    project_id: str = Field(pattern=r"^(?:[0-9a-f]{32}|example)$")
    revision: StrictInt = Field(ge=1)
    program_sha256: Digest
    runtime: dict[str, str]


class ArtifactDigest(Record):
    sha256: Digest
    bytes: StrictInt = Field(ge=0, le=MAX_BUNDLE_BYTES)


class BundleManifest(Record):
    format: Literal["open-skyfall-bundle/1"]
    binding: ProgramBinding
    files: dict[str, ArtifactDigest] = Field(max_length=8)


def _read_bundle(path):
    path = Path(path)
    if path.is_dir():
        paths = {
            name: path / name
            for name in BUNDLE_NAMES
            if name != "reference.png" or (path / name).exists() or (path / name).is_symlink()
        }
        if any(file.is_symlink() or not file.is_file() for file in paths.values()):
            raise ValueError("Bundle files must be regular files")
        if sum(file.stat().st_size for file in paths.values()) > MAX_BUNDLE_BYTES:
            raise ValueError("Bundle exceeds the size limit")
        files = {name: file.read_bytes() for name, file in paths.items()}
    else:
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if len(entries) != len({entry.filename for entry in entries}) or {
                    entry.filename for entry in entries
                } not in [BUNDLE_NAMES, BUNDLE_NAMES - {"reference.png"}]:
                    raise ValueError("Bundle has missing, duplicate or unexpected filenames")
                if sum(entry.file_size for entry in entries) > MAX_BUNDLE_BYTES:
                    raise ValueError("Bundle exceeds the size limit")
                files = {entry.filename: archive.read(entry.filename) for entry in entries}
        except zipfile.BadZipFile as exc:
            raise ValueError("Bundle archive could not be decoded") from exc
    if sum(map(len, files.values())) > MAX_BUNDLE_BYTES:
        raise ValueError("Bundle exceeds the size limit")
    manifest = BundleManifest.model_validate_json(files["bundle-manifest.json"]).model_dump(
        mode="json"
    )
    if set(manifest["files"]) != set(files) - {"bundle-manifest.json"}:
        raise ValueError("Unsupported or incomplete bundle manifest")
    for name, recorded in manifest["files"].items():
        if recorded != {"sha256": _digest(files[name]), "bytes": len(files[name])}:
            raise ValueError(f"Bundle artifact integrity failed: {name}")
    if files["replay.py"] != REPLAY_SCRIPT.encode():
        raise ValueError("Bundle replay.py does not match the installed reviewed runner")
    return files, manifest


def _same_geometry(expected, actual):
    try:
        if len(expected["parts"]) != len(actual["parts"]):
            return False
        for old, new in zip(expected["parts"], actual["parts"], strict=True):
            if any(old[key] != new[key] for key in ["id", "definition_id", "triangles", "color"]):
                return False
            for key in ["vertices", "bounds"]:
                left, right = np.asarray(old[key]), np.asarray(new[key])
                if (
                    left.shape != right.shape
                    or not np.isfinite(left).all()
                    or not np.allclose(left, right, rtol=0, atol=1e-9)
                ):
                    return False
        for key in ["center", "scale"]:
            if not np.allclose(
                expected["normalization"][key], actual["normalization"][key], rtol=0, atol=1e-9
            ):
                return False
        return expected["coordinates"] == actual["coordinates"]
    except (KeyError, TypeError, ValueError):
        return False


def _same_values(left, right):
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _same_values(value, right[key]) for key, value in left.items()
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _same_values(a, b) for a, b in zip(left, right, strict=True)
        )
    if type(left) is float and type(right) is float:
        return math.isfinite(left) and math.isclose(left, right, rel_tol=0, abs_tol=1e-9)
    return type(left) is type(right) and left == right


def replay_bundle(bundle, output):
    """Validate the exported data and reproduce geometry without executing bundled code."""
    output = Path(output)
    if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
        raise ValueError("Replay output must be an empty directory")
    files, manifest = _read_bundle(bundle)
    program = ConceptProgram.model_validate_json(files["program.json"])
    installed_runtime = runtime_profile()
    if program.runtime != installed_runtime:
        fields = sorted(
            key
            for key in program.runtime.keys() | installed_runtime.keys()
            if program.runtime.get(key) != installed_runtime.get(key)
        )
        raise ValueError(
            f"Unsupported runtime profile ({', '.join(fields)}); replay needs the exact recorded runtime"
        )
    recorded_analysis = json.loads(files["checks.json"])
    if not isinstance(recorded_analysis, dict) or manifest["binding"] != recorded_analysis.get(
        "binding"
    ):
        raise ValueError("Mixed revision bindings in bundle checks")
    expected_program = _digest(files["program.json"])
    binding = manifest["binding"]
    if binding != {
        "project_id": program.project_id,
        "revision": program.revision,
        "program_sha256": expected_program,
        "runtime": program.runtime,
    }:
        raise ValueError("Program binding does not match the bundle")
    _check_source(program, files["source.bin"], files.get("reference.png"))
    trace = []
    preview = build_preview(program.plan, trace=trace)
    expected = json.loads(files["preview.json"])
    same = _same_geometry(expected, preview)
    same_trace = _same_values(json.loads(files["trace.json"]), trace)
    analysis = _analysis(program, preview, trace)
    same_checks = _same_values(recorded_analysis, analysis)
    passed = same and same_trace and same_checks
    analysis["checks"] = [check for check in analysis["checks"] if check["scope"] != "replay"]
    analysis["checks"].append(
        {
            "scope": "replay",
            "outcome": "pass" if passed else "fail",
            "detail": "Ordered identities and indices are exact; vertices, bounds and normalization use rtol=0, atol=1e-9. Actual operation traces must match.",
        }
    )
    report = {
        "outcome": "pass" if passed else "fail",
        "binding": binding,
        "source_sha256": _digest(files["source.bin"]),
        "reference_sha256": _digest(files["reference.png"]) if "reference.png" in files else None,
        "expected_preview_sha256": _digest(files["preview.json"]),
        "actual_preview_sha256": _digest(_json_bytes(preview)),
        "expected_trace_sha256": _digest(files["trace.json"]),
        "actual_trace_sha256": _digest(_json_bytes(trace)),
        "geometry_matches": same,
        "trace_matches": same_trace,
        "stored_checks_match": same_checks,
        "coverage": analysis["coverage"],
        "checks": analysis["checks"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".replay-", dir=output.parent) as temporary:
        stage = Path(temporary)
        (stage / "preview.json").write_bytes(_json_bytes(preview))
        (stage / "trace.json").write_bytes(_json_bytes(trace))
        _atomic_json(stage / "replay-report.json", report)
        os.rename(stage, output)
    return report


class DecompositionStore:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve() / "decompositions"
        self.root.mkdir(parents=True, exist_ok=True)

    def directory(self, project_id):
        if not re.fullmatch(r"[0-9a-f]{32}", project_id):
            raise ValueError("Invalid decomposition ID")
        path = self.root / project_id
        if not path.is_dir() or path.is_symlink():
            raise FileNotFoundError("Decomposition does not exist")
        return path

    @contextmanager
    def locked(self, project_id):
        directory = self.directory(project_id)
        with (directory / ".lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield directory
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def create(self, raw, name, rights, *, description="", workflow=False):
        if not isinstance(description, str) or len(description) > 20000:
            raise ValueError("Description must contain at most 20000 characters")
        if not raw:
            if not description.strip():
                raise ValueError("Supply an image or a description")
            return self.create_text(name, rights, description)
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError("Image must contain 1 byte to 10 MB")
        if not isinstance(rights, str) or not 1 <= len(rights.strip()) <= 500:
            raise ValueError("Record the permission or license for this input")
        try:
            with Image.open(BytesIO(raw)) as image:
                if image.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ValueError("Use a PNG, JPEG or WebP image")
                if image.width * image.height > 24_000_000:
                    raise ValueError("Image exceeds 24 megapixels")
                image.load()
                preview = ImageOps.exif_transpose(image).convert("RGB")
                preview.thumbnail((1600, 1600))
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ValueError("Image could not be decoded") from exc
        project_id = uuid.uuid4().hex
        directory = self.root / project_id
        directory.mkdir()
        (directory / "source.bin").write_bytes(raw)
        preview.save(directory / "reference.png")
        manifest = {
            "id": project_id,
            "kind": "decomposition",
            "name": str(name)[:100],
            "revision": 0,
            "state": "awaiting_plan",
            "plan": None,
            "source": {
                "sha256": hashlib.sha256(raw).hexdigest(),
                "rights": rights,
                "reference_size": list(preview.size),
                "reference_sha256": hashlib.sha256(
                    (directory / "reference.png").read_bytes()
                ).hexdigest(),
            },
            "artifacts": {},
            "limitations": "Agent-authored concept geometry; source fidelity, hidden structure and manufacturing suitability are unverified.",
        }
        if workflow or description:
            from .decomposition_workflow import initialize

            initialize(manifest, description)
        _atomic_json(directory / "manifest.json", manifest)
        return manifest

    def create_text(self, name, rights, description):
        if not isinstance(rights, str) or not 1 <= len(rights.strip()) <= 500:
            raise ValueError("Record the permission or license for this input")
        project_id = uuid.uuid4().hex
        directory = self.root / project_id
        directory.mkdir()
        raw = description.encode()
        (directory / "source.bin").write_bytes(raw)
        manifest = {
            "id": project_id,
            "kind": "decomposition",
            "name": str(name)[:100],
            "revision": 0,
            "state": "awaiting_plan",
            "plan": None,
            "source": {"kind": "text", "sha256": _digest(raw), "rights": rights},
            "artifacts": {},
            "limitations": "Text brief only; dimensions and hidden geometry need explicit design choices.",
        }
        from .decomposition_workflow import initialize

        initialize(manifest, description)
        _atomic_json(directory / "manifest.json", manifest)
        return manifest

    def get(self, project_id):
        return json.loads((self.directory(project_id) / "manifest.json").read_text())

    def reference(self, project_id):
        directory = self.directory(project_id)
        source = self.get(project_id)["source"]
        if source.get("kind") == "text":
            raise FileNotFoundError("This project has a text brief, not a reference image")
        for filename, digest in [
            ("source.bin", source["sha256"]),
            ("reference.png", source["reference_sha256"]),
        ]:
            path = directory / filename
            if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("Source image integrity check failed")
        return directory / "reference.png"

    def list(self):
        return [
            self.get(path.name)
            for path in sorted(self.root.iterdir())
            if path.is_dir() and not path.is_symlink() and (path / "manifest.json").is_file()
        ]

    def update(self, project_id, payload):
        command = PlanUpdate.model_validate(payload)
        with self.locked(project_id) as directory:
            current = self.get(project_id)
            if command.revision != current["revision"]:
                raise RevisionConflict("Revision changed; read the current decomposition first")
            if "workflow" in current and command.workflow_revision != current["workflow_revision"]:
                raise RevisionConflict("Workflow changed; read the current review state first")
            if command.plan.source_sha256 != current["source"]["sha256"]:
                raise ValueError("Plan belongs to a different source image")
            from .decomposition_workflow import reconcile, validate_plan_transition

            validate_plan_transition(current, command.request_id, command.plan)
            revision = current["revision"] + 1
            is_text = current["source"].get("kind") == "text"
            reference = None if is_text else self.reference(project_id).read_bytes()
            source = dict(current["source"])
            if reference is not None:
                with Image.open(BytesIO(reference)) as image:
                    source["reference_size"] = list(image.size)
            brief = current.get("workflow", {}).get("brief")
            program = ConceptProgram(
                project_id=project_id,
                revision=revision,
                source=TextSourceBinding.model_validate(source)
                if is_text
                else SourceBinding.model_validate(source),
                brief=BriefBinding.model_validate(brief) if brief and brief["text"] else None,
                runtime=runtime_profile(),
                plan=command.plan,
            )
            files, analysis = _revision_files(
                program, (directory / "source.bin").read_bytes(), reference
            )
            parent = directory / "revisions"
            parent.mkdir(exist_ok=True)
            relative = f"revisions/{revision}-{uuid.uuid4().hex}"
            snapshot = {key: value for key, value in current.items() if key != "revision_records"}
            snapshot.update(
                revision=revision,
                state="ready",
                source=source,
                plan=command.plan.model_dump(mode="json"),
                artifacts={f"{relative}/{name}": _digest(raw) for name, raw in files.items()},
                preview=f"{relative}/preview.json",
                program=f"{relative}/program.json",
                bundle=f"{relative}/bundle.zip",
                analysis=analysis,
            )
            reconcile(snapshot, previous=current, request_id=command.request_id)
            with tempfile.TemporaryDirectory(prefix=".pending-", dir=parent) as temporary:
                stage = Path(temporary)
                for name, raw in files.items():
                    (stage / name).write_bytes(raw)
                _atomic_json(stage / "record.json", snapshot)
                record_sha = _digest((stage / "record.json").read_bytes())
                os.rename(stage, directory / relative)
            records = dict(current.get("revision_records", {}))
            records[str(revision)] = {"path": f"{relative}/record.json", "sha256": record_sha}
            current = {**snapshot, "revision_records": records}
            _atomic_json(directory / "manifest.json", current)
            return current

    def _artifact(self, snapshot, name):
        if name not in snapshot["artifacts"]:
            raise FileNotFoundError("Artifact is not part of the current revision")
        directory = self.directory(snapshot["id"])
        path = directory / name
        if (
            path.is_symlink()
            or not path.resolve().is_relative_to(directory)
            or hashlib.sha256(path.read_bytes()).hexdigest() != snapshot["artifacts"][name]
        ):
            raise ValueError("Artifact integrity check failed")
        return path

    def artifact(self, project_id, name):
        return self._artifact(self.get(project_id), name)

    def revision(self, project_id, revision):
        current = self.get(project_id)
        record = current.get("revision_records", {}).get(str(revision))
        if (
            isinstance(revision, bool)
            or not isinstance(revision, int)
            or revision < 1
            or not record
        ):
            raise FileNotFoundError("Accepted revision has no retained program")
        directory = self.directory(project_id)
        path = directory / record["path"]
        if (
            path.is_symlink()
            or not path.resolve().is_relative_to(directory)
            or _digest(path.read_bytes()) != record["sha256"]
        ):
            raise ValueError("Revision record integrity check failed")
        snapshot = json.loads(path.read_text())
        if snapshot["id"] != project_id or snapshot["revision"] != revision:
            raise ValueError("Revision record has a mismatched identity")
        return snapshot

    def bundle(self, project_id, revision=None):
        snapshot = self.get(project_id) if revision is None else self.revision(project_id, revision)
        if "bundle" not in snapshot:
            raise FileNotFoundError("This revision has no replay bundle")
        return self._artifact(snapshot, snapshot["bundle"])

    def request(self, method, path, payload=None):
        payload = payload or {}
        if path == "/api/decomposition-anatomy-example" and method == "GET":
            from .decomposition_workflow import anatomy_example

            return anatomy_example(self)
        if "/workflow/" in path:
            from .decomposition_workflow import DecompositionWorkflow

            return DecompositionWorkflow(self).request(method, path, payload)
        if path == "/api/decomposition-example" and method == "GET":
            return example()
        if path == "/api/decomposition-schema" and method == "GET":
            return {"schema": PlanUpdate.model_json_schema()}
        if path == "/api/decompositions":
            if method == "GET":
                return {"projects": self.list()}
            if method == "POST":
                command = InputCommand.model_validate(payload)
                return self.create(
                    base64.b64decode(command.data_base64, validate=True),
                    command.name,
                    command.rights,
                    description=command.description,
                    workflow=command.workflow,
                )
        match = re.fullmatch(
            r"/api/decompositions/([0-9a-f]{32})(?:/(plan|reference|bundle|revisions/[0-9]+(?:/bundle)?|artifacts/.+))?",
            path,
        )
        if match:
            project_id, action = match.groups()
            if method == "PUT" and action == "plan":
                return self.update(project_id, payload)
            if method != "GET":
                raise ValueError("Unsupported decomposition operation")
            if not action:
                return self.get(project_id)
            if action == "reference":
                source = self.reference(project_id)
                return {
                    "filename": "reference.png",
                    "mime_type": "image/png",
                    "data_base64": base64.b64encode(source.read_bytes()).decode(),
                }
            if action.startswith("revisions/"):
                parts = action.split("/")
                if len(parts) == 2:
                    return self.revision(project_id, int(parts[1]))
                artifact = self.bundle(project_id, int(parts[1]))
            elif action == "bundle":
                artifact = self.bundle(project_id)
            elif action.startswith("artifacts/"):
                artifact = self.artifact(project_id, action[10:])
            else:
                raise ValueError("Unsupported decomposition operation")
            if artifact.suffix == ".json":
                return json.loads(artifact.read_text())
            return {
                "filename": artifact.name,
                "mime_type": "application/zip"
                if artifact.suffix == ".zip"
                else "application/octet-stream",
                "data_base64": base64.b64encode(artifact.read_bytes()).decode(),
            }
        raise ValueError("Unsupported decomposition operation")


def example():
    directory = Path(__file__).resolve().parents[2] / "examples" / "decomposition"
    if not directory.is_dir():
        directory = Path(__file__).parent / "data" / "decomposition"
    raw = (directory / "desk-lamp.png").read_bytes()
    plan = Plan.model_validate_json((directory / "plan.json").read_text())
    if hashlib.sha256(raw).hexdigest() != plan.source_sha256:
        raise ValueError("Example reference hash mismatch")
    return {
        "id": "example",
        "kind": "decomposition",
        "name": "Desk lamp",
        "revision": 1,
        "state": "ready",
        "plan": plan.model_dump(),
        "preview_data": build_preview(plan),
        "source": {"sha256": plan.source_sha256, "rights": "Original MIT illustration"},
        "reference_base64": base64.b64encode(raw).decode(),
        "limitations": "Authored reference example · agent-interpreted concept geometry",
    }
