import copy
import json
import math
import uuid
from typing import Annotated, Literal

import numpy as np
from pydantic import Field, StrictBool, model_validator

from .decomposition import (
    ConceptProgram,
    Identifier,
    Plan,
    Record,
    _check_source,
    _digest,
    _json_bytes,
    parameter_values,
)
from .decomposition_workflow import DecompositionWorkflow, ScopeCommand, _now
from .project import _atomic_json

CheckNumber = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=-1e6, le=1e6)]


class ParameterRange(Record):
    kind: Literal["parameter_range"]
    id: Identifier
    address: str = Field(min_length=1, max_length=250)
    min: CheckNumber | None = None
    max: CheckNumber | None = None
    unit: Literal["mm", "relative", "deg"]
    quote: str = Field(min_length=1, max_length=2000)
    required: StrictBool = True

    @model_validator(mode="after")
    def limits(self):
        if self.min is None and self.max is None:
            raise ValueError("A parameter range needs at least one limit")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("The minimum must not exceed the maximum")
        return self


class ManualCheck(Record):
    kind: Literal["manual"]
    id: Identifier
    description: str = Field(min_length=1, max_length=2000)
    quote: str = Field(min_length=1, max_length=2000)
    required: StrictBool = True


CheckRule = Annotated[ParameterRange | ManualCheck, Field(discriminator="kind")]


class CheckContext(ScopeCommand):
    text: str = Field(min_length=1, max_length=12000)
    rules: list[CheckRule] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def quotations(self):
        if not self.text.strip():
            raise ValueError("Keep the user's literal nonempty check context")
        if len({rule.id for rule in self.rules}) != len(self.rules):
            raise ValueError("Check rule IDs must be unique")
        if {rule.id for rule in self.rules} & {
            "source-program",
            "selected-meshes",
            "native-readback",
            "user-intent",
            "source-fidelity",
            "manufacturing",
        }:
            raise ValueError("Rule IDs must not replace automatic check identities")
        if any(not rule.quote.strip() or rule.quote not in self.text for rule in self.rules):
            raise ValueError("Each rule must quote the supplied check context literally")
        return self


def _criteria(text="", rules=None):
    rules = rules or []
    return {
        "context": {"text": text, "sha256": _digest(text.encode())},
        "rules": rules,
        "criteria_digest": _digest(_json_bytes({"text": text, "rules": rules})),
        "report": None,
        "history": [],
    }


def _binding(project, node_id, criteria):
    return {
        "project_id": project["id"],
        "node_id": node_id,
        "revision": project["revision"],
        "source_sha256": project["source"]["sha256"],
        "brief_sha256": project["workflow"]["brief"]["sha256"],
        "program_sha256": project["analysis"]["binding"]["program_sha256"],
        "review_digest": project["workflow"]["scopes"][node_id]["review_digest"],
        "criteria_digest": criteria["criteria_digest"],
        "native_build_ids": {
            part["node_id"]: part["cad_build_id"]
            for part in project["workflow"]["parts"]
            if part["node_id"] in project["workflow"]["scopes"][node_id]["part_ids"]
        },
    }


def reconcile_checks(project):
    for node_id, criteria in project.get("workflow", {}).get("checks", {}).items():
        report = criteria.get("report")
        if report and (
            node_id not in project["workflow"]["scopes"]
            or report["binding"] != _binding(project, node_id, criteria)
        ):
            report["status"] = "stale"


def _allowed_parameters(plan, scope):
    definitions = {node.definition_id for node in plan.nodes if node.id in scope["part_ids"]}
    nodes = {node.id: node for node in plan.nodes}
    allowed_nodes = set(scope["part_ids"])
    for part_id in scope["part_ids"]:
        parent = nodes[part_id].parent_id
        while parent:
            allowed_nodes.add(parent)
            parent = nodes[parent].parent_id
    return {
        address: value
        for address, value in parameter_values(plan).items()
        if (
            address.startswith("shape/")
            and address.split("/")[1] in definitions
            or address.startswith("node/")
            and address.split("/")[1] in allowed_nodes
        )
    }


def _result(id, kind, outcome, detail, *, required=False, **data):
    return {
        "id": id,
        "kind": kind,
        "outcome": outcome,
        "detail": detail,
        "required": required,
        **data,
    }


