"""Seed the C++ 算法学习 course into MySQL + Neo4j for the MCP demo stack.

Usage (repo root .env must provide DATABASE_URL / NEO4J_*):
    cd apps/mcp
    uv run python scripts/seed_cpp_course.py --dry-run   # 校验语料与图谱结构对齐
    uv run python scripts/seed_cpp_course.py --username zhixing-demo

Parsing rules: each `## x.y <标题>` heading in the corpus files becomes one
KnowledgeChunk; headings are matched to the section names in cpp_algorithms.json
so that graph nodes carry source_chunk_ids back to the MySQL ground truth.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from mcp_servers._bootstrap import ensure_api_importable  # noqa: E402

ensure_api_importable()


SEED_DIR = Path(__file__).resolve().parents[3] / "data" / "seed" / "cpp_algorithms"
DEFAULT_USERNAME = "zhixing-demo"


def parse_corpus(file_path: Path) -> dict[str, str]:
    """Return {section_name: section_body} parsed from a chapter markdown."""
    lines = file_path.read_text(encoding="utf-8").splitlines()
    sections: dict[str, str] = {}
    current: str | None = None
    body: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(body).strip()
            heading = line[3:].strip()
            # heading 形如 "1.1 什么是算法"，去掉编号前缀后与 JSON 的 name 对齐
            name = heading.split(" ", 1)[1].strip() if " " in heading else heading
            current = name
            body = []
        elif current is not None:
            body.append(line)
    if current is not None:
        sections[current] = "\n".join(body).strip()
    return sections


def collect_sections(spec: dict) -> tuple[list[dict], dict[str, str]]:
    """Load all sections and their corpus text; raise on mismatch."""
    chapters = spec["chapters"]
    corpus_text: dict[str, str] = {}
    for chapter in chapters:
        file_path = SEED_DIR / chapter["file"]
        parsed = parse_corpus(file_path)
        for section in chapter["sections"]:
            if section["name"] not in parsed:
                raise SystemExit(
                    f"corpus mismatch: '{section['name']}' not found in {file_path.name}; "
                    f"headings: {sorted(parsed)}"
                )
            corpus_text[section["id"]] = parsed[section["name"]]
    flat: list[dict] = []
    for chapter in chapters:
        for section in chapter["sections"]:
            flat.append(
                {
                    **section,
                    "chapter_id": chapter["id"],
                    "chapter_name": chapter["name"],
                    "chapter_order": chapter["file"].split("-")[1],
                }
            )
    return flat, corpus_text


def build_graph(spec: dict, sections: list[dict], chunk_ids: dict[str, int]) -> tuple[list[dict], list[dict]]:
    root_id = spec["root_id"]
    nodes: list[dict] = [
        {
            "id": root_id,
            "name": spec["course"],
            "node_type": "concept",
            "difficulty": "basic",
            "summary": spec.get("description", ""),
            "source_chunk_ids": [],
            "confidence": 1.0,
            "level": 0,
            "order": 0,
            "parent_id": "",
        }
    ]
    edges: list[dict] = []
    for index, chapter in enumerate(spec["chapters"], start=1):
        nodes.append(
            {
                "id": chapter["id"],
                "name": chapter["name"],
                "node_type": "concept",
                "difficulty": "basic",
                "summary": "",
                "source_chunk_ids": [],
                "confidence": 1.0,
                "level": 1,
                "order": index,
                "parent_id": root_id,
            }
        )
        edges.append(
            {
                "id": f"{root_id}->{chapter['id']}",
                "source_node_id": root_id,
                "target_node_id": chapter["id"],
                "relation_type": "contains",
                "reason": "课程章节结构",
                "confidence": 1.0,
            }
        )
        for order, section in enumerate(chapter["sections"], start=1):
            nodes.append(
                {
                    "id": section["id"],
                    "name": section["name"],
                    "node_type": section["node_type"],
                    "difficulty": section["difficulty"],
                    "summary": "",
                    "source_chunk_ids": [chunk_ids[section["id"]]],
                    "confidence": 1.0,
                    "level": 2,
                    "order": order,
                    "parent_id": chapter["id"],
                }
            )
            edges.append(
                {
                    "id": f"{chapter['id']}->{section['id']}",
                    "source_node_id": chapter["id"],
                    "target_node_id": section["id"],
                    "relation_type": "contains",
                    "reason": "章节小节结构",
                    "confidence": 1.0,
                }
            )
    for section in sections:
        for prereq in section.get("prerequisites", []):
            if not prereq:
                continue
            edges.append(
                {
                    "id": f"{prereq}->{section['id']}",
                    "source_node_id": prereq,
                    "target_node_id": section["id"],
                    "relation_type": "prerequisite",
                    "reason": "学习前置依赖",
                    "confidence": 0.95,
                }
            )
    return nodes, edges


def seed(username: str, dry_run: bool) -> None:
    spec = json.loads((SEED_DIR / "cpp_algorithms.json").read_text(encoding="utf-8"))
    sections, corpus_text = collect_sections(spec)
    print(f"[ok] corpus aligned: {len(sections)} sections across {len(spec['chapters'])} chapters")
    for section in sections:
        length = len(corpus_text[section["id"]])
        if length < 200:
            raise SystemExit(f"corpus too short for '{section['name']}': {length} chars")

    if dry_run:
        print("[dry-run] database writes skipped")
        return

    from sqlalchemy import select

    from app.models.course import Course, CourseMaterial, KnowledgeChunk
    from app.models.user import User
    from app.db import SessionLocal
    from app.services.graph_store import Neo4jGraphStore

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(
                username=username,
                email=f"{username}@zhixing.local",
                password_hash="not-used-for-demo",
            )
            db.add(user)
            db.flush()
            print(f"[ok] created user {username} (id={user.id})")

        course = db.scalar(
            select(Course).where(Course.user_id == user.id, Course.name == spec["course"])
        )
        if course is None:
            course = Course(
                user_id=user.id,
                name=spec["course"],
                major=spec.get("major", ""),
                level=spec.get("level", ""),
                description=spec.get("description", ""),
                status="ready",
            )
            db.add(course)
            db.flush()
            print(f"[ok] created course {spec['course']} (id={course.id})")

        existing_chunks = db.scalars(
            select(KnowledgeChunk).where(KnowledgeChunk.course_id == course.id)
        ).all()
        if existing_chunks:
            print(f"[skip] course already has {len(existing_chunks)} chunks; delete course first to re-seed")
            return

        material = CourseMaterial(
            course_id=course.id,
            user_id=user.id,
            filename="C++算法学习教材（内置语料）.md",
            file_type="md",
            storage_path=str(SEED_DIR / "corpus"),
            size_bytes=sum(len(text.encode("utf-8")) for text in corpus_text.values()),
            parse_status="parsed",
        )
        db.add(material)
        db.flush()

        chunk_ids: dict[str, int] = {}
        for index, section in enumerate(sections):
            chunk = KnowledgeChunk(
                course_id=course.id,
                material_id=material.id,
                chunk_index=index,
                source_locator=f"{section['chapter_name']}#{section['name']}",
                heading=section["name"],
                content=corpus_text[section["id"]],
                token_count=len(corpus_text[section["id"]]),
                embedding_id="",
            )
            db.add(chunk)
            db.flush()
            chunk_ids[section["id"]] = chunk.id
        db.commit()
        print(f"[ok] inserted {len(chunk_ids)} knowledge chunks")

    nodes, edges = build_graph(spec, sections, chunk_ids)
    store = Neo4jGraphStore()
    try:
        store.replace_course_graph(user.id, course.id, nodes, edges)
        print(f"[ok] Neo4j graph replaced: {len(nodes)} nodes / {len(edges)} edges")
    finally:
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    seed(args.username, args.dry_run)
