from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy.orm import sessionmaker

from app.db import SessionLocal, get_db, init_db
from app.routers import agentarts_proxy, assessments, auth, chat, coderun, courses, edge_tts, kb_evaluations, paths, profiles, memory_debug, resources, tts, tutor, voice_ws, wrong_question_tutor
from app.services.material_task_queue import MaterialTaskQueue


def create_app(session_factory: sessionmaker | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if session_factory is None:
            init_db()
        yield

    app = FastAPI(title="Personalized Learning Agents", lifespan=lifespan)
    app.state.material_task_queue = MaterialTaskQueue(session_factory or SessionLocal)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if session_factory is not None:
        def override_get_db():
            db = session_factory()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db

    app.include_router(auth.router)
    app.include_router(agentarts_proxy.router)
    app.include_router(chat.router)
    app.include_router(profiles.router)
    app.include_router(resources.router)
    app.include_router(courses.router)
    app.include_router(kb_evaluations.router)
    app.include_router(paths.router)
    app.include_router(assessments.router)
    app.include_router(tts.router)
    app.include_router(edge_tts.router)
    app.include_router(tutor.router)
    app.include_router(wrong_question_tutor.router)
    app.include_router(coderun.router)
    app.include_router(voice_ws.router)
    app.include_router(memory_debug.router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
