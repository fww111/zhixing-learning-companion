from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import logging
from typing import Callable

from sqlalchemy.orm import Session


SessionFactory = Callable[[], Session]
logger = logging.getLogger(__name__)


class MaterialTaskQueue:
    def __init__(self, session_factory: SessionFactory, max_workers: int = 1) -> None:
        self.session_factory = session_factory
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="material-worker")

    def enqueue(self, user_id: int, course_id: int, material_id: int, chunk_params: dict | None = None) -> None:
        self.executor.submit(self._process, user_id, course_id, material_id, chunk_params)

    def enqueue_vector_rebuild(self, user_id: int, course_id: int) -> None:
        self.executor.submit(self._rebuild_vector_index, user_id, course_id)

    def _process(self, user_id: int, course_id: int, material_id: int, chunk_params: dict | None = None) -> None:
        from app.services.course_service import CourseService

        db = self.session_factory()
        try:
            CourseService(db).process_material_by_id(user_id, course_id, material_id, chunk_params=chunk_params)
        except Exception:
            logger.exception("material processing task failed", extra={"user_id": user_id, "course_id": course_id, "material_id": material_id})
        finally:
            db.close()

    def _rebuild_vector_index(self, user_id: int, course_id: int) -> None:
        from app.services.course_service import CourseService

        db = self.session_factory()
        try:
            CourseService(db).rebuild_vector_index(user_id, course_id)
        except Exception:
            logger.exception("vector rebuild task failed", extra={"user_id": user_id, "course_id": course_id})
        finally:
            db.close()
