import base64
import json
import mimetypes
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP, Image

from .context import BriefRequest, ContextUpdate
from .decomposition import DecompositionStore
from .document import AssemblyDocument
from .intent import questions, write_intent
from .native import native_cases


def create_mcp(store):
    decomposition = DecompositionStore(store.root)
    mcp = FastMCP("OpenSkyfall", host="127.0.0.1", port=8767)
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="assembly-mcp")

    def rebuild(job):
        if (job["document"] or {}).get("backend") == "smlibpy":
            if job["state"] == "queued":
                pool.submit(store.execute_native, job["id"], job.get("build_id"))
        else:
            pool.submit(store.rebuild, job["id"], job["revision"])
        return job

    @mcp.tool(structured_output=True)
    def workspace_request(method: str, path: str, payload: dict | None = None) -> dict[str, Any]:
        """Manage project context and CAD changes from the conversation. Paths match the documented /api interface. Import assets as name, units and data_base64. Read jobs, preserve context, capture requests, execute supported geometry, review factory questions or download artifacts. The side window displays STEP rather than editing project context. Do not invent units or factory confirmations."""
        payload = payload or {}
        if path.startswith(
            ("/api/decompositions", "/api/decomposition-")
        ):
            return decomposition.request(method, path, payload)
        if method == "GET" and path == "/api/native-cases":
            return native_cases()
        if method == "POST" and path == "/api/native-examples":
            return rebuild(store.create_native_example(payload, defer_build=True))
        if method == "POST" and path == "/api/briefs":
            body = BriefRequest.model_validate(payload)
            return store.create_brief(body.text, body.name)
        if method == "GET" and path == "/api/design-schema":
            return {
                "schema": AssemblyDocument.model_json_schema(),
                "coordinates": "Millimeters. Recipes are centered at the local origin. Holes and cylinder height use local Z. Occurrence transforms map local column vectors to parents.",
            }
        if method == "GET" and path == "/api/jobs":
            return {"jobs": store.list()}
        if method == "GET" and path == "/api/demo":
            from .fixtures import create_demo

            demo_dir = Path(store.root) / "demo"
            demo = create_demo(demo_dir)
            source = demo.get("input") or demo.get("stl") or demo.get("input_path")
            return rebuild(
                store.create(Path(source), "mm", "Generated mechanical sample", defer_build=True)
            )
        if method == "POST" and path == "/api/jobs":
            name = Path(str(payload.get("name", "input.stl"))).name
            raw = base64.b64decode(payload.get("data_base64", ""), validate=True)
            if not raw or len(raw) > 30 * 1024 * 1024:
                raise ValueError("Input must contain 1 byte to 30 MB")
            import hashlib

            inbox = Path(store.root) / "mcp-inbox" / hashlib.sha256(raw).hexdigest()
            inbox.mkdir(parents=True, exist_ok=True)
            target = inbox / name
            target.write_bytes(raw)
            return rebuild(store.create(target, payload.get("units"), name, defer_build=True))
        match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)(?:/(.*))?", path)
        if not match:
            raise ValueError("Unsupported workspace path")
        job_id, action = match.groups()
        if method == "GET" and not action:
            return store.get(job_id)
        if method == "PATCH" and action == "context":
            body = ContextUpdate.model_validate(payload)
            return store.update_context(job_id, body.context_revision, body.context)
        if method == "POST" and action == "change-requests":
            return store.capture_change_request(job_id, payload)
        if method == "POST" and action == "native-edits":
            admitted = False

            def admit():
                nonlocal admitted
                admitted = True

            job = store.native_edit(job_id, payload, defer_build=True, admit=admit)
            return rebuild(job) if admitted else job
        if method == "GET" and action == "intent":
            return questions(store, job_id)
        if method == "POST" and action == "intent":
            return write_intent(
                store,
                job_id,
                payload["revision"],
                payload["analysis_id"],
                payload.get("answers", {}),
                payload.get("confirmed", False),
                payload.get("accept_defaults", False),
            )
        if method == "POST" and action == "cancel":
            return store.cancel(job_id)
        if method == "POST" and action == "rebuild":
            job = store.get(job_id)
            if (job["document"] or {}).get("backend") == "smlibpy":
                raise ValueError(
                    "Native cases require a new captured native edit, not legacy rebuild"
                )
            if payload["revision"] != job["revision"]:
                raise ValueError("Revision changed; inspect the current assembly first")
            return rebuild(job)
        if method == "POST" and action == "design":
            doc = AssemblyDocument.model_validate(payload["document"])
            return rebuild(store.set_design(job_id, payload["revision"], doc, defer_build=True))
        if method == "PATCH" and action and action.startswith("parts/"):
            return rebuild(
                store.edit(
                    job_id,
                    payload["revision"],
                    action[6:],
                    payload.get("parameters"),
                    payload.get("holes"),
                    defer_build=True,
                )
            )
        if method == "GET" and action and action.startswith("artifacts/"):
            artifact = store.artifact(job_id, action[10:])
        elif method == "GET" and action == "bundle":
            artifact = store.bundle(job_id)
        else:
            raise ValueError("Unsupported workspace operation")
        if artifact.suffix == ".json":
            return json.loads(artifact.read_text())
        return {
            "filename": artifact.name,
            "mime_type": mimetypes.guess_type(artifact.name)[0] or "application/octet-stream",
            "data_base64": base64.b64encode(artifact.read_bytes()).decode(),
        }

    @mcp.tool(
        structured_output=True,
        meta={
            "ui": {"resourceUri": "ui://open-assembly/workspace-v1.html"},
            "openai/ui": {"entrypoints": [{"type": "thread"}]},
        },
    )
    def show_assembly(job_id: str | None = None) -> dict[str, Any]:
        """Open the STEP viewer beside the conversation for this job. Manage project context and CAD edits with workspace_request. The pane provides model inspection and current STEP download, without project or parameter forms. Geometry execution and factory confirmation remain separate."""
        return store.get(job_id) if job_id else {"jobs": store.list()}

    @mcp.tool(
        structured_output=True,
        meta={
            "ui": {"resourceUri": "ui://open-assembly/decomposition-v1.html"},
            "openai/ui": {"entrypoints": [{"type": "thread"}]},
        },
    )
    def show_decomposition(project_id: str) -> dict[str, Any]:
        """Show agent-authored image decomposition beside chat. This is concept geometry, not verified recovered CAD. Create an image with workspace_request POST /api/decompositions, inspect it with get_decomposition_image, then GET /api/decomposition-schema and PUT a source-bound plan at /api/decompositions/{id}/plan."""
        return decomposition.get(project_id)

    @mcp.tool()
    def get_decomposition_image(project_id: str) -> Image:
        """Read the actual source reference before proposing physical parts and geometry. Do not infer hidden structure or metric scale as observed facts."""
        source = decomposition.reference(project_id)
        return Image(data=source.read_bytes(), format="png")

    @mcp.tool()
    def get_reference_image(job_id: str) -> Image:
        """Read the authorized reference image for this job so the chat model can propose measured bounded recipes. Missing scale and hidden geometry remain unresolved. This tool does not reconstruct CAD."""
        from io import BytesIO

        from PIL import Image as PILImage

        manifest = store.get(job_id)
        if manifest["input"]["kind"] != "image":
            raise ValueError("This job does not contain an image reference")
        source = store.job_directory(job_id) / manifest["input"]["filename"]
        with PILImage.open(source) as image:
            image.thumbnail((1600, 1600))
            buffer = BytesIO()
            image.convert("RGB").save(buffer, format="PNG")
        return Image(data=buffer.getvalue(), format="png")

    @mcp.resource("ui://open-assembly/workspace-v1.html", mime_type="text/html;profile=mcp-app")
    def workspace_ui() -> str:
        root = Path(__file__).resolve().parents[2]
        packaged = Path(__file__).resolve().parent / "web_dist"
        dist = packaged if packaged.is_dir() else root / "web" / "dist"
        index = dist / "index.html"
        if not index.exists():
            return "<p>Build the Open Assembly viewer with npm ci and npm run build in web/.</p>"
        html = index.read_text().replace("<body>", '<body data-viewer="step">')

        def script(match):
            text = (dist / match.group(1).lstrip("/")).read_text().replace("</script", "<\\/script")
            return f'<script type="module">{text}</script>'

        def style(match):
            return "<style>" + (dist / match.group(1).lstrip("/")).read_text() + "</style>"

        html = re.sub(r'<script[^>]*src="([^"]+)"[^>]*></script>', script, html)
        return re.sub(r'<link[^>]*href="([^"]+\.css)"[^>]*>', style, html)

    @mcp.resource("ui://open-assembly/decomposition-v1.html", mime_type="text/html;profile=mcp-app")
    def decomposition_ui() -> str:
        return workspace_ui().replace('data-viewer="step"', 'data-viewer="decomposition"')

    return mcp
