from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from my_agent.web.db import get_session
from my_agent.web.service import WebAppService


STATIC_DIR = Path(__file__).resolve().parent / "static"
DEV_FRONTEND_ORIGINS = [
    "http://127.0.0.1:3003",
    "http://localhost:3003",
]


def create_app(service: WebAppService, static_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="my-agent-web", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=DEV_FRONTEND_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    register_api_routes(app, service)
    app.mount(
        "/",
        StaticFiles(directory=str(static_dir or STATIC_DIR), html=True),
        name="static",
    )
    return app


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):  # noqa: ARG001
        detail = exc.detail if isinstance(exc.detail, str) else "request failed"
        return JSONResponse(status_code=exc.status_code, content={"error": detail})


def register_api_routes(app: FastAPI, service: WebAppService) -> None:
    @app.get("/api/config")
    async def get_config():
        return service.get_config(masked=True)

    @app.post("/api/config")
    async def update_config(payload: dict[str, Any] = Body(default_factory=dict)):
        return service.update_config(payload)

    @app.post("/api/providers/test")
    async def test_provider(payload: dict[str, Any] = Body(default_factory=dict)):
        try:
            return service.test_provider_connection(
                provider_id=str(payload.get("provider_id") or ""),
                model=str(payload.get("model")) if payload.get("model") else None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/personas")
    async def list_personas():
        return service.list_personas()

    @app.post("/api/personas", status_code=201)
    async def clone_persona(payload: dict[str, Any] = Body(default_factory=dict)):
        try:
            return service.clone_persona(
                source_persona_id=str(payload.get("source_persona_id") or ""),
                display_name=payload.get("display_name"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.patch("/api/personas/{persona_id}")
    async def update_persona(
        persona_id: str,
        payload: dict[str, Any] = Body(default_factory=dict),
    ):
        try:
            return service.update_persona(persona_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/api/personas/{persona_id}")
    async def archive_persona(persona_id: str):
        try:
            return service.archive_persona(persona_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/personas/model")
    async def assign_persona_model(payload: dict[str, Any] = Body(default_factory=dict)):
        return service.assign_persona_model(
            persona_ids=[str(item) for item in payload.get("persona_ids") or []],
            provider_id=payload.get("provider_id"),
            model=payload.get("model"),
        )

    @app.post("/api/topic/refine")
    async def refine_topic(payload: dict[str, Any] = Body(default_factory=dict)):
        return service.refine_topic(
            str(payload.get("raw_input") or ""),
            title=payload.get("title"),
            previous_topic=payload.get("previous_topic"),
            clarification_answers=as_string_list(payload.get("clarification_answers")),
        )

    @app.get("/api/sessions")
    async def list_sessions(q: str | None = None):
        query = q.strip() if q else None
        return service.list_sessions(query=query or None)

    @app.post("/api/sessions", status_code=201)
    async def create_session(payload: dict[str, Any] = Body(default_factory=dict)):
        try:
            return service.create_session(
                raw_input=str(payload.get("raw_input") or ""),
                topic=payload.get("topic") or {},
                persona_ids=[str(item) for item in payload.get("persona_ids") or []],
                style=str(payload.get("style") or "analysis"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/sessions/{session_id}")
    async def read_session(session_id: str):
        with service.connection() as conn:
            session = get_session(conn, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="session not found")
        return session

    @app.post("/api/sessions/{session_id}/personas")
    async def add_session_personas(
        session_id: str,
        payload: dict[str, Any] = Body(default_factory=dict),
    ):
        try:
            return service.add_session_personas(
                session_id=session_id,
                persona_ids=[str(item) for item in payload.get("persona_ids") or []],
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/sessions/{session_id}/messages", status_code=201)
    async def continue_session(
        session_id: str,
        payload: dict[str, Any] = Body(default_factory=dict),
    ):
        try:
            return service.continue_session(
                session_id=session_id,
                user_message=str(payload.get("content") or ""),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/sessions/{session_id}/stream")
    async def stream_session(
        session_id: str,
        payload: dict[str, Any] = Body(default_factory=dict),
    ):
        with service.connection() as conn:
            if not get_session(conn, session_id):
                raise HTTPException(status_code=404, detail="session not found")
        return StreamingResponse(
            (
                encode_sse_event(event)
                for event in service.continue_session_events(
                    session_id=session_id,
                    user_message=str(payload.get("content") or ""),
                )
            ),
            media_type="text/event-stream",
        )


def as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def encode_sse_event(event: dict[str, Any]) -> str:
    event_type = str(event.get("type") or "message")
    data = json.dumps(event, ensure_ascii=False)
    return f"event: {event_type}\ndata: {data}\n\n"


def run_server(
    host: str = "127.0.0.1",
    port: int = 3004,
    config_path: Path | None = None,
    db_path: Path | None = None,
) -> None:
    service = WebAppService(config_path=config_path, db_path=db_path)
    service.bootstrap()
    app = create_app(service=service)
    print(f"my_agent web API running at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
