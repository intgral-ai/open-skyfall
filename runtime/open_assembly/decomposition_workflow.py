import base64
import copy
import json
import re
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import Field, StrictBool, StrictInt, model_validator

from .decomposition import Digest, Identifier, Plan, Record, _digest, _json_bytes
from .project import RevisionConflict, _atomic_json

_NATIVE_CAPACITY = threading.BoundedSemaphore(2)


def _now():
    return datetime.now(UTC).isoformat()


class ProposalPart(Record):
    id: Identifier
    label: str = Field(min_length=1, max_length=100)
    parent_id: Identifier | None = None
    description: str = Field(min_length=1, max_length=1000)


class Proposal(Record):
    summary: str = Field(min_length=1, max_length=3000)
    parts: list[ProposalPart] = Field(min_length=1, max_length=64)
    unknowns: list[str] = Field(default_factory=list, max_length=32)
    manufacturing_notes: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def hierarchy(self):
        nodes = {part.id: part for part in self.parts}
        if len(nodes) != len(self.parts) or not self.summary.strip():
            raise ValueError("Proposal needs unique part IDs and a concrete summary")
        if len([part for part in self.parts if part.parent_id is None]) != 1:
            raise ValueError("Proposal needs one assembly root")
        for part in self.parts:
            seen = {part.id}
            parent = part.parent_id
            while parent:
                if parent not in nodes or parent in seen:
                    raise ValueError("Proposal parent hierarchy is invalid")
                seen.add(parent)
                parent = nodes[parent].parent_id
        return self


class Mutation(Record):
    revision: StrictInt = Field(ge=0)
    workflow_revision: StrictInt = Field(ge=0)


class Propose(Mutation):
    proposal: Proposal


class ApproveProposal(Mutation):
    proposal_digest: Digest


class Capture(Mutation):
    request_id: Identifier
    node_id: Identifier
    text: str = Field(min_length=1, max_length=6000)


class ScopeCommand(Mutation):
    node_id: Identifier
    review_digest: Digest


class Confirm(ScopeCommand):
    confirmed: StrictBool


def initialize(project, description):
    project["workflow_revision"] = 0
    project["workflow"] = {
        "brief": {"text": description, "sha256": _digest(description.encode())},
        "proposal": None,
        "requests": [],
        "approvals": {},
        "approval_history": [],
        "builds": {},
        "cad": {"parts": {}, "assembly": None},
        "parts": [],
        "scopes": {},
        "phase": "input",
        "status": "ready",
        "error": None,
    }


def _part_data(project):
    plan = Plan.model_validate(project["plan"])
    data = plan.model_dump(mode="json")
    nodes = {node["id"]: node for node in data["nodes"]}
    definitions = {item["id"]: item for item in data["definitions"]}
    explanation = data["explanation"]
    result = []
    for node in nodes.values():
        if not node["definition_id"]:
            continue
        definition = definitions[node["definition_id"]]
        lineage = [node]
        while lineage[-1]["parent_id"]:
            lineage.append(nodes[lineage[-1]["parent_id"]])
        evidence = None
        if explanation:
            addresses = {
                key: ref
                for key, ref in explanation["parameters"].items()
                if key.startswith(f"shape/{definition['id']}/")
                or any(key.startswith(f"node/{item['id']}/") for item in lineage)
            }
            shapes = {
                key: ref
                for key, ref in explanation["shapes"].items()
                if key.startswith(definition["id"] + "/")
            }
            bases = {explanation["scale"], *addresses.values(), *shapes.values()}
            node_evidence = {item["id"]: explanation["nodes"][item["id"]] for item in lineage}
            for refs in node_evidence.values():
                bases.update(refs.values())
            reasons = {key: explanation["bases"][key] for key in sorted(bases)}
            observations = {ref for basis in reasons.values() for ref in basis["observations"]}
            evidence = {
                "parameters": addresses,
                "shapes": shapes,
                "nodes": node_evidence,
                "bases": reasons,
                "scale": explanation["scale"],
                "observations": [
                    item for item in explanation["observations"] if item["id"] in observations
                ],
            }
        digest = _digest(
            _json_bytes(
                {
                    "source": project["source"],
                    "brief": project["workflow"]["brief"],
                    "units": plan.units,
                    "scale_note": plan.scale_note,
                    "assumptions": plan.assumptions,
                    "definition": definition,
                    "lineage": lineage,
                    "evidence": evidence,
                }
            )
        )
        result.append(
            {
                "node_id": node["id"],
                "definition_id": definition["id"],
                "label": node["label"],
                "review_digest": digest,
                "approved": False,
                "cad_build_id": None,
                "shared_occurrence_ids": [
                    item["id"]
                    for item in nodes.values()
                    if item["definition_id"] == definition["id"]
                ],
                "manufacturing": definition["manufacturing"],
                "ancestors": [item["id"] for item in lineage],
            }
        )
    return plan, result


