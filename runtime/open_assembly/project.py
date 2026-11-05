import hashlib
import json
import os
import re
import shutil
import struct
import threading
import uuid
import zipfile
from collections.abc import Callable
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from .context import (
    BriefRequest,
    CapturedRequest,
    ChangeRequestCommand,
    ContextUpdate,
    ProjectContext,
)
from .document import AssemblyDocument, NativeAssemblyDocument, parse_document
from .file_lock import exclusive_lock
from .native import NativeEditCommand, NativeExampleCommand, NativeExecution

MAX_INPUT_BYTES = 30 * 1024 * 1024
MAX_TRIANGLES = 200_000
_IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp"}
_JOB_ID = re.compile(r"^[0-9a-f]{32}$")


class RevisionConflict(ValueError):
    """The caller's revision no longer describes the accepted project."""


class ArtifactUnavailable(ValueError):
    """No accepted artifact exists for this project revision."""


def _now():
    return datetime.now(UTC).isoformat()


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path, value):
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, allow_nan=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _relative_name(filename):
    name = PurePosixPath(filename)
    if (
        not filename
        or "\\" in filename
        or name.is_absolute()
        or any(part in {"", ".", ".."} for part in filename.split("/"))
    ):
        raise ValueError("Artifact names must be safe relative paths")
    return name


