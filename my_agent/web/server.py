from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from my_agent.web.service import WebAppService


STATIC_DIR = Path(__file__).resolve().parent / "static"


def make_handler(service: WebAppService, static_dir: Path | None = None):
    root = static_dir or STATIC_DIR

    class WebHandler(BaseHTTPRequestHandler):
        server_version = "my-agent-web/0.1"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/config":
                    self.write_json(service.get_config(masked=True))
                    return
                if parsed.path == "/api/personas":
                    self.write_json(service.list_personas())
                    return
                if parsed.path == "/api/sessions":
                    query = parse_qs(parsed.query).get("q", [""])[0].strip()
                    self.write_json(service.list_sessions(query=query or None))
                    return
                if parsed.path.startswith("/api/sessions/"):
                    session_id = parsed.path.removeprefix("/api/sessions/").strip("/")
                    with service.connection() as conn:
                        from my_agent.web.db import get_session

                        session = get_session(conn, session_id)
                    if not session:
                        self.write_error(HTTPStatus.NOT_FOUND, "session not found")
                        return
                    self.write_json(session)
                    return
                self.serve_static(parsed.path, root)
            except Exception as exc:
                self.write_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                payload = self.read_json()
                if parsed.path == "/api/config":
                    self.write_json(service.update_config(payload))
                    return
                if parsed.path == "/api/topic/refine":
                    self.write_json(
                        service.refine_topic(
                            str(payload.get("raw_input") or ""),
                            title=payload.get("title"),
                        )
                    )
                    return
                if parsed.path == "/api/sessions":
                    session = service.create_session(
                        raw_input=str(payload.get("raw_input") or ""),
                        topic=payload.get("topic") or {},
                        persona_ids=[str(item) for item in payload.get("persona_ids") or []],
                        style=str(payload.get("style") or "analysis"),
                    )
                    self.write_json(session, status=HTTPStatus.CREATED)
                    return
                if parsed.path == "/api/personas":
                    persona = service.clone_persona(
                        source_persona_id=str(payload.get("source_persona_id") or ""),
                        display_name=payload.get("display_name"),
                    )
                    self.write_json(persona, status=HTTPStatus.CREATED)
                    return
                if parsed.path == "/api/personas/model":
                    result = service.assign_persona_model(
                        persona_ids=[str(item) for item in payload.get("persona_ids") or []],
                        provider_id=payload.get("provider_id"),
                        model=payload.get("model"),
                    )
                    self.write_json(result)
                    return
                if parsed.path.startswith("/api/sessions/") and parsed.path.endswith("/messages"):
                    session_id = parsed.path.split("/")[3]
                    updated = service.continue_session(
                        session_id=session_id,
                        user_message=str(payload.get("content") or ""),
                    )
                    self.write_json(updated, status=HTTPStatus.CREATED)
                    return
                self.write_error(HTTPStatus.NOT_FOUND, "endpoint not found")
            except ValueError as exc:
                self.write_error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception as exc:
                self.write_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

        def do_PATCH(self) -> None:
            parsed = urlparse(self.path)
            try:
                payload = self.read_json()
                if parsed.path.startswith("/api/personas/"):
                    persona_id = parsed.path.removeprefix("/api/personas/").strip("/")
                    self.write_json(service.update_persona(persona_id, payload))
                    return
                self.write_error(HTTPStatus.NOT_FOUND, "endpoint not found")
            except ValueError as exc:
                self.write_error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception as exc:
                self.write_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

        def do_DELETE(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path.startswith("/api/personas/"):
                    persona_id = parsed.path.removeprefix("/api/personas/").strip("/")
                    self.write_json(service.archive_persona(persona_id))
                    return
                self.write_error(HTTPStatus.NOT_FOUND, "endpoint not found")
            except ValueError as exc:
                self.write_error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception as exc:
                self.write_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

        def read_json(self) -> dict:
            length = int(self.headers.get("Content-Length") or "0")
            if not length:
                return {}
            body = self.rfile.read(length).decode("utf-8")
            if not body.strip():
                return {}
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError("JSON payload must be an object")
            return data

        def write_json(self, payload, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def write_error(self, status: HTTPStatus, message: str) -> None:
            self.write_json({"error": message}, status=status)

        def serve_static(self, request_path: str, static_root: Path) -> None:
            relative = request_path.strip("/") or "index.html"
            if ".." in Path(relative).parts:
                self.write_error(HTTPStatus.BAD_REQUEST, "invalid path")
                return
            path = static_root / relative
            if path.is_dir():
                path = path / "index.html"
            if not path.exists() or not path.is_file():
                self.write_error(HTTPStatus.NOT_FOUND, "not found")
                return
            body = path.read_bytes()
            content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

    return WebHandler


def run_server(
    host: str = "127.0.0.1",
    port: int = 3004,
    config_path: Path | None = None,
    db_path: Path | None = None,
) -> None:
    service = WebAppService(config_path=config_path, db_path=db_path)
    service.bootstrap()
    server = ThreadingHTTPServer((host, port), make_handler(service=service))
    print(f"my_agent web API running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        server.server_close()