def _verified_geometry(store, project):
    program_path = store.artifact(project["id"], project["program"])
    program = ConceptProgram.model_validate_json(program_path.read_bytes())
    binding = project["analysis"]["binding"]
    if (
        program.project_id != project["id"]
        or program.revision != project["revision"]
        or program.plan.model_dump(mode="json") != project["plan"]
        or program.source.model_dump(mode="json") != project["source"]
        or program.runtime != binding["runtime"]
        or (program.brief.model_dump(mode="json") if program.brief else None)
        != (project["workflow"]["brief"] if project["workflow"]["brief"]["text"] else None)
        or _digest(program_path.read_bytes()) != binding["program_sha256"]
    ):
        raise ValueError("The displayed Plan does not match its accepted program")
    source = store.directory(project["id"]) / "source.bin"
    if source.is_symlink():
        raise ValueError("Source input must be a regular retained file")
    reference = (
        None
        if project["source"].get("kind") == "text"
        else store.reference(project["id"]).read_bytes()
    )
    _check_source(program, source.read_bytes(), reference)
    preview = json.loads(store.artifact(project["id"], project["preview"]).read_text())
    return program.plan, preview


def _mesh_check(preview, scope, plan):
    parts = [part for part in preview["parts"] if part["id"] in scope["part_ids"]]
    definitions = {node.id: node.definition_id for node in plan.nodes}
    if (
        len(parts) != len(scope["part_ids"])
        or {part["id"] for part in parts} != set(scope["part_ids"])
        or any(part["definition_id"] != definitions[part["id"]] for part in parts)
    ):
        raise ValueError("Selected preview membership does not match its physical scope")
    for part in parts:
        vertices = np.asarray(part["vertices"], dtype=float)
        faces = np.asarray(part["triangles"])
        if (
            vertices.ndim != 2
            or vertices.shape[1] != 3
            or not np.isfinite(vertices).all()
            or faces.ndim != 2
            or faces.shape[1] != 3
            or faces.dtype.kind not in "iu"
            or not len(faces)
            or faces.min() < 0
            or faces.max() >= len(vertices)
        ):
            return False
        triangles = vertices[faces]
        if not np.all(
            np.linalg.norm(
                np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]),
                axis=1,
            )
            > 0
        ):
            return False
    return True


def _native_result(store, project, scope):
    flow = project["workflow"]
    parts = [part for part in flow["parts"] if part["node_id"] in scope["part_ids"]]
    if not all(part["cad_build_id"] for part in parts):
        return _result(
            "native-readback",
            "native_readback",
            "unchecked",
            "Not every selected part has a current native build; no new CAD was built by this check.",
        )
    reports = {}
    manager = DecompositionWorkflow(store)
    for part in parts:
        build_id = part["cad_build_id"]
        build = flow["builds"][build_id]
        if (
            build["status"] != "ready"
            or build["binding"]["review_digests"].get(part["node_id"]) != part["review_digest"]
        ):
            raise ValueError("Native build does not match the selected current part")
        if build_id not in reports:
            manager.artifact(project["id"], build_id, build["step_path"])
            reports[build_id] = json.loads(
                manager.artifact(project["id"], build_id, build["report_path"]).read_text()
            )
            if reports[build_id]["binding"] != build["binding"]:
                raise ValueError("Native report binding does not match its build")
        occurrence = next(
            (item for item in reports[build_id]["occurrences"] if item["id"] == part["node_id"]),
            None,
        )
        if not occurrence or occurrence["review_digest"] != part["review_digest"]:
            raise ValueError("Native report does not contain the current selected occurrence")
        for metrics in [occurrence["metrics"], occurrence["step_readback"]]:
            if (
                metrics["valid"] is not True
                or metrics["solid_count"] != 1
                or not math.isfinite(metrics["volume"])
                or metrics["volume"] <= 0
            ):
                return _result(
                    "native-readback",
                    "native_readback",
                    "fail",
                    "Stored native validity or STEP readback failed.",
                    required=True,
                )
    return _result(
        "native-readback",
        "native_readback",
        "pass",
        "Registered STEP/report bytes match their hashes. Stored native and STEP readback metrics are valid for each selected part; the kernel was not rerun.",
        required=True,
        build_ids=sorted(reports),
    )


