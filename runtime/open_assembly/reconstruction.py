import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh

from .document import AssemblyDocument, Hole, InputEvidence, Occurrence, PartDefinition, Recipe
from .geometry import build_shape, mesh_payload, surface_fit


class ReconstructionError(ValueError):
    """The input does not support a measured bounded reconstruction."""


@dataclass
class FittedPart:
    recipe: Recipe
    transform: list[list[float]]
    fit: dict


def _circle(points, tolerance):
    xy = np.unique(np.round(points[:, :2], 7), axis=0)
    if len(xy) < 12:
        raise ReconstructionError("Circular wall needs at least 12 observed segments")
    coefficients, _, rank, _ = np.linalg.lstsq(
        np.column_stack((2 * xy, np.ones(len(xy)))), (xy * xy).sum(axis=1), rcond=None
    )
    if rank != 3:
        raise ReconstructionError("Circular wall is degenerate")
    center = coefficients[:2]
    radius = np.sqrt(coefficients[2] + center @ center)
    residual = np.max(np.abs(np.linalg.norm(xy - center, axis=1) - radius))
    angles = np.sort(np.arctan2(xy[:, 1] - center[1], xy[:, 0] - center[0]))
    gaps = np.diff(np.r_[angles, angles[0] + 2 * np.pi])
    if not np.isfinite(radius) or radius <= 0 or residual > tolerance or gaps.max() > 0.55:
        raise ReconstructionError(
            "Wall is not a complete circular cylinder within fitting tolerance"
        )
    return center, float(radius), float(residual)


def _wall_groups(mesh, indices):
    if not len(indices):
        return []
    wall = mesh.submesh([indices], append=True, repair=False)
    return wall.split(only_watertight=False, repair=False)


def _frame_candidates(mesh):
    normals = np.asarray(mesh.face_normals).copy()
    signs = normals[np.arange(len(normals)), np.argmax(np.abs(normals), axis=1)]
    normals[signs < 0] *= -1
    _, groups = np.unique(np.round(normals, 3), axis=0, return_inverse=True)
    areas = np.bincount(groups, weights=mesh.area_faces)
    vectors = np.column_stack(
        [np.bincount(groups, weights=normals[:, axis] * mesh.area_faces) for axis in range(3)]
    )
    directions = [
        [vector / np.linalg.norm(vector), float(area)] for vector, area in zip(vectors, areas)
    ]
    directions.sort(key=lambda entry: -entry[1])
    normal_moment = (normals * mesh.area_faces[:, None]).T @ normals
    _, axes = np.linalg.eigh(normal_moment)
    axial_directions = [n for n, _ in directions[:3]] + [axes[:, 0]]
    for z in axial_directions:
        perpendicular = [n for n, _ in directions if abs(n @ z) < 1e-5]
        x = perpendicular[0] if perpendicular else np.eye(3)[np.argmin(np.abs(z))]
        x = x - (x @ z) * z
        x /= np.linalg.norm(x)
        y = np.cross(z, x)
        extents = np.ptp(np.asarray(mesh.vertices) @ np.column_stack((x, y, z)), axis=0)
        if extents[0] < extents[1]:
            x, y = y, -x
        yield np.column_stack((x, y, z))


