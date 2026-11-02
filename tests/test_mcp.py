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

    asyncio.run(exercise())
