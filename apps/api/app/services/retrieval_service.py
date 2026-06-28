from __future__ import annotations


def search_seed_resources(topic: str) -> list[dict[str, str]]:
    return [{"topic": topic, "title": f"{topic}基础资源", "source": "seed"}]