def _run(store, project, node_id, scope, criteria):
    results = []
    try:
        plan, preview = _verified_geometry(store, project)
        results.append(
            _result(
                "source-program",
                "source_program_integrity",
                "pass",
                "Retained source, program and preview artifact hashes match; the displayed Plan matches the program.",
                required=True,
            )
        )
        valid = _mesh_check(preview, scope, plan)
        results.append(
            _result(
                "selected-meshes",
                "mesh_integrity",
                "pass" if valid else "fail",
                "Selected meshes were checked for finite vertices, indexed triangles and nonzero triangle area. This is not native-solid validity.",
                required=True,
                part_ids=scope["part_ids"],
            )
        )
    except (ValueError, OSError, KeyError, TypeError) as error:
        results.append(
            _result("source-program", "source_program_integrity", "fail", str(error), required=True)
        )
        plan = None
    try:
        results.append(_native_result(store, project, scope))
    except (ValueError, OSError, KeyError, TypeError) as error:
        results.append(
            _result("native-readback", "native_readback", "fail", str(error), required=True)
        )
    values = _allowed_parameters(plan, scope) if plan else {}
    for raw in criteria["rules"]:
        if raw["kind"] == "manual":
            results.append(
                _result(
                    raw["id"],
                    "manual",
                    "blocked" if raw["required"] else "unchecked",
                    "Requires a separate evidenced review: " + raw["description"],
                    required=raw["required"],
                    quote=raw["quote"],
                )
            )
            continue
        rule = ParameterRange.model_validate(raw)
        actual = values.get(rule.address)
        unit = "deg" if "/rotation/" in rule.address else plan.units if plan else None
        if actual is None or unit != rule.unit:
            outcome, detail = (
                "blocked",
                "Parameter is unavailable in this scope or its unit/scale does not match the requirement.",
            )
        else:
            passed = (rule.min is None or actual >= rule.min) and (
                rule.max is None or actual <= rule.max
            )
            outcome, detail = (
                ("pass" if passed else "fail"),
                "Measured the accepted authored parameter against the quoted limits; source accuracy remains separate.",
            )
        results.append(
            _result(
                rule.id,
                rule.kind,
                outcome,
                detail,
                required=rule.required,
                address=rule.address,
                actual=actual,
                min=rule.min,
                max=rule.max,
                unit=unit,
                expected_unit=rule.unit,
                quote=rule.quote,
            )
        )
    results.extend(
        [
            _result(
                "user-intent",
                "user_intent",
                "unchecked",
                "Only listed machine criteria were tested. No complete intent review is established."
                if criteria["rules"]
                else "No user criteria were supplied; this run checks structural integrity only.",
            ),
            _result(
                "source-fidelity",
                "source_fidelity",
                "unchecked",
                "Agreement with the source image or reference requires separate measurements.",
            ),
            _result(
                "manufacturing",
                "manufacturing",
                "unchecked",
                "Factory tolerances, fits, loads and manufacturability were not evaluated.",
            ),
        ]
    )
    required = [item for item in results if item["required"]]
    outcome = (
        "fail"
        if any(item["outcome"] == "fail" for item in required)
        else "blocked"
        if any(item["outcome"] != "pass" for item in required)
        else "pass"
    )
    return {
        "id": uuid.uuid4().hex,
        "status": "current",
        "outcome": outcome,
        "ci_exit_code": {"pass": 0, "fail": 1, "blocked": 2}[outcome],
        "binding": _binding(project, node_id, criteria),
        "results": results,
        "summary": {
            state: sum(item["outcome"] == state for item in results)
            for state in ["pass", "fail", "blocked", "unchecked"]
        },
        "created_at": _now(),
    }


def check_action(store, project_id, action, payload):
    if action not in {"check-context", "check"}:
        raise ValueError("Unsupported part check action")
    command = (CheckContext if action == "check-context" else ScopeCommand).model_validate(payload)
    manager = DecompositionWorkflow(store)
    with store.locked(project_id) as directory:
        project = store.get(project_id)
        manager._check(project, command)
        scope = manager._scope(project, command.node_id, command.review_digest)
        checks = project["workflow"].setdefault("checks", {})
        criteria = checks.setdefault(command.node_id, _criteria())
        if action == "check-context":
            values = _allowed_parameters(Plan.model_validate(project["plan"]), scope)
            for rule in command.rules:
                if isinstance(rule, ParameterRange) and rule.address not in values:
                    raise ValueError("A check parameter must belong to the selected physical scope")
            updated = _criteria(
                command.text, [rule.model_dump(mode="json") for rule in command.rules]
            )
            updated.update(report=criteria["report"], history=criteria["history"])
            checks[command.node_id] = updated
        else:
            retained = _criteria(criteria["context"]["text"], criteria["rules"])
            if (
                retained["context"] != criteria["context"]
                or retained["criteria_digest"] != criteria["criteria_digest"]
            ):
                raise ValueError("Saved check context does not match its recorded digest")
            if criteria["report"]:
                criteria["history"] = [*criteria["history"], copy.deepcopy(criteria["report"])][
                    -16:
                ]
            criteria["report"] = _run(store, project, command.node_id, scope, criteria)
        project["workflow"]["checks"][command.node_id]["review_digest"] = scope["review_digest"]
        reconcile_checks(project)
        project["workflow_revision"] += 1
        _atomic_json(directory / "manifest.json", project)
        return project
