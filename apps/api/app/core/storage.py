from __future__ import annotations

import re
from pathlib import Path


ALLOWED_EXTENSIONS = {"pdf", "ppt", "pptx"}
WINDOWS_RESERVED_BASENAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def allowed_file_type(filename: str) -> str | None:
    extension = Path(filename).suffix.lower().lstrip(".")
    if extension in ALLOWED_EXTENSIONS:
        return extension
    return None


def safe_upload_name(filename: str) -> str:
    name = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    stem = Path(name).stem
    suffix = Path(name).suffix.lower()
    safe_stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", stem).strip(" .")
    if safe_stem.upper() in WINDOWS_RESERVED_BASENAMES:
        safe_stem = f"upload_{safe_stem}"
    return f"{safe_stem or 'upload'}{suffix}"


def course_upload_dir(root: str | Path, user_id: int | str, course_id: int | str) -> Path:
    user_segment = _positive_int_segment(user_id, "user_id")
    course_segment = _positive_int_segment(course_id, "course_id")
    resolved_root = Path(root).resolve(strict=False)
    path = (resolved_root / user_segment / course_segment).resolve(strict=False)
    try:
        path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("Upload path must stay under upload root") from exc
    path.mkdir(parents=True, exist_ok=True)
    return path


def _positive_int_segment(value: int | str, field_name: str) -> str:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    if isinstance(value, int):
        if value <= 0:
            raise ValueError(f"{field_name} must be a positive integer")
        return str(value)
    if isinstance(value, str) and value.isdecimal():
        if int(value) <= 0:
            raise ValueError(f"{field_name} must be a positive integer")
        return value
    raise ValueError(f"{field_name} must be a positive integer")
