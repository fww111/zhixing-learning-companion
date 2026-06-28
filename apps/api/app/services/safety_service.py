from __future__ import annotations

from app.core.security import is_safe_content


def validate_generated_content(content: str) -> None:
    if not is_safe_content(content):
        raise ValueError("generated content failed safety validation")
