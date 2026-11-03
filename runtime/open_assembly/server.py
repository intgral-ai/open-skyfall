"""Local HTTP adapter for the revisioned project store. Importing starts no service."""

import importlib
import ipaddress
import mimetypes
import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from starlette.concurrency import run_in_threadpool

from .context import BriefRequest, ChangeRequestCommand, ContextUpdate
from .decomposition import DecompositionStore
from .document import AssemblyDocument
from .native import NativeEditCommand, NativeExampleCommand, native_cases
from .project import MAX_INPUT_BYTES, ArtifactUnavailable, ProjectStore, RevisionConflict


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: StrictInt = Field(ge=1)


class EditRequest(RevisionRequest):
    parameters: dict[str, float] | None = None
    holes: list[dict] | None = None


class DesignRequest(RevisionRequest):
    document: AssemblyDocument


class IntentRequest(RevisionRequest):
    analysis_id: str = Field(min_length=1, max_length=128)
    answers: dict[str, dict]
    confirmed: bool = False
    accept_defaults: bool = False


def _local_host(value):
    if value.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def _trusted_request(request, mutation=False):
    try:
        url = urlsplit(f"http://{request.headers.get('host', '')}")
        host = url.hostname
        if (
            not host
            or not _local_host(host)
            or url.username
            or url.password
            or url.path
            or url.query
            or url.fragment
        ):
            return False
        _ = url.port
    except ValueError:
        return False
    if mutation:
        if request.client is None or not _local_host(request.client.host):
            return False
        origin = request.headers.get("origin")
        if origin:
            try:
                parsed = urlsplit(origin)
                if (
                    parsed.scheme != request.url.scheme
                    or parsed.netloc != request.headers.get("host")
                    or parsed.path not in {"", "/"}
                    or parsed.query
                    or parsed.fragment
                ):
                    return False
            except ValueError:
                return False
        if request.headers.get("sec-fetch-site") == "cross-site":
            return False
    return True


class _BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        total = 0

        async def bounded_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > MAX_INPUT_BYTES + 1024 * 1024:
                raise HTTPException(413, "Request exceeds the 30 MB upload limit")
            return message

        await self.app(scope, bounded_receive, send)


