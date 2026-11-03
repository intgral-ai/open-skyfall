import asyncio
import base64
from datetime import timedelta
from io import BytesIO
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image


def test_stdio_tools_resource_and_authorized_reference_image(tmp_path):
    async def exercise():
        executable = Path(__file__).resolve().parents[1] / ".venv/bin/open-assembly"
        params = StdioServerParameters(
            command=str(executable), args=["--workspace", str(tmp_path), "mcp"]
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(
                reader, writer, read_timeout_seconds=timedelta(seconds=30)
            ) as session:
                await session.initialize()
                tools = await session.list_tools()
                indexed = {tool.name: tool for tool in tools.tools}
                assert {"workspace_request", "show_assembly", "get_reference_image"} <= set(indexed)
                assert indexed["show_assembly"].meta["ui"]["resourceUri"].startswith("ui://")
                resource = await session.read_resource("ui://open-assembly/workspace-v1.html")
                html = resource.contents[0].text
                assert "Open Assembly" in html
                assert "workspace_request" in html
                assert 'src="/assets/' not in html
                image = BytesIO()
                Image.new("RGB", (80, 50), "white").save(image, format="PNG")
                result = await session.call_tool(
                    "workspace_request",
                    {
                        "method": "POST",
                        "path": "/api/jobs",
                        "payload": {
                            "name": "reference.png",
                            "units": "mm",
                            "data_base64": base64.b64encode(image.getvalue()).decode(),
                        },
                    },
                )
                assert not result.isError
                job = result.structuredContent
                assert job["state"] == "needs_evidence"
                rendered = await session.call_tool("get_reference_image", {"job_id": job["id"]})
                assert not rendered.isError
                assert rendered.content[0].type == "image"
                example = Path(__file__).resolve().parents[1] / "examples/decomposition"
                created = await session.call_tool(
                    "workspace_request",
                    {
                        "method": "POST",
                        "path": "/api/decompositions",
                        "payload": {
                            "name": "Lamp",
                            "rights": "Original MIT illustration",
                            "data_base64": base64.b64encode(
                                (example / "desk-lamp.png").read_bytes()
                            ).decode(),
                        },
                    },
                )
                assert not created.isError
                project = created.structuredContent
                reference = await session.call_tool(
                    "get_decomposition_image", {"project_id": project["id"]}
                )
                assert not reference.isError and reference.content[0].type == "image"
                import json

                result = await session.call_tool(
                    "workspace_request",
                    {
                        "method": "PUT",
                        "path": f"/api/decompositions/{project['id']}/plan",
                        "payload": {
                            "revision": 0,
                            "plan": json.loads((example / "plan.json").read_text()),
                        },
                    },
                )
                assert not result.isError, result.content
                assert result.structuredContent["revision"] == 1
                shown = await session.call_tool("show_decomposition", {"project_id": project["id"]})
                assert not shown.isError and shown.structuredContent["kind"] == "decomposition"
                downloaded = await session.call_tool(
                    "workspace_request",
                    {
                        "method": "GET",
                        "path": f"/api/decompositions/{project['id']}/revisions/1/bundle",
                    },
                )
                assert not downloaded.isError, downloaded.content
                payload = downloaded.structuredContent
                assert payload["mime_type"] == "application/zip"
                bundle = tmp_path / "mcp-export.zip"
                bundle.write_bytes(base64.b64decode(payload["data_base64"], validate=True))
                from open_assembly.decomposition import replay_bundle

                assert replay_bundle(bundle, tmp_path / "mcp-replay")["outcome"] == "pass"
                resource = await session.read_resource("ui://open-assembly/decomposition-v1.html")
                assert 'data-viewer="decomposition"' in resource.contents[0].text

    asyncio.run(exercise())