def _recipe_in_frame(mesh, rotation):
    coordinates = np.asarray(mesh.vertices) @ rotation
    lower, upper = coordinates.min(axis=0), coordinates.max(axis=0)
    center = (lower + upper) / 2
    local = mesh.copy()
    local.vertices = coordinates - center
    size = upper - lower
    tolerance = max(0.0002, np.linalg.norm(size) * 2e-5)
    triangles = local.triangles
    cap = np.all(np.abs(triangles[:, :, 2] - size[2] / 2) < tolerance, axis=1) | np.all(
        np.abs(triangles[:, :, 2] + size[2] / 2) < tolerance, axis=1
    )
    if (
        not cap.any()
        or not np.any(local.face_normals[cap, 2] > 0.99)
        or not np.any(local.face_normals[cap, 2] < -0.99)
    ):
        raise ReconstructionError("No pair of planar end faces")
    side = ~cap
    if np.any(np.abs(local.face_normals[side, 2]) > 1e-4):
        raise ReconstructionError("Side faces are not straight extrusions")
    boundary = np.zeros(len(triangles), dtype=bool)
    for axis in (0, 1):
        for sign in (-1, 1):
            boundary |= np.all(
                np.abs(triangles[:, :, axis] - sign * size[axis] / 2) < tolerance, axis=1
            )
    if size[2] <= min(size[:2]) + tolerance and all(
        np.any(np.all(np.abs(triangles[:, :, axis] - sign * size[axis] / 2) < tolerance, axis=1))
        for axis in (0, 1)
        for sign in (-1, 1)
    ):
        holes = []
        for group in _wall_groups(local, np.flatnonzero(side & ~boundary)):
            circle_center, radius, _ = _circle(group.vertices, tolerance)
            if not np.allclose(group.bounds[:, 2], [-size[2] / 2, size[2] / 2], atol=tolerance):
                raise ReconstructionError("Blind holes and partial walls are unsupported")
            holes.append(
                Hole(x=float(circle_center[0]), y=float(circle_center[1]), diameter=2 * radius)
            )
        holes.sort(key=lambda h: (round(h.x, 5), round(h.y, 5)))
        recipe = Recipe(
            kind="plate",
            parameters=dict(length=float(size[0]), width=float(size[1]), height=float(size[2])),
            holes=holes,
        )
    else:
        circles = [
            _circle(group.vertices, tolerance)
            for group in _wall_groups(local, np.flatnonzero(side))
        ]
        if len(circles) not in (1, 2) or any(np.linalg.norm(c[0]) > tolerance * 2 for c in circles):
            raise ReconstructionError(
                "Only concentric cylinders and single-bore sleeves are supported"
            )
        radii = sorted(c[1] for c in circles)
        parameters = {"outer_diameter": radii[-1] * 2, "height": float(size[2])}
        if len(radii) == 2:
            parameters["inner_diameter"] = radii[0] * 2
        recipe = Recipe(kind="sleeve" if len(radii) == 2 else "cylinder", parameters=parameters)
    transform = np.eye(4)
    transform[:3, :3] = rotation
    transform[:3, 3] = rotation @ center
    return recipe, transform, local


def _canonical_plate(recipe, transform):
    candidates = []
    for swap in (False, True):
        for sx in (-1, 1):
            for sy in (-1, 1):
                plane = np.array([[0, sx], [sy, 0]]) if swap else np.diag([sx, sy])
                rotation = np.eye(4)
                rotation[:2, :2] = plane
                rotation[2, 2] = round(np.linalg.det(plane))
                holes = []
                for hole in recipe.holes:
                    x, y = plane.T @ [hole.x, hole.y]
                    holes.append(Hole(x=float(x), y=float(y), diameter=hole.diameter))
                holes.sort(key=lambda h: (round(h.x, 3), round(h.y, 3), round(h.diameter, 3)))
                length = recipe.parameters["width" if swap else "length"]
                width = recipe.parameters["length" if swap else "width"]
                key = (
                    -round(length, 3),
                    -round(width, 3),
                    tuple((round(h.x, 3), round(h.y, 3), round(h.diameter, 3)) for h in holes),
                )
                canonical = Recipe(
                    kind="plate",
                    parameters=dict(length=length, width=width, height=recipe.parameters["height"]),
                    holes=holes,
                )
                candidates.append((key, canonical, transform @ rotation))
    _, canonical, pose = min(candidates, key=lambda candidate: candidate[0])
    return canonical, pose