def create_app(store=None):
    store = store or ProjectStore(
        os.environ.get("OPEN_ASSEMBLY_DATA", "~/.local/share/open-assembly-cad")
    )
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="assembly-build")
    capacity = threading.BoundedSemaphore(16)

    @asynccontextmanager
    async def lifespan(app):
        yield
        executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="Open Assembly CAD", lifespan=lifespan)
    app.state.store = store
    decomposition = DecompositionStore(store.root)
    app.add_middleware(_BodyLimit)

    @app.middleware("http")
    async def local_requests(request, call_next):
        mutation = (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            or request.url.path in {"/api/demo", "/api/decomposition-anatomy-example"}
        )
        if not _trusted_request(request, mutation):
            return JSONResponse(
                {"detail": "Use a trusted local host and same-origin browser"}, status_code=403
            )
        length = request.headers.get("content-length")
        if length:
            try:
                if int(length) > MAX_INPUT_BYTES + 1024 * 1024:
                    return JSONResponse(
                        {"detail": "Request exceeds the 30 MB upload limit"}, status_code=413
                    )
            except ValueError:
                return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(RevisionConflict)
    @app.exception_handler(ArtifactUnavailable)
    async def conflict(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(FileNotFoundError)
    async def missing(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    def reserve():
        if not capacity.acquire(blocking=False):
            raise HTTPException(503, "The local build queue is full; retry after a build finishes")

    def schedule(job):
        def build():
            try:
                if (job["document"] or {}).get("backend") == "smlibpy":
                    store.execute_native(job["id"], job.get("build_id"))
                else:
                    store.rebuild(job["id"], job["revision"])
            except RevisionConflict:
                pass
            finally:
                capacity.release()

        try:
            executor.submit(build)
        except Exception:
            capacity.release()
            raise
        return job

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "open-assembly-cad"}

    @app.get("/api/jobs")
    def jobs():
        return store.list()

    @app.get("/api/native-cases")
    def registered_native_cases():
        return native_cases()

    @app.post("/api/native-examples", status_code=202)
    def create_native_example(body: NativeExampleCommand):
        reserve()
        try:
            job = store.create_native_example(body, defer_build=True)
        except Exception:
            capacity.release()
            raise
        return schedule(job)

    @app.post("/api/jobs/{job_id}/native-edits", status_code=202)
    def native_edit(job_id: str, body: NativeEditCommand):
        admitted = False

        def admit():
            nonlocal admitted
            reserve()
            admitted = True

        try:
            job = store.native_edit(job_id, body, defer_build=True, admit=admit)
        except Exception:
            if admitted:
                capacity.release()
            raise
        return schedule(job) if admitted else job

    @app.post("/api/jobs", status_code=202)
    async def create_job(
        file: Annotated[UploadFile, File()],
        units: Annotated[str | None, Form()] = None,
        name: Annotated[str | None, Form()] = None,
    ):
        reserve()
        pending = True
        suffix = Path(file.filename or "").suffix.lower()
        try:
            with tempfile.TemporaryDirectory(prefix="assembly-upload-") as temporary:
                path = Path(temporary) / (Path(file.filename or f"upload{suffix}").name[:240])
                size = 0
                with path.open("xb") as output:
                    while chunk := await file.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_INPUT_BYTES:
                            raise HTTPException(413, "Upload exceeds 30 MB")
                        output.write(chunk)
                job = await run_in_threadpool(
                    store.create, path, units or None, name, defer_build=True
                )
            if job["state"] == "queued":
                pending = False
                return schedule(job)
            return job
        finally:
            await file.close()
            if pending:
                capacity.release()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        return store.get(job_id)

    @app.post("/api/briefs", status_code=201)
    def create_brief(body: BriefRequest):
        return store.create_brief(body.text, body.name)

    @app.patch("/api/jobs/{job_id}/context")
    def update_context(job_id: str, body: ContextUpdate):
        return store.update_context(job_id, body.context_revision, body.context)

    @app.post("/api/jobs/{job_id}/change-requests", status_code=201)
    def capture_change_request(job_id: str, body: ChangeRequestCommand):
        return store.capture_change_request(job_id, body)

    @app.patch("/api/jobs/{job_id}/parts/{definition_id}", status_code=202)
    def edit_part(job_id: str, definition_id: str, body: EditRequest):
        reserve()
        try:
            job = store.edit(
                job_id, body.revision, definition_id, body.parameters, body.holes, defer_build=True
            )
        except Exception:
            capacity.release()
            raise
        return schedule(job)

    @app.post("/api/jobs/{job_id}/design", status_code=202)
    def set_design(job_id: str, body: DesignRequest):
        reserve()
        try:
            job = store.set_design(job_id, body.revision, body.document, defer_build=True)
        except Exception:
            capacity.release()
            raise
        return schedule(job)

    @app.post("/api/jobs/{job_id}/rebuild", status_code=202)
    def rebuild(job_id: str, body: RevisionRequest):
        reserve()
        try:
            job = store.get(job_id)
            if (job["document"] or {}).get("backend") == "smlibpy":
                raise ValueError(
                    "Native cases require a new captured native edit, not legacy rebuild"
                )
            if job["revision"] != body.revision or job["state"] == "building":
                raise RevisionConflict("Revision is stale or already building")
        except Exception:
            capacity.release()
            raise
        return schedule(job)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel(job_id: str):
        return store.cancel(job_id)

    @app.get("/api/jobs/{job_id}/artifacts/{filename:path}")
    def artifact(job_id: str, filename: str):
        path = store.artifact(job_id, filename)
        media_type = (
            "application/json" if path.suffix == ".json" else mimetypes.guess_type(path.name)[0]
        )
        return FileResponse(
            path, filename=path.name, media_type=media_type or "application/octet-stream"
        )

    @app.get("/api/design-schema")
    def design_schema():
        from .document import AssemblyDocument

        return {
            "schema": AssemblyDocument.model_json_schema(),
            "coordinates": "Millimeters; centered local recipes; local Z hole/cylinder axis; rigid local-to-parent transforms.",
        }

    @app.get("/api/jobs/{job_id}/bundle")
    def bundle(job_id: str):
        return FileResponse(
            store.bundle(job_id), filename=f"assembly-{job_id}.zip", media_type="application/zip"
        )

    @app.get("/api/jobs/{job_id}/intent")
    def intent_questions(job_id: str):
        try:
            adapter = importlib.import_module("open_assembly.intent")
        except ImportError as exc:
            raise HTTPException(409, "Factory intent requires the pinned Specify engine") from exc
        return adapter.questions(store, job_id)

    @app.post("/api/jobs/{job_id}/intent")
    def write_intent(job_id: str, body: IntentRequest):
        try:
            adapter = importlib.import_module("open_assembly.intent")
        except ImportError as exc:
            raise HTTPException(409, "Factory intent requires the pinned Specify engine") from exc
        return adapter.write_intent(
            store,
            job_id,
            body.revision,
            body.analysis_id,
            body.answers,
            confirmed=body.confirmed,
            accept_defaults=body.accept_defaults,
        )

    @app.get("/api/demo", status_code=202)
    def demo():
        existing = [job for job in store.list() if job.get("name") == "Server demo"]
        if existing:
            return existing[0]
        reserve()
        try:
            from .fixtures import create_demo

            with tempfile.TemporaryDirectory(prefix="assembly-demo-") as temporary:
                result = create_demo(Path(temporary))
                source = result.get("input") or result.get("stl") or result.get("path")
                if source is None:
                    raise ValueError("Demo generator did not return an input STL path")
                job = store.create(source, "mm", "Server demo", defer_build=True)
        except Exception:
            capacity.release()
            raise
        return schedule(job)

    @app.get("/api/decomposition-schema")
    def decomposition_schema():
        return decomposition.request("GET", "/api/decomposition-schema")

    @app.get("/api/decomposition-example")
    def decomposition_example():
        return decomposition.request("GET", "/api/decomposition-example")

    @app.get("/api/decomposition-anatomy-example")
    def anatomy_decomposition_example():
        return decomposition.request("GET", "/api/decomposition-anatomy-example")

    @app.get("/api/decompositions")
    def list_decompositions():
        return decomposition.request("GET", "/api/decompositions")

    @app.post("/api/decompositions", status_code=201)
    def create_decomposition(payload: dict):
        return decomposition.request("POST", "/api/decompositions", payload)

    @app.get("/api/decompositions/{project_id}")
    def get_decomposition(project_id: str):
        return decomposition.get(project_id)

    @app.put("/api/decompositions/{project_id}/plan")
    def put_decomposition(project_id: str, payload: dict):
        return decomposition.update(project_id, payload)

    @app.post("/api/decompositions/{project_id}/workflow/{action}")
    def decomposition_workflow_action(project_id: str, action: str, payload: dict):
        return decomposition.request(
            "POST", f"/api/decompositions/{project_id}/workflow/{action}", payload
        )

    @app.get("/api/decompositions/{project_id}/workflow/builds/{build_id}/artifacts/{name:path}")
    def decomposition_native_artifact(project_id: str, build_id: str, name: str):
        from .decomposition_workflow import DecompositionWorkflow

        artifact = DecompositionWorkflow(decomposition).artifact(project_id, build_id, name)
        return FileResponse(
            artifact,
            filename=artifact.name,
            media_type="application/step"
            if artifact.suffix == ".step"
            else mimetypes.guess_type(artifact.name)[0] or "application/octet-stream",
        )

    @app.get("/api/decompositions/{project_id}/reference")
    def decomposition_reference(project_id: str):
        return FileResponse(decomposition.reference(project_id), media_type="image/png")

    @app.get("/api/decompositions/{project_id}/bundle")
    def decomposition_bundle(project_id: str):
        return FileResponse(
            decomposition.bundle(project_id),
            media_type="application/zip",
            filename="decomposition.zip",
        )

    @app.get("/api/decompositions/{project_id}/revisions/{revision}")
    def decomposition_revision(project_id: str, revision: int):
        return decomposition.revision(project_id, revision)

    @app.get("/api/decompositions/{project_id}/revisions/{revision}/bundle")
    def decomposition_revision_bundle(project_id: str, revision: int):
        return FileResponse(
            decomposition.bundle(project_id, revision),
            media_type="application/zip",
            filename=f"decomposition-r{revision}.zip",
        )

    @app.get("/api/decompositions/{project_id}/artifacts/{name:path}")
    def decomposition_artifact(project_id: str, name: str):
        artifact = decomposition.artifact(project_id, name)
        return FileResponse(
            artifact,
            media_type=mimetypes.guess_type(artifact.name)[0] or "application/octet-stream",
        )

    packaged = Path(__file__).resolve().parent / "web_dist"
    dist = packaged if packaged.is_dir() else Path(__file__).resolve().parents[2] / "web" / "dist"
    if dist.is_dir() and (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    else:

        @app.get("/")
        def root():
            return PlainTextResponse(
                "Open Assembly CAD local service. API docs at /docs. "
                "Build web/dist to install the browser interface."
            )

    return app
