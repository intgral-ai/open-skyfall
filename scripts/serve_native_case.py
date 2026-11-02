"""Serve a verified offline native build with the repository's existing STEP UI.

This read-only adapter deliberately does not register an external model in the
main service's bounded wiring-cover executor or expose code execution routes.
"""

import argparse
import hashlib
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_case(directory):
    directory = Path(directory).resolve()
    case = json.loads((directory / "case.json").read_text())
    step_hash = digest(directory / "assembly.step")
    for name in ["native-report.json", "inspection.json"]:
        report = json.loads((directory / name).read_text())
        if (
            report.get("valid") is not True
            or not report.get("checks")
            or not all(report["checks"].values())
        ):
            raise ValueError(f"Case has not passed {name}")
        if report.get("step_sha256") != step_hash:
            raise ValueError(f"Stale STEP binding in {name}")
        if name == "native-report.json":
            bindings = report.get("artifact_hashes")
            if not bindings:
                raise ValueError("Native execution has no bound artifact set")
            for artifact, expected in bindings.items():
                path = (directory / artifact).resolve()
                if (
                    not path.is_relative_to(directory)
                    or not path.is_file()
                    or digest(path) != expected
                ):
                    raise ValueError(f"Native artifact binding changed: {artifact}")
    artifacts = {}
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise ValueError("Symlink artifacts are not supported")
        if path.is_file():
            artifacts[path.relative_to(directory).as_posix()] = {
                "sha256": digest(path),
                "bytes": path.stat().st_size,
            }
    return {**case, "state": "ready", "artifacts": artifacts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument(
        "--ui", type=Path, default=Path(__file__).resolve().parents[1] / "web" / "dist"
    )
    parser.add_argument("--port", type=int, default=8774)
    args = parser.parse_args()
    directory = args.case.resolve()
    ui = args.ui.resolve()
    if not (ui / "index.html").is_file():
        parser.error("Build the repository UI first: npm --prefix web run build")
    case = load_case(directory)
    prefix = f"/api/jobs/{case['id']}"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            if path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if path == "/health":
                return self.json({"service": "open-assembly-native-case", "case": case["id"]})
            if path == "/api/jobs":
                return self.json([case])
            if path == prefix:
                return self.json(case)
            if path.startswith(prefix + "/artifacts/"):
                name = path[len(prefix + "/artifacts/") :]
                metadata = case["artifacts"].get(name)
                target = (directory / name).resolve()
                if metadata is None or not target.is_relative_to(directory) or not target.is_file():
                    return self.send_error(404)
                # Read once: the hash applies to precisely the bytes sent.
                data = target.read_bytes()
                if (
                    hashlib.sha256(data).hexdigest() != metadata["sha256"]
                    or len(data) != metadata["bytes"]
                ):
                    return self.send_error(
                        409, "Artifact changed; restart the verified case server"
                    )
                attachment = name.endswith((".step", ".zip", ".smb", ".pdf"))
                return self.bytes(
                    data,
                    mimetypes.guess_type(name)[0] or "application/octet-stream",
                    Path(name).name if attachment else None,
                )
            if path.startswith("/api/"):
                return self.send_error(404)
            target = (ui / ("index.html" if path == "/" else path.lstrip("/"))).resolve()
            if not target.is_relative_to(ui) or not target.is_file():
                return self.send_error(404)
            self.bytes(
                target.read_bytes(),
                mimetypes.guess_type(target.name)[0] or "application/octet-stream",
            )

        def bytes(self, data, content_type, filename=None):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(data)

        def json(self, data):
            self.bytes(json.dumps(data, allow_nan=False).encode(), "application/json")

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"http://127.0.0.1:{server.server_port}/?job={case['id']}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
