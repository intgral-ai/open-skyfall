import argparse
import json
import shutil
from pathlib import Path

from .document import AssemblyDocument


def _store(root):
    from .project import ProjectStore

    return ProjectStore(root)


def _delivery(store, job, output):
    output.mkdir(parents=True, exist_ok=True)
    if job["state"] == "ready":
        for name in job["artifacts"]:
            path = output / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(store.artifact(job["id"], name), path)
        shutil.copy2(store.bundle(job["id"]), output / "project.zip")
    (output / "job.json").write_text(json.dumps(job, indent=2))
    return {
        "id": job["id"],
        "state": job["state"],
        "revision": job["revision"],
        "output": str(output.resolve()),
        "validation": job.get("validation"),
        "error": job.get("error"),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Reconstruct supported mechanical parts as editable CAD and assembly STEP"
    )
    parser.add_argument("--workspace", default="jobs")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ["demo", "run"]:
        p = sub.add_parser(command)
        if command == "run":
            p.add_argument("input", type=Path)
            p.add_argument("--units", choices=["mm", "cm", "in"])
        else:
            p.add_argument("--variant", type=int, default=0)
        p.add_argument("--out", type=Path, default=Path("output"))
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8766)
    mcp = sub.add_parser("mcp")
    mcp.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("input", type=Path)
    inspect.add_argument("--units", choices=["mm", "cm", "in"])
    verify = sub.add_parser("verify")
    verify.add_argument("input", type=Path)
    evaluate = sub.add_parser("eval")
    evaluate.add_argument("--out", type=Path, default=Path("evidence/evaluation"))
    evaluate.add_argument("--count", type=int, default=10)
    edit = sub.add_parser("edit")
    edit.add_argument("job_id")
    edit.add_argument("definition_id")
    edit.add_argument("--revision", type=int, required=True)
    edit.add_argument(
        "--parameters", required=True, help="JSON object of dimensions in millimeters"
    )
    args = parser.parse_args()
    try:
        if args.command == "serve":
            import uvicorn

            from .server import create_app

            uvicorn.run(create_app(_store(args.workspace)), host="127.0.0.1", port=args.port)
            return
        if args.command == "mcp":
            from .mcp import create_mcp

            create_mcp(_store(args.workspace)).run(transport=args.transport)
            return
        if args.command == "inspect":
            from .reconstruction import inspect_stl

            print(inspect_stl(args.input, args.units).model_dump_json(indent=2))
            return
        if args.command == "verify":
            import build123d as cad
            from specify_core import api

            shape = cad.import_step(args.input)
            print(
                json.dumps(
                    {
                        "valid": shape.is_valid,
                        "solid_count": len(shape.solids()),
                        "volume_mm3": shape.volume,
                        "independent_parts": api.parts(args.input),
                    },
                    indent=2,
                )
            )
            if not shape.is_valid:
                raise SystemExit(1)
            return
        if args.command == "eval":
            from .evaluation import evaluate

            print(json.dumps(evaluate(args.out, args.count), indent=2))
            return
        store = _store(args.workspace)
        if args.command == "edit":
            job = store.edit(
                args.job_id, args.revision, args.definition_id, json.loads(args.parameters)
            )
            print(json.dumps(job, indent=2))
            return
        if args.command == "demo":
            from .fixtures import create_demo

            demo = create_demo(args.out / "fixture", args.variant)
            job = store.create(Path(demo["input"]), "mm", "Mechanical demo")
        elif args.input.suffix.lower() == ".json":
            document = AssemblyDocument.model_validate_json(args.input.read_text())
            job = store.create_document(document)
        else:
            job = store.create(args.input, args.units)
        print(json.dumps(_delivery(store, job, args.out), indent=2))
        if job["state"] != "ready":
            raise SystemExit(2)
    except (ValueError, FileNotFoundError) as exc:
        parser.exit(2, f"open-assembly: {exc}\n")