def reconcile(project, *, previous=None, request_id=None):
    if "workflow" not in project:
        return
    flow = project["workflow"] = copy.deepcopy(project["workflow"])
    if request_id:
        request = next(item for item in flow["requests"] if item["id"] == request_id)
        request.update(status="applied", applied_revision=project["revision"])
    if not project.get("plan"):
        flow["phase"] = "proposal" if flow["proposal"] else "input"
        return
    plan, parts = _part_data(project)
    pending = {
        part
        for request in flow["requests"]
        if request["status"] == "pending"
        for part in request["part_ids"]
    }
    approvals = flow["approvals"]
    live = {part["node_id"]: part for part in parts}
    for node_id, approval in list(approvals.items()):
        if (
            node_id not in live
            or approval["review_digest"] != live[node_id]["review_digest"]
            or node_id in pending
        ):
            flow["approval_history"].append(
                {**approval, "node_id": node_id, "invalidated_at_revision": project["revision"]}
            )
            del approvals[node_id]
    for part in parts:
        node_id = part["node_id"]
        part["approved"] = node_id in approvals
        cad = flow["cad"]["parts"].get(node_id)
        if cad and part["approved"] and cad["review_digest"] == part["review_digest"]:
            part["cad_build_id"] = cad["build_id"]
        else:
            flow["cad"]["parts"].pop(node_id, None)
    scopes = {}
    for node in plan.nodes:
        members = [part for part in parts if node.id in part["ancestors"]]
        identities = {part["node_id"]: part["review_digest"] for part in members}
        approved = bool(members) and all(part["approved"] for part in members)
        scopes[node.id] = {
            "part_ids": list(identities),
            "review_digest": _digest(_json_bytes(identities)),
            "approved": approved,
            "approved_count": sum(part["approved"] for part in members),
            "part_count": len(members),
            "can_build": approved and plan.units == "mm",
        }
    if previous and previous["revision"] != project["revision"]:
        flow["cad"]["assembly"] = None
    flow["parts"] = [
        {key: value for key, value in part.items() if key != "ancestors"} for part in parts
    ]
    flow["scopes"] = scopes
    flow["phase"] = "cad" if flow["cad"]["assembly"] else "review"
    flow["status"] = (
        "building"
        if any(item["status"] == "building" for item in flow["builds"].values())
        else "failed"
        if flow["error"]
        else "ready"
    )
    from .decomposition_checks import reconcile_checks

    reconcile_checks(project)
    if previous is not None:
        project["workflow_revision"] = previous.get("workflow_revision", 0) + 1


def validate_plan_transition(project, request_id, plan=None):
    flow = project.get("workflow")
    if flow is None:
        if request_id:
            raise ValueError("This project has no captured change requests")
        return
    proposal = flow["proposal"]
    if not proposal or not proposal["approved"]:
        raise ValueError("Confirm the proposal before accepting its decomposition")
    if request_id:
        request = next((item for item in flow["requests"] if item["id"] == request_id), None)
        if not request or request["status"] != "pending":
            raise ValueError("A pending captured request is required")
    if plan is not None:
        physical_ids = {node.id for node in plan.nodes if node.definition_id}
        for pending in flow["requests"]:
            if pending["status"] == "pending" and pending["id"] != request_id:
                if not set(pending["part_ids"]) <= physical_ids:
                    raise ValueError(
                        "Preserve the IDs affected by pending requests, or explicitly resolve that request"
                    )