def _fit_part(mesh):
    failures = []
    for rotation in _frame_candidates(mesh):
        try:
            recipe, transform, local = _recipe_in_frame(mesh, rotation)
            payload = mesh_payload(build_shape(recipe))
            candidate = trimesh.Trimesh(payload["vertices"], payload["triangles"], process=False)
            fit = surface_fit(local, candidate)
            if fit["valid"]:
                if recipe.kind == "plate":
                    recipe, transform = _canonical_plate(recipe, transform)
                return FittedPart(recipe, transform.tolist(), fit)
            failures.append(
                f"surface residual {fit['max_mm']:.4g} mm or volume error {fit['relative_volume_error']:.3%}"
            )
        except (ValueError, np.linalg.LinAlgError) as error:
            failures.append(str(error))
    raise ReconstructionError("Unsupported solid. " + "; ".join(dict.fromkeys(failures)))


def inspect_stl(path, units) -> AssemblyDocument:
    if units not in {"mm", "cm", "in"}:
        raise ReconstructionError("Declare STL units explicitly as mm, cm, or in")
    path = Path(path)
    if path.suffix.lower() != ".stl":
        raise ReconstructionError(
            "Automatic reconstruction accepts STL only; images need calibrated design evidence"
        )
    if not path.is_file() or not 84 <= path.stat().st_size <= 25_000_000:
        raise ReconstructionError("STL must be a nonempty file smaller than 25 MB")
    try:
        mesh = trimesh.load_mesh(path, file_type="stl", process=False)
    except Exception as error:
        raise ReconstructionError(f"Cannot parse STL: {error}") from error
    if not isinstance(mesh, trimesh.Trimesh) or not 4 <= len(mesh.faces) <= 20_000:
        raise ReconstructionError("STL must contain 4 to 20000 triangles")
    if not np.isfinite(mesh.vertices).all() or np.any(mesh.area_faces <= 1e-14):
        raise ReconstructionError("STL contains nonfinite vertices or degenerate triangles")
    mesh.merge_vertices()
    if not np.all(mesh.unique_faces()) or not mesh.is_watertight or not mesh.is_winding_consistent:
        raise ReconstructionError(
            "STL must be closed, manifold and consistently wound; dirty meshes are unsupported"
        )
    mesh.apply_scale({"mm": 1.0, "cm": 10.0, "in": 25.4}[units])
    components = list(mesh.split(only_watertight=False, repair=False))
    if not 1 <= len(components) <= 32:
        raise ReconstructionError("STL must contain 1 to 32 disconnected closed solids")
    components.sort(key=lambda m: tuple(np.round(m.bounds.mean(axis=0), 6)))
    definitions, occurrences = [], []
    signatures = {}
    for index, component in enumerate(components):
        if not component.is_watertight or component.volume <= 1e-8:
            raise ReconstructionError(f"Component {index + 1} is open, inverted or degenerate")
        try:
            part = _fit_part(component)
        except ReconstructionError as error:
            raise ReconstructionError(f"Component {index + 1}: {error}") from error
        signature = (
            part.recipe.kind,
            tuple((k, round(v, 3)) for k, v in sorted(part.recipe.parameters.items())),
            tuple((round(h.x, 3), round(h.y, 3), round(h.diameter, 3)) for h in part.recipe.holes),
        )
        if signature in signatures:
            definition = definitions[signatures[signature]]
            definition.evidence["component_indices"].append(index)
            definition.evidence["fits"].append(part.fit)
        else:
            definition = PartDefinition(
                id=f"part_{len(definitions) + 1}",
                label=f"{part.recipe.kind.title()} {len(definitions) + 1}",
                recipe=part.recipe,
                evidence={
                    "component_indices": [index],
                    "fit": part.fit,
                    "fits": [part.fit],
                    "deduplication_tolerance_mm": 0.001,
                    "method": "bounded analytic wall fitting",
                },
            )
            signatures[signature] = len(definitions)
            definitions.append(definition)
        occurrences.append(
            Occurrence(
                id=f"occurrence_{index + 1}", definition_id=definition.id, transform=part.transform
            )
        )
    return AssemblyDocument(
        name=path.stem,
        input=InputEvidence(
            name=path.name,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            kind="stl",
            units=units,
        ),
        definitions=definitions,
        occurrences=occurrences,
        assumptions=[
            "Each disconnected watertight component is one rigid part.",
            "Fitted planes and circular walls describe nominal geometry; original design history and mates are not recovered.",
        ],
    )