class ProjectStore:
    """Persist one accepted revision per job; compute outside the publication lock."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks = {}
        self._locks_guard = threading.Lock()

    def job_directory(self, job_id: str) -> Path:
        if not isinstance(job_id, str) or not _JOB_ID.fullmatch(job_id):
            raise ValueError("Invalid project ID")
        directory = self.root / job_id
        if directory.is_symlink() or not directory.is_dir():
            raise FileNotFoundError("Project does not exist")
        return directory

    @contextmanager
    def _locked(self, job_id):
        directory = self.job_directory(job_id)
        with self._locks_guard:
            lock = self._locks.setdefault(job_id, threading.RLock())
        with lock, (directory / ".lock").open("a+b") as stream, exclusive_lock(stream):
            yield directory

    def _read(self, directory):
        manifest = json.loads((directory / "manifest.json").read_text())
        manifest.setdefault("context_revision", 0)
        manifest.setdefault("context", ProjectContext().model_dump())
        manifest.setdefault("change_requests", [])
        manifest.setdefault("executions", [])
        return manifest

    def _save(self, directory, manifest):
        manifest["updated_at"] = _now()
        _atomic_json(directory / "manifest.json", manifest)

    def _check_revision(self, manifest, expected_revision):
        if expected_revision is not None and (
            type(expected_revision) is not int or expected_revision != manifest["revision"]
        ):
            raise RevisionConflict(
                f"Revision {expected_revision!r} is stale; current revision is {manifest['revision']}"
            )

    def create(
        self,
        path: str | Path,
        units: str | None,
        name: str | None = None,
        *,
        defer_build: bool = False,
    ) -> dict:
        if units not in {None, "mm", "cm", "in"}:
            raise ValueError("Units must be explicitly mm, cm or in, or left unknown")
        source = Path(path)
        suffix = source.suffix.lower()
        if suffix != ".stl" and suffix not in _IMAGE_TYPES:
            raise ValueError("Upload an STL, PNG, JPEG or WebP file")
        if not source.is_file():
            raise ValueError("Input must be a regular file")
        if not 0 < source.stat().st_size <= MAX_INPUT_BYTES:
            raise ValueError("Input must be nonempty and no larger than 30 MB")
        if name is not None and (not isinstance(name, str) or not 1 <= len(name.strip()) <= 120):
            raise ValueError("Project name must contain 1 to 120 characters")
        job_id = uuid.uuid4().hex
        directory = self.root / job_id
        directory.mkdir()
        destination = directory / f"input{suffix}"
        try:
            with source.open("rb") as original, destination.open("xb") as copied:
                total = 0
                while chunk := original.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_INPUT_BYTES:
                        raise ValueError("Input exceeds 30 MB")
                    copied.write(chunk)
            if total == 0:
                raise ValueError("Input must be nonempty")
            kind = "stl" if suffix == ".stl" else "image"
            if kind == "image":
                with destination.open("rb") as image_stream:
                    header = image_stream.read(16)
                valid_image = (
                    suffix == ".png"
                    and header.startswith(b"\x89PNG\r\n\x1a\n")
                    or suffix in {".jpg", ".jpeg"}
                    and header.startswith(b"\xff\xd8\xff")
                    or suffix == ".webp"
                    and header.startswith(b"RIFF")
                    and header[8:12] == b"WEBP"
                )
                if not valid_image:
                    raise ValueError("Image content does not match its PNG, JPEG or WebP extension")
            state = "queued" if kind == "stl" and units is not None else "needs_evidence"
            reason = None
            if state == "needs_evidence":
                reason = {
                    "code": "measured_design_required" if kind == "image" else "units_required",
                    "message": (
                        "Image reconstruction requires a host-provided measured AssemblyDocument. "
                        "Supply dimensions, part definitions and placements in millimeters."
                        if kind == "image"
                        else "STL has no scale metadata. Supply explicit units and a measured design."
                    ),
                }
            manifest = self._initial_manifest(
                job_id,
                name.strip() if name else source.stem[:120] or "Assembly",
                {
                    "filename": destination.name,
                    "name": source.name,
                    "kind": kind,
                    "units": units,
                    "sha256": _sha256(destination),
                },
                state,
                reason,
            )
            _atomic_json(directory / "manifest.json", manifest)
        except Exception:
            shutil.rmtree(directory)
            raise
        if state == "queued" and not defer_build:
            return self.rebuild(job_id, expected_revision=1)
        return manifest

    def _initial_manifest(self, job_id, name, input_evidence, state, error=None, document=None):
        timestamp = _now()
        return {
            "id": job_id,
            "name": name,
            "state": state,
            "revision": 1,
            "context_revision": 0,
            "context": ProjectContext().model_dump(),
            "change_requests": [],
            "executions": [],
            "document": document,
            "validation": None,
            "error": error,
            "artifacts": {},
            "intent": None,
            "input": input_evidence,
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    def create_brief(self, text: str, name: str | None = None) -> dict:
        body = BriefRequest(text=text, name=name)
        job_id = uuid.uuid4().hex
        directory = self.root / job_id
        directory.mkdir()
        try:
            source = directory / "input.txt"
            with source.open("xb") as stream:
                stream.write(body.text.encode("utf-8"))
            manifest = self._initial_manifest(
                job_id,
                body.name.strip() if body.name else "Design project",
                {
                    "filename": source.name,
                    "name": source.name,
                    "kind": "brief",
                    "units": None,
                    "sha256": _sha256(source),
                },
                "needs_evidence",
            )
            manifest["context"] = ProjectContext(goal=body.text).model_dump()
            _atomic_json(directory / "manifest.json", manifest)
            return manifest
        except Exception:
            shutil.rmtree(directory)
            raise

    def _check_context_revision(self, manifest, expected):
        if expected != manifest["context_revision"]:
            raise RevisionConflict(
                f"Context revision {expected} is stale; current context revision is "
                f"{manifest['context_revision']}"
            )

    def update_context(self, job_id: str, context_revision: int, context: ProjectContext | dict) -> dict:
        body = ContextUpdate(context_revision=context_revision, context=context)
        with self._locked(job_id) as directory:
            manifest = self._read(directory)
            self._check_context_revision(manifest, body.context_revision)
            manifest["context"] = body.context.model_dump()
            manifest["context_revision"] += 1
            self._save(directory, manifest)
            return manifest

    def capture_change_request(self, job_id: str, command: ChangeRequestCommand | dict) -> dict:
        body = ChangeRequestCommand.model_validate(command)
        comparison = body.model_dump()
        with self._locked(job_id) as directory:
            manifest = self._read(directory)
            for request in manifest["change_requests"]:
                if request["id"] == body.request_id:
                    if request["command"] != comparison:
                        raise RevisionConflict("Request ID already belongs to a different command")
                    return {"job": manifest, "request": request}
            self._check_context_revision(manifest, body.context_revision)
            self._check_revision(manifest, body.revision)
            target = body.target.model_dump()
            if target["kind"] == "occurrence":
                document = manifest["document"] or {}
                occurrences = document.get("occurrences", [])
                selected = next(
                    (item for item in occurrences if item["id"] == target["occurrence_id"]), None
                )
                if selected is None:
                    raise ValueError("The target occurrence is not in the current project")
                definition_id = selected["definition_id"]
                if not any(item["id"] == definition_id for item in document["definitions"]):
                    raise ValueError("The target definition is not in the current project")
                target.update(
                    definition_id=definition_id,
                    affected_occurrence_ids=[
                        item["id"] for item in occurrences if item["definition_id"] == definition_id
                    ],
                )
            request = CapturedRequest(
                id=body.request_id,
                created_at=_now(),
                job_id=job_id,
                text=body.text,
                context_revision=body.context_revision,
                context=deepcopy(manifest["context"]),
                revision=body.revision,
                step_sha256=manifest["artifacts"].get("assembly.step", {}).get("sha256"),
                target=target,
                command=body,
            ).model_dump()
            manifest["change_requests"].append(request)
            self._save(directory, manifest)
            return {"job": manifest, "request": request}

    def create_document(
        self,
        document: AssemblyDocument | dict,
        name: str | None = None,
        *,
        defer_build: bool = False,
    ) -> dict:
        parsed = parse_document(document)
        if isinstance(parsed, NativeAssemblyDocument):
            raise ValueError("Create registered native cases through native-examples")
        if not parsed.definitions or not parsed.occurrences or parsed.input.units is None:
            raise ValueError(
                "A measured design must contain parts, occurrences and explicit input units"
            )
        if name is not None and (not isinstance(name, str) or not 1 <= len(name.strip()) <= 120):
            raise ValueError("Project name must contain 1 to 120 characters")
        content = parsed.model_dump_json(indent=2).encode()
        if len(content) > MAX_INPUT_BYTES:
            raise ValueError("Design exceeds the 30 MB input limit")
        job_id = uuid.uuid4().hex
        directory = self.root / job_id
        directory.mkdir()
        try:
            source = directory / "input.json"
            source.write_bytes(content)
            manifest = self._initial_manifest(
                job_id,
                name.strip() if name else parsed.name,
                {
                    "filename": source.name,
                    "name": source.name,
                    "kind": "recipe",
                    "units": parsed.input.units,
                    "sha256": _sha256(source),
                },
                "queued",
                document=parsed.model_dump(),
            )
            _atomic_json(directory / "manifest.json", manifest)
        except Exception:
            shutil.rmtree(directory)
            raise
        return manifest if defer_build else self.rebuild(job_id, 1)

    def get(self, job_id: str) -> dict:
        with self._locked(job_id) as directory:
            return self._read(directory)

    def create_native_example(self, command, *, defer_build=False):
        from .native import native_cases, native_document, registered_source

        NativeExampleCommand.model_validate(command)
        capability = native_cases()["cases"][0]
        if not capability["available"]:
            raise ValueError(capability["unavailable_reason"])
        document = native_document()
        job_id, build_id = uuid.uuid4().hex, uuid.uuid4().hex
        directory = self.root / job_id
        directory.mkdir()
        try:
            source = directory / "input.py"
            shutil.copyfile(registered_source(), source)
            manifest = self._initial_manifest(
                job_id, document.name,
                {"filename": source.name, "name": document.input.name, "kind": "native",
                 "units": "mm", "sha256": document.source_sha256},
                "queued", document=document.model_dump(),
            )
            execution = self._native_execution(manifest, build_id, None, 5.55)
            execution.update(base_revision=0, output_revision=1)
            manifest.update(build_id=build_id, executions=[execution])
            _atomic_json(directory / "manifest.json", manifest)
        except Exception:
            shutil.rmtree(directory)
            raise
        return manifest if defer_build else self.execute_native(job_id, build_id)

    def _native_execution(self, manifest, build_id, request_id, hook_top):
        timestamp = _now()
        return NativeExecution(
            id=uuid.uuid4().hex, request_id=request_id, command={"hook_top": hook_top},
            base_revision=manifest["revision"], output_revision=manifest["revision"] + 1,
            context_revision=manifest["context_revision"], build_id=build_id,
            base_step_sha256=manifest["artifacts"].get("assembly.step", {}).get("sha256"),
            created_at=timestamp, updated_at=timestamp,
        ).model_dump()

    def native_edit(
        self, job_id, command, *, defer_build=False, admit: Callable[[], None] | None = None
    ):
        body = NativeEditCommand.model_validate(command)
        with self._locked(job_id) as directory:
            manifest = self._read(directory)
            document = parse_document(manifest["document"] or {})
            if not isinstance(document, NativeAssemblyDocument):
                raise ValueError("Native edits require a registered native case")
            for execution in manifest["executions"]:
                if execution["request_id"] == body.request_id:
                    if execution["command"] != {"hook_top": body.hook_top}:
                        raise RevisionConflict("This capture already has a different native proposal")
                    return manifest
            request = next(
                (row for row in manifest["change_requests"] if row["id"] == body.request_id), None
            )
            if request is None:
                raise ValueError("Save a change request before executing its native proposal")
            self._check_revision(manifest, request["revision"])
            self._check_context_revision(manifest, request["context_revision"])
            step = self._artifact_path(directory, manifest, "assembly.step")
            if request["step_sha256"] != _sha256(step):
                raise RevisionConflict("The capture does not identify the current accepted STEP")
            target = request["target"]
            if target["kind"] == "occurrence" and (
                target["occurrence_id"] != "wiring_cover_1"
                or target["definition_id"] != "wiring_cover"
                or target["affected_occurrence_ids"] != ["wiring_cover_1"]
            ):
                raise RevisionConflict("The capture target does not match the registered native part")
            if body.hook_top == document.definitions[0].parameters.hook_top:
                raise ValueError("The native proposal must change hook_top")
            build_id = uuid.uuid4().hex
            execution = self._native_execution(manifest, build_id, body.request_id, body.hook_top)
            if admit is not None:
                admit()
            manifest["executions"].append(execution)
            manifest.update(state="queued", build_id=build_id, error=None)
            self._save(directory, manifest)
        return manifest if defer_build else self.execute_native(job_id, build_id)

    def _transition_native(self, execution, status, **values):
        execution.update(status=status, status_version=execution["status_version"] + 1,
                         updated_at=_now(), **values)

    def execute_native(self, job_id, build_id):
        from .native import build_native, registered_source

        with self._locked(job_id) as directory:
            manifest = self._read(directory)
            execution = next(
                (row for row in manifest["executions"] if row["build_id"] == build_id), None
            )
            if execution is None or execution["status"] != "queued":
                return manifest
            if manifest.get("build_id") != build_id:
                self._transition_native(execution, "stale")
                self._save(directory, manifest)
                return manifest
            document = parse_document(manifest["document"])
            if not isinstance(document, NativeAssemblyDocument):
                raise ValueError("Native execution requires a registered native document")
            base_document = document.model_dump()
            document.definitions[0].parameters.hook_top = execution["command"]["hook_top"]
            previous = (manifest.get("validation") or {}).get("native")
            self._transition_native(execution, "building")
            manifest["state"] = "building"
            self._save(directory, manifest)
        attempt = directory / "revisions" / f"{execution['output_revision']}-{build_id}"
        try:
            attempt.mkdir(parents=True)
            result = build_native(document, attempt, previous=previous,
                                  base_revision=execution["base_revision"])
            artifacts = self._validated_artifacts(document, attempt, result)
            error = None
        except Exception as exc:
            error = {"code": type(exc).__name__, "message": str(exc)}
        with self._locked(job_id):
            current = self._read(directory)
            run = next(row for row in current["executions"] if row["id"] == execution["id"])
            if run["status"] != "building":
                return current
            if error is None:
                try:
                    registered_source()
                except (OSError, ValueError) as exc:
                    error = {"code": type(exc).__name__, "message": str(exc)}
            stale = (
                current.get("build_id") != build_id
                or current["revision"] != manifest["revision"]
                or current["context_revision"] != execution["context_revision"]
                or current["document"] != base_document
                or current["artifacts"].get("assembly.step", {}).get("sha256")
                != execution["base_step_sha256"]
            )
            if not stale and execution["base_step_sha256"] is not None:
                try:
                    self._artifact_path(directory, {**current, "state": "ready"}, "assembly.step")
                except ArtifactUnavailable as exc:
                    stale = True
                    error = {"code": type(exc).__name__, "message": str(exc)}
            if stale or error:
                failure = error or {"code": "stale_native_execution",
                                    "message": "Geometry or captured context changed during execution"}
                self._transition_native(run, "stale" if stale else "failed", error=failure)
                if current.get("build_id") == build_id:
                    current.pop("build_id", None)
                    current.update(state="ready" if current["artifacts"] else "failed", error=failure)
            else:
                self._transition_native(run, "accepted", output_step_sha256=artifacts["assembly.step"]["sha256"])
                current.update(
                    state="ready", revision=run["output_revision"], document=document.model_dump(),
                    validation=result["validation"], artifacts=artifacts, intent=None, error=None,
                    artifact_directory=str(attempt.relative_to(directory)),
                )
                current.pop("build_id", None)
            self._save(directory, current)
            return current

    def list(self) -> list[dict]:
        jobs = []
        for directory in self.root.iterdir():
            if _JOB_ID.fullmatch(directory.name) and (directory / "manifest.json").is_file():
                try:
                    jobs.append(self.get(directory.name))
                except (FileNotFoundError, json.JSONDecodeError):
                    continue
        return sorted(jobs, key=lambda job: job["created_at"], reverse=True)

    def _clear_exports(self, manifest):
        manifest.update(artifacts={}, validation=None, intent=None, error=None)
        manifest.pop("artifact_directory", None)
        manifest.pop("build_id", None)

    def _validate_mesh_size(self, path):
        with path.open("rb") as stream:
            header = stream.read(84)
            if len(header) >= 84:
                count = struct.unpack("<I", header[80:84])[0]
                if 84 + 50 * count == path.stat().st_size:
                    if count > MAX_TRIANGLES:
                        raise ValueError(f"STL exceeds the {MAX_TRIANGLES} triangle limit")
                    return
            stream.seek(0)
            count = 0
            for line in stream:
                count += line.lstrip().lower().startswith(b"facet normal")
                if count > MAX_TRIANGLES:
                    raise ValueError(f"STL exceeds the {MAX_TRIANGLES} triangle limit")

    def rebuild(self, job_id: str, expected_revision: int | None = None) -> dict:
        with self._locked(job_id) as directory:
            manifest = self._read(directory)
            self._check_revision(manifest, expected_revision)
            if (manifest["document"] or {}).get("backend") == "smlibpy":
                raise ValueError("Native cases require a new captured native edit, not legacy rebuild")
            if manifest["state"] == "building":
                raise RevisionConflict("This revision is already building")
            if manifest["document"] is None and (
                manifest["input"]["kind"] != "stl" or manifest["input"]["units"] is None
            ):
                return manifest
            self._clear_exports(manifest)
            revision = manifest["revision"]
            build_id = uuid.uuid4().hex
            manifest.update(state="building", build_id=build_id)
            self._save(directory, manifest)
        attempt = directory / "revisions" / f"{revision}-{build_id}"
        try:
            attempt.mkdir(parents=True)
            if manifest["document"] is None:
                from .reconstruction import inspect_stl

                source = directory / manifest["input"]["filename"]
                self._validate_mesh_size(source)
                document = inspect_stl(source, manifest["input"]["units"])
            else:
                document = parse_document(manifest["document"])
            if not document.definitions or not document.occurrences:
                raise ValueError("Design must contain at least one part definition and occurrence")
            from .geometry import build_assembly

            reference = (
                directory / manifest["input"]["filename"]
                if manifest["input"]["kind"] == "stl" and manifest["document"] is None
                else None
            )
            result = build_assembly(document, attempt, reference_mesh=reference)
            validation = result["validation"]
            artifacts = self._validated_artifacts(document, attempt, result)
            with self._locked(job_id):
                current = self._read(directory)
                if current.get("build_id") != build_id or current["revision"] != revision:
                    return current
                current.update(
                    state="ready",
                    document=document.model_dump(),
                    validation=validation,
                    artifacts=artifacts,
                    artifact_directory=str(attempt.relative_to(directory)),
                    error=None,
                )
                current.pop("build_id", None)
                self._save(directory, current)
                return current

        except Exception as exc:
            with self._locked(job_id):
                current = self._read(directory)
                if current.get("build_id") != build_id or current["revision"] != revision:
                    return current
                current.update(
                    state="failed",
                    error={"code": type(exc).__name__, "message": str(exc)},
                    artifacts={},
                    validation=None,
                )
                current.pop("build_id", None)
                self._save(directory, current)
                return current

    def _validated_artifacts(self, document, attempt, result):
        validation = result["validation"]
        if validation.get("valid") is not True:
            raise ValueError("Geometry validation rejected the assembly")
        if validation.get("roundtrip_valid") is not True:
            raise ValueError("STEP readback validation rejected the assembly")
        if validation.get("solid_count") != len(document.occurrences):
            raise ValueError("STEP solid count does not match assembly occurrences")
        required_files = [
            "assembly.step", "source.py", "document.json", "preview.json", "validation.json",
        ]
        if isinstance(document, NativeAssemblyDocument):
            from .native_worker import STAGES

            required_files += [
                "final.smb", "parameters.json", "rebuild.py", "provenance.json", "NOTICE.txt",
                "construction.json", "native-report.json",
            ]
            required_files += [
                f"checkpoints/{index + 1:02}-{stage}.{suffix}"
                for index, stage in enumerate(STAGES) for suffix in ("smb", "json")
            ]
            if _sha256(attempt / "source.py") != document.source_sha256:
                raise ValueError("Native source artifact changed")
            if json.loads((attempt / "document.json").read_text()) != document.model_dump():
                raise ValueError("Native document artifact does not match the proposal")
        for required in required_files:
            if not (attempt / required).is_file():
                raise ValueError(f"Geometry did not produce {required}")
        return self._collect_artifacts(attempt)

    def _collect_artifacts(self, directory):
        artifacts = {}
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise ValueError("Artifact output must not contain symbolic links")
            if path.is_file():
                filename = path.relative_to(directory).as_posix()
                _relative_name(filename)
                artifacts[filename] = {
                    "path": filename,
                    "sha256": _sha256(path),
                    "size": path.stat().st_size,
                }
        return artifacts

    def set_design(
        self,
        job_id: str,
        expected_revision: int,
        document: AssemblyDocument | dict,
        *,
        defer_build: bool = False,
    ) -> dict:
        if type(expected_revision) is not int:
            raise RevisionConflict("An integer expected revision is required")
        parsed = parse_document(document)
        if isinstance(parsed, NativeAssemblyDocument):
            raise ValueError("Native cases require a captured native edit")
        if not parsed.definitions or not parsed.occurrences:
            raise ValueError("A measured design must contain definitions and occurrences")
        if parsed.input.units is None:
            raise ValueError(
                "A measured design must state its input units; recipe dimensions use mm"
            )
        with self._locked(job_id) as directory:
            manifest = self._read(directory)
            self._check_revision(manifest, expected_revision)
            if (manifest["document"] or {}).get("backend") == "smlibpy":
                raise ValueError("Native cases require a captured native edit")
            self._clear_exports(manifest)
            manifest.update(
                document=parsed.model_dump(), state="queued", revision=manifest["revision"] + 1
            )
            self._save(directory, manifest)
        return manifest if defer_build else self.rebuild(job_id, manifest["revision"])

    def edit(
        self,
        job_id: str,
        expected_revision: int,
        definition_id: str,
        parameters: dict | None = None,
        holes: list | None = None,
        *,
        defer_build: bool = False,
    ) -> dict:
        if type(expected_revision) is not int:
            raise RevisionConflict("An integer expected revision is required")
        with self._locked(job_id) as directory:
            manifest = self._read(directory)
            self._check_revision(manifest, expected_revision)
            if manifest["document"] is None:
                raise ValueError("Provide a measured design before editing parts")
            if manifest["document"].get("backend") == "smlibpy":
                raise ValueError("Native cases require a captured native edit")
            document = manifest["document"]
            definition = next(
                (part for part in document["definitions"] if part["id"] == definition_id), None
            )
            if definition is None:
                raise ValueError(f"Unknown part definition {definition_id!r}")
            if parameters is None and holes is None:
                raise ValueError("Supply parameters or holes to edit")
            if "fit" in definition["evidence"]:
                definition["evidence"]["reconstruction_fit"] = {
                    "revision": manifest["revision"],
                    "recipe": deepcopy(definition["recipe"]),
                    "metrics": definition["evidence"].pop("fit"),
                }
                definition["evidence"]["modified_from_input"] = True
            if parameters is not None:
                definition["recipe"]["parameters"].update(parameters)
            if holes is not None:
                definition["recipe"]["holes"] = holes
            parsed = AssemblyDocument.model_validate(document)
            self._clear_exports(manifest)
            manifest.update(
                document=parsed.model_dump(), state="queued", revision=manifest["revision"] + 1
            )
            self._save(directory, manifest)
        return manifest if defer_build else self.rebuild(job_id, manifest["revision"])

    def cancel(self, job_id: str) -> dict:
        with self._locked(job_id) as directory:
            manifest = self._read(directory)
            if (manifest["document"] or {}).get("backend") == "smlibpy":
                for execution in manifest["executions"]:
                    if execution["status"] in {"queued", "building"}:
                        self._transition_native(execution, "stale", error={
                            "code": "cancelled", "message": "Native execution was cancelled",
                        })
                manifest.pop("build_id", None)
                manifest.update(state="ready" if manifest["artifacts"] else "cancelled", error=None)
                self._save(directory, manifest)
                return manifest
            self._clear_exports(manifest)
            manifest.update(state="cancelled", revision=manifest["revision"] + 1)
            self._save(directory, manifest)
            return manifest

    def _artifact_path(self, directory, manifest, filename):
        name = _relative_name(filename)
        if manifest["state"] != "ready" or filename not in manifest["artifacts"]:
            raise ArtifactUnavailable("No accepted artifact exists for the current revision")
        base = directory / manifest["artifact_directory"]
        path = base / str(name)
        if base.is_symlink() or any(
            parent.is_symlink() for parent in path.parents if parent != directory
        ):
            raise ArtifactUnavailable("Artifact path is not authorized")
        if (
            path.is_symlink()
            or not path.is_file()
            or not path.resolve().is_relative_to(base.resolve())
        ):
            raise ArtifactUnavailable("Artifact path is not authorized")
        metadata = manifest["artifacts"][filename]
        if path.stat().st_size != metadata["size"] or _sha256(path) != metadata["sha256"]:
            raise ArtifactUnavailable(
                "Artifact has changed since validation; rebuild this revision"
            )
        return path

    def artifact(self, job_id: str, filename: str) -> Path:
        with self._locked(job_id) as directory:
            return self._artifact_path(directory, self._read(directory), filename)

    def bundle(self, job_id: str) -> Path:
        with self._locked(job_id) as directory:
            manifest = self._read(directory)
            if manifest["state"] != "ready":
                raise ArtifactUnavailable("Build and validate this revision before downloading")
            files = {
                name: self._artifact_path(directory, manifest, name)
                for name in manifest["artifacts"]
            }
            target = directory / f"bundle-{manifest['revision']}-{uuid.uuid4().hex}.zip"
            temporary = target.with_suffix(".tmp")
            try:
                with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr("manifest.json", json.dumps(manifest, indent=2))
                    for name, path in files.items():
                        archive.write(path, name)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
            return target

    def update_intent(self, job_id: str, revision: int, result: dict) -> dict:
        with self._locked(job_id) as directory:
            manifest = self._read(directory)
            if (manifest["document"] or {}).get("backend") == "smlibpy":
                raise ValueError("Factory intent is not supported for registered native cases")
            self._check_revision(manifest, revision)
            step = self._artifact_path(directory, manifest, "assembly.step")
            artifacts = self._collect_artifacts(step.parent)
            for name, metadata in manifest["artifacts"].items():
                if artifacts.get(name) != metadata:
                    raise ArtifactUnavailable(
                        "Intent writing changed an accepted geometry artifact"
                    )
            requested = result.get("artifacts", {})
            names = requested.keys() if isinstance(requested, dict) else requested
            for name in names:
                _relative_name(name)
                if name not in artifacts:
                    raise ArtifactUnavailable(f"Intent did not produce {name}")
                manifest["artifacts"][name] = artifacts[name]
            manifest["intent"] = result
            self._save(directory, manifest)
            return manifest