class DecompositionWorkflow:
    def __init__(self, store):
        self.store = store

    def _check(self, project, command):
        if command.revision != project["revision"] or command.workflow_revision != project.get(
            "workflow_revision", 0
        ):
            raise RevisionConflict("Project or workflow changed; read its current state")
        if "workflow" not in project:
            raise ValueError("This legacy project has no review workflow; import a new project")

    def _save(self, directory, project):
        reconcile(project)
        project["workflow_revision"] += 1
        _atomic_json(directory / "manifest.json", project)
        return project

    def _scope(self, project, node_id, digest=None):
        scope = project["workflow"]["scopes"].get(node_id)
        if not scope or not scope["part_ids"]:
            raise ValueError("Select a part or assembly with accepted geometry")
        if digest is not None and digest != scope["review_digest"]:
            raise RevisionConflict("The inspected part scope changed; review it again")
        return scope

    def mutate(self, project_id, action, payload):
        models = {
            "proposal": Propose,
            "approve-proposal": ApproveProposal,
            "request": Capture,
            "approve": Confirm,
        }
        if action not in models:
            raise ValueError("Unsupported review action")
        command = models[action].model_validate(payload)
        with self.store.locked(project_id) as directory:
            project = self.store.get(project_id)
            flow = project.get("workflow", {})
            if action == "request":
                existing = next(
                    (item for item in flow.get("requests", []) if item["id"] == command.request_id),
                    None,
                )
                if existing:
                    if (
                        existing["text"] == command.text
                        and existing["node_id"] == command.node_id
                        and existing["revision"] == command.revision
                    ):
                        return project
                    raise RevisionConflict("Request ID already belongs to different input")
            self._check(project, command)
            flow["error"] = None
            if action == "proposal":
                if project["plan"]:
                    raise ValueError(
                        "A proposal precedes decomposition; iterate existing parts through requests"
                    )
                data = command.proposal.model_dump(mode="json")
                digest = _digest(
                    _json_bytes(
                        {"source": project["source"], "brief": flow["brief"], "proposal": data}
                    )
                )
                flow["proposal"] = {"data": data, "digest": digest, "approved": False}
            elif action == "approve-proposal":
                proposal = flow["proposal"]
                if not proposal or proposal["digest"] != command.proposal_digest:
                    raise RevisionConflict("The proposal changed; inspect the current proposal")
                proposal.update(approved=True, confirmed_at=_now())
            elif action == "request":
                if not command.text.strip():
                    raise ValueError("Capture the user's literal nonempty requested change")
                if len(flow["requests"]) >= 128:
                    raise ValueError("This project has reached its change-request limit")
                scope = self._scope(project, command.node_id)
                parts = [part for part in flow["parts"] if part["node_id"] in scope["part_ids"]]
                affected = sorted(
                    {item for part in parts for item in part["shared_occurrence_ids"]}
                )
                flow["requests"].append(
                    {
                        "id": command.request_id,
                        "node_id": command.node_id,
                        "text": command.text,
                        "status": "pending",
                        "part_ids": affected,
                        "revision": project["revision"],
                        "source_sha256": project["source"]["sha256"],
                        "program_sha256": project["analysis"]["binding"]["program_sha256"],
                        "scope_digest": scope["review_digest"],
                        "captured_at": _now(),
                    }
                )
                flow["cad"]["assembly"] = None
            elif action == "approve":
                if command.confirmed is not True:
                    raise ValueError("Explicit user confirmation is required")
                scope = self._scope(project, command.node_id, command.review_digest)
                if any(
                    set(request["part_ids"]) & set(scope["part_ids"])
                    for request in flow["requests"]
                    if request["status"] == "pending"
                ):
                    raise ValueError("Resolve captured changes before confirming these parts")
                for part in flow["parts"]:
                    if part["node_id"] in scope["part_ids"]:
                        flow["approvals"][part["node_id"]] = {
                            "review_digest": part["review_digest"],
                            "method": "explicit_user_action",
                            "confirmed_at": _now(),
                        }
            return self._save(directory, project)

    def build(self, project_id, payload):
        from .decomposition_native import build_native

        command = ScopeCommand.model_validate(payload)
        if not _NATIVE_CAPACITY.acquire(blocking=False):
            raise ValueError("Native build capacity is full; retry when a build finishes")
        try:
            with self.store.locked(project_id) as directory:
                project = self.store.get(project_id)
                self._check(project, command)
                scope = self._scope(project, command.node_id, command.review_digest)
                if not scope["can_build"]:
                    raise ValueError(
                        "Confirm every selected part and establish millimeter scale before CAD"
                    )
                if project["workflow"]["status"] == "building":
                    raise RevisionConflict("This project already has a native build in progress")
                plan = Plan.model_validate(project["plan"])
                self.store.artifact(project_id, project["program"])
                source_path = directory / "source.bin"
                if (
                    source_path.is_symlink()
                    or _digest(source_path.read_bytes()) != project["source"]["sha256"]
                ):
                    raise ValueError("Source input integrity check failed")
                selected = {
                    part["node_id"]: part["review_digest"]
                    for part in project["workflow"]["parts"]
                    if part["node_id"] in scope["part_ids"]
                }
                binding = {
                    "project_id": project_id,
                    "revision": project["revision"],
                    "source_sha256": project["source"]["sha256"],
                    "brief_sha256": project["workflow"]["brief"]["sha256"],
                    "program_sha256": project["analysis"]["binding"]["program_sha256"],
                    "plan_sha256": _digest(_json_bytes(plan.model_dump(mode="json"))),
                    "review_digests": selected,
                    "scope_digest": scope["review_digest"],
                    "part_ids": scope["part_ids"],
                }
                build_id = uuid.uuid4().hex
                if (directory / "cad").is_symlink():
                    raise ValueError("Native output must remain inside the project directory")
                build = {
                    "status": "building",
                    "scope": command.node_id,
                    "binding": binding,
                    "plan_revision": project["revision"],
                    "artifacts": {},
                    "started_at": _now(),
                }
                project["workflow"]["builds"][build_id] = build
                self._save(directory, project)
                output = directory / "cad" / build_id
            try:
                result = build_native(plan, output, binding=binding, node_ids=scope["part_ids"])
                self._validate_result(output, result, binding)
            except Exception as error:
                with self.store.locked(project_id) as directory:
                    current = self.store.get(project_id)
                    current["workflow"]["builds"][build_id].update(
                        status="failed", error=str(error)[:2000], finished_at=_now()
                    )
                    current["workflow"]["error"] = str(error)[:2000]
                    self._save(directory, current)
                raise ValueError(f"Native construction failed: {error}") from error
            with self.store.locked(project_id) as directory:
                current = self.store.get(project_id)
                live = current["workflow"]["scopes"].get(command.node_id)
                accepted = (
                    current["revision"] == binding["revision"]
                    and live
                    and live["can_build"]
                    and live["review_digest"] == binding["scope_digest"]
                )
                record = current["workflow"]["builds"][build_id]
                record.update(result, status="ready" if accepted else "stale", finished_at=_now())
                if accepted:
                    for node_id, digest in selected.items():
                        current["workflow"]["cad"]["parts"][node_id] = {
                            "build_id": build_id,
                            "review_digest": digest,
                        }
                    if len(selected) == len(current["workflow"]["parts"]):
                        current["workflow"]["cad"]["assembly"] = build_id
                result_project = self._save(directory, current)
                if not accepted:
                    raise RevisionConflict(
                        "Native result is retained as stale; project or confirmation changed during construction"
                    )
                return result_project
        finally:
            _NATIVE_CAPACITY.release()

    def _validate_result(self, output, result, binding):
        if result.get("binding") != binding or result.get("step_structure") != "flat_named_bodies":
            raise ValueError("Native result has a mismatched construction binding")
        checks = result.get("checks", {})
        if any(
            checks.get(gate, {}).get("status") != "PASS"
            for gate in ["native_validity", "step_exchange"]
        ):
            raise ValueError("Native validity and STEP readback must both pass")
        artifacts = result.get("artifacts", {})
        for name in ["assembly.step", "native-preview.json", "native-report.json", "assembly.json"]:
            if name not in artifacts:
                raise ValueError("Native delivery is incomplete")
        for name, digest in artifacts.items():
            path = output / name
            if (
                path.is_symlink()
                or not path.is_file()
                or not path.resolve().is_relative_to(output.resolve())
                or _digest(path.read_bytes()) != digest
            ):
                raise ValueError("Native artifact integrity check failed")

    def artifact(self, project_id, build_id, name):
        if not re.fullmatch(r"[0-9a-f]{32}", build_id):
            raise ValueError("Invalid native build ID")
        project = self.store.get(project_id)
        build = project.get("workflow", {}).get("builds", {}).get(build_id)
        if not build or name not in build["artifacts"]:
            raise FileNotFoundError("Artifact is not registered to this native build")
        directory = self.store.directory(project_id) / "cad" / build_id
        path = directory / name
        if (
            path.is_symlink()
            or not path.resolve().is_relative_to(self.store.directory(project_id))
            or _digest(path.read_bytes()) != build["artifacts"][name]
        ):
            raise ValueError("Native artifact integrity check failed")
        return path

    def request(self, method, path, payload):
        match = re.fullmatch(r"/api/decompositions/([0-9a-f]{32})/workflow/([a-z-]+)", path)
        if method == "POST" and match:
            project_id, action = match.groups()
            if action in {"check-context", "check"}:
                from .decomposition_checks import check_action

                return check_action(self.store, project_id, action, payload)
            if action == "decompose-example":
                return self.decompose_example(project_id, payload)
            return (
                self.build(project_id, payload)
                if action == "build"
                else self.mutate(project_id, action, payload)
            )
        match = re.fullmatch(
            r"/api/decompositions/([0-9a-f]{32})/workflow/builds/([0-9a-f]{32})/artifacts/(.+)",
            path,
        )
        if method == "GET" and match:
            artifact = self.artifact(*match.groups())
            if artifact.suffix == ".json":
                return json.loads(artifact.read_text())
            return {
                "filename": artifact.name,
                "mime_type": "application/step"
                if artifact.suffix == ".step"
                else "application/octet-stream",
                "data_base64": base64.b64encode(artifact.read_bytes()).decode(),
            }
        raise ValueError("Unsupported decomposition workflow operation")

    def decompose_example(self, project_id, payload):
        command = Mutation.model_validate(payload)
        with self.store.locked(project_id):
            project = self.store.get(project_id)
            self._check(project, command)
            if project["workflow"].get("example_case") != "inspection-rig" or project["plan"]:
                raise ValueError(
                    "Only the labeled undecomposed design example can use its authored plan"
                )
            validate_plan_transition(project, None)
            fixture = _fixture_directory()
            plan = json.loads((fixture / "plan.json").read_text())
            if plan["source_sha256"] != project["source"]["sha256"]:
                raise ValueError("Designed example does not match this project's source")
        return self.store.update(
            project_id,
            {
                "revision": command.revision,
                "workflow_revision": command.workflow_revision,
                "plan": plan,
            },
        )


def _fixture_directory():
    fixture = Path(__file__).resolve().parents[2] / "examples/decomposition/inspection-rig"
    if not fixture.is_dir():
        fixture = Path(__file__).parent / "data/decomposition/inspection-rig"
    if not fixture.is_dir():
        raise FileNotFoundError("The authored inspection-rig example is unavailable")
    return fixture


def anatomy_example(store):
    fixture = _fixture_directory()
    project = store.create(
        (fixture / "reference.png").read_bytes(),
        "Bench comparator · designed example",
        "Original repository MIT design illustration",
        description=(fixture / "brief.txt").read_text(),
        workflow=True,
    )
    with store.locked(project["id"]) as directory:
        project["workflow"]["example_case"] = "inspection-rig"
        _atomic_json(directory / "manifest.json", project)
    manager = DecompositionWorkflow(store)
    payload = {
        "revision": 0,
        "workflow_revision": 0,
        "proposal": json.loads((fixture / "proposal.json").read_text()),
    }
    return manager.mutate(project["id"], "proposal", payload)
