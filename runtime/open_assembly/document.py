import hashlib
import json
import math
from typing import Annotated, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Hole(Record):
    x: float = 0
    y: float = 0
    diameter: float = Field(gt=0, le=2000)


class Recipe(Record):
    kind: Literal["plate", "box", "sleeve", "cylinder"]
    parameters: dict[str, float]
    holes: list[Hole] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def valid_dimensions(self):
        required = {
            "plate": {"length", "width", "height"},
            "box": {"length", "width", "height"},
            "sleeve": {"outer_diameter", "inner_diameter", "height"},
            "cylinder": {"outer_diameter", "height"},
        }[self.kind]
        if set(self.parameters) != required:
            raise ValueError(f"{self.kind} requires exactly {sorted(required)}")
        if any(not math.isfinite(v) or not 0.01 <= v <= 2000 for v in self.parameters.values()):
            raise ValueError("Dimensions must be finite millimeters between 0.01 and 2000")
        if (
            self.kind == "sleeve"
            and self.parameters["inner_diameter"] >= self.parameters["outer_diameter"]
        ):
            raise ValueError("The bore must be smaller than the outside diameter")
        if self.kind in {"sleeve", "cylinder"} and self.holes:
            raise ValueError("Additional offset holes are supported only on plates and boxes")
        if self.kind in {"plate", "box"}:
            for hole in self.holes:
                if abs(hole.x) + hole.diameter / 2 >= self.parameters["length"] / 2:
                    raise ValueError("Hole intersects the plate's X boundary")
                if abs(hole.y) + hole.diameter / 2 >= self.parameters["width"] / 2:
                    raise ValueError("Hole intersects the plate's Y boundary")
        return self


class PartDefinition(Record):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    label: str = Field(min_length=1, max_length=120)
    recipe: Recipe
    evidence: dict = Field(default_factory=dict)


def identity_matrix() -> list[list[float]]:
    return np.eye(4).tolist()


class Occurrence(Record):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    definition_id: str
    parent_id: str | None = None
    transform: list[list[float]] = Field(default_factory=identity_matrix)

    @model_validator(mode="after")
    def rigid_transform(self):
        m = np.asarray(self.transform, dtype=float)
        if m.shape != (4, 4) or not np.isfinite(m).all():
            raise ValueError("Transform must be a finite 4 by 4 matrix")
        if not np.allclose(m[3], [0, 0, 0, 1], atol=1e-8):
            raise ValueError("Transform has an invalid final row")
        r = m[:3, :3]
        if not np.allclose(r.T @ r, np.eye(3), atol=1e-6) or not np.isclose(np.linalg.det(r), 1):
            raise ValueError("Transform must contain a proper rigid rotation")
        return self


class InputEvidence(Record):
    name: str
    sha256: str
    kind: Literal["stl", "image", "recipe"]
    units: Literal["mm", "cm", "in"] | None = None
    assumptions: list[str] = Field(default_factory=list)


class DocumentEnvelope(Record):
    name: str = Field(default="Assembly", min_length=1, max_length=120)
    input: InputEvidence
    occurrences: list[Occurrence] = Field(default_factory=list, max_length=128)
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_graph(self):
        definitions = {d.id for d in self.definitions}
        occurrences = {o.id: o for o in self.occurrences}
        if len(definitions) != len(self.definitions) or len(occurrences) != len(self.occurrences):
            raise ValueError("Definition and occurrence IDs must be unique")
        for occurrence in self.occurrences:
            if occurrence.definition_id not in definitions:
                raise ValueError(f"Unknown definition {occurrence.definition_id}")
            seen = {occurrence.id}
            parent = occurrence.parent_id
            while parent is not None:
                if parent not in occurrences or parent in seen:
                    raise ValueError("Occurrence parents must form an acyclic tree")
                seen.add(parent)
                parent = occurrences[parent].parent_id
        return self

    @property
    def revision(self) -> str:
        data = json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(data.encode()).hexdigest()[:20]

    def global_transform(self, occurrence_id: str) -> list[list[float]]:
        occurrences = {o.id: o for o in self.occurrences}
        occurrence = occurrences[occurrence_id]
        matrix = np.asarray(occurrence.transform)
        while occurrence.parent_id is not None:
            occurrence = occurrences[occurrence.parent_id]
            matrix = np.asarray(occurrence.transform) @ matrix
        return matrix.tolist()


class AssemblyDocument(DocumentEnvelope):
    schema_version: Literal[1] = 1
    definitions: list[PartDefinition] = Field(default_factory=list, max_length=32)


NATIVE_SOURCE_SHA256 = "7bc71c24414c9c8da0059c7381cbae4e9884d76cd97d0c47986cd373024d621a"
HookTop = Annotated[float, Field(strict=True, ge=5.55, le=6.55, allow_inf_nan=False)]


class NativeParameters(Record):
    hook_top: HookTop = 5.55


class NativePartDefinition(Record):
    id: Literal["wiring_cover"] = "wiring_cover"
    label: str = "Wiring cover"
    native_part_id: Literal["wiring_cover"] = "wiring_cover"
    parameters: NativeParameters = Field(default_factory=NativeParameters)
    evidence: dict = Field(default_factory=dict)


class NativeInputEvidence(InputEvidence):
    kind: Literal["native"] = "native"
    units: Literal["mm"] = "mm"


class NativeAssemblyDocument(DocumentEnvelope):
    schema_version: Literal[2] = 2
    backend: Literal["smlibpy"] = "smlibpy"
    case_id: Literal["wiring-cover"] = "wiring-cover"
    source_sha256: Literal[NATIVE_SOURCE_SHA256] = NATIVE_SOURCE_SHA256
    input: NativeInputEvidence
    definitions: list[NativePartDefinition] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def fixed_case(self):
        if len(self.occurrences) != 1:
            raise ValueError("The wiring cover is one physical part")
        occurrence = self.occurrences[0]
        if (
            occurrence.id != "wiring_cover_1"
            or occurrence.parent_id is not None
            or occurrence.transform != identity_matrix()
        ):
            raise ValueError("The registered cover uses its fixed body-frame placement")
        if self.input.sha256 != self.source_sha256:
            raise ValueError("Native input must identify the registered source")
        return self


Document = AssemblyDocument | NativeAssemblyDocument


def parse_document(value: Document | dict) -> Document:
    if isinstance(value, (AssemblyDocument, NativeAssemblyDocument)):
        return value
    if value.get("schema_version") == 2:
        return NativeAssemblyDocument.model_validate(value)
    return AssemblyDocument.model_validate(value)
