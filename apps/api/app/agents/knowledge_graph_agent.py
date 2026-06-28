from __future__ import annotations

import json
import re
from typing import Any, Iterable

from app.core.config import settings
from app.llm.client import LLMClient


ALLOWED_NODE_TYPES = {"concept", "method", "formula", "tool", "case"}
ALLOWED_DIFFICULTIES = {"basic", "intermediate", "advanced"}
ALLOWED_RELATION_TYPES = {
    "prerequisite",
    "contains",
    "applies_to",
    "common_mistake",
    "case_supports",
}


class KnowledgeGraphAgent:
    def __init__(self, mock: bool | None = None, llm: LLMClient | None = None) -> None:
        self.mock = settings.mock_llm if mock is None else mock
        self.llm = llm or LLMClient(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            mock=self.mock,
        )

    def build_graph(self, chunks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        if not self.mock:
            raise RuntimeError("KnowledgeGraphAgent.build_graph is mock-only in real mode; use build_graph_async instead.")
        return self._build_mock_graph(chunks)

    async def build_graph_async(self, chunks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        outline_graph = self._build_outline_graph(chunks)

        if self.mock or getattr(self.llm, "mock", False):
            return self._build_mock_graph(chunks)

        graph_chunks = self._representative_chunks(chunks)
        chunk_ids = [str(chunk.get("id")) for chunk in graph_chunks if chunk.get("id") is not None]
        try:
            data = await self.llm.complete_json(
                system_prompt=(
                    "You are a course semantic knowledge-graph extraction agent. Return only a JSON object "
                    'with the shape {"nodes": [], "edges": []}. '
                    "Extract the graph from the actual course material chunks, not merely from the table of contents. "
                    "The graph should describe teachable knowledge points and their learning relationships. "
                    "Each node must include id, name, node_type, difficulty, summary, source_chunk_ids, confidence. "
                    "Allowed node_type values: concept, method, formula, tool, case. "
                    "Allowed difficulty values: basic, intermediate, advanced. "
                    "Node confidence must be a number from 0 to 1. "
                    f"Node source_chunk_ids must only use these provided chunk ids: {chunk_ids}. "
                    "Each edge must include id, source_node_id, target_node_id, relation_type, reason, confidence. "
                    "Allowed relation_type values: prerequisite, contains, applies_to, common_mistake, case_supports. "
                    "Edge confidence must be a number from 0 to 1. "
                    "Every edge source_node_id and target_node_id must reference a node id returned in this response. "
                    "Prefer prerequisite, applies_to, common_mistake, and case_supports edges for semantic learning paths; "
                    "use contains only when a larger concept truly groups smaller concepts."
                ),
                user_prompt=json.dumps({"chunks": graph_chunks}, ensure_ascii=False),
            )
        except Exception:
            if outline_graph["nodes"]:
                return outline_graph
            return self._build_mock_graph(graph_chunks)

        graph = self._normalize_graph(data, graph_chunks)
        if not graph["nodes"]:
            if outline_graph["nodes"]:
                return outline_graph
            return self._build_mock_graph(graph_chunks)
        return self._merge_outline_and_semantic_graphs(outline_graph, graph)

    def _build_mock_graph(self, chunks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        outline_graph = self._build_outline_graph(chunks)
        if outline_graph["nodes"]:
            return outline_graph

        candidates = self._representative_chunks(chunks)
        if not candidates:
            candidates = [{"id": "mock-chunk-1", "heading": "Course overview", "content": "Course overview"}]

        nodes = []
        for index, chunk in enumerate(candidates[:6]):
            name = self._clean_text(chunk.get("heading")) or self._first_sentence(chunk.get("content")) or f"Knowledge point {index + 1}"
            node_id = f"concept-{self._slug(name) or index + 1}"
            nodes.append(
                {
                    "id": node_id,
                    "name": name[:40],
                    "node_type": "concept" if index == 0 else "method",
                    "difficulty": "basic" if index < 2 else "intermediate",
                    "summary": self._first_sentence(chunk.get("content")) or f"Key course content about {name}.",
                    "source_chunk_ids": [str(chunk.get("id") or f"mock-chunk-{index + 1}")],
                    "confidence": 0.78,
                    "level": 1,
                    "order": index,
                    "parent_id": "",
                }
            )

        if len(nodes) == 1:
            practice_id = f"{nodes[0]['id']}-practice"
            nodes.append(
                {
                    "id": practice_id,
                    "name": f"{nodes[0]['name']} 学习实践"[:40],
                    "node_type": "case",
                    "difficulty": "intermediate",
                    "summary": f"Use examples and exercises to consolidate {nodes[0]['name']}.",
                    "source_chunk_ids": nodes[0]["source_chunk_ids"],
                    "confidence": 0.7,
                    "level": 2,
                    "order": 1,
                    "parent_id": nodes[0]["id"],
                }
            )

        edges = []
        for index in range(len(nodes) - 1):
            edges.append(
                {
                    "id": f"edge-{nodes[index]['id']}-{nodes[index + 1]['id']}",
                    "source_node_id": nodes[index]["id"],
                    "target_node_id": nodes[index + 1]["id"],
                    "relation_type": "contains" if index == 0 else "prerequisite",
                    "reason": "Adjacent course concepts appear in the parsed course material sequence.",
                    "confidence": 0.72,
                }
            )
        return {"nodes": nodes, "edges": edges}

    def _build_outline_graph(self, chunks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        items = self._extract_outline_items(chunks)
        if len(items) < 3:
            return {"nodes": [], "edges": []}

        root_id = "course-root"
        course_name = self._course_name(chunks)
        nodes = [
            {
                "id": root_id,
                "name": course_name,
                "node_type": "concept",
                "difficulty": "basic",
                "summary": f"{course_name} 的课程知识结构总览。",
                "source_chunk_ids": self._first_chunk_ids(chunks),
                "confidence": 0.92,
                "level": 0,
                "order": 0,
                "parent_id": "",
            }
        ]

        sorted_items = sorted(items.values(), key=lambda item: item["sort_key"])
        key_to_id = {"course": root_id}
        for index, item in enumerate(sorted_items, start=1):
            node_id = f"outline-{self._slug(item['key']) or index}"
            key_to_id[item["key"]] = node_id
            nodes.append(
                {
                    "id": node_id,
                    "name": item["name"][:80],
                    "node_type": self._outline_node_type(item["name"]),
                    "difficulty": "basic" if item["level"] <= 2 else "intermediate",
                    "summary": item["summary"][:220],
                    "source_chunk_ids": item["source_chunk_ids"],
                    "confidence": 0.88,
                    "level": item["level"],
                    "order": index,
                    "parent_id": "",
                }
            )

        node_by_key = {item["key"]: nodes[index + 1] for index, item in enumerate(sorted_items)}
        edges = []
        children_by_parent: dict[str, list[dict[str, Any]]] = {}
        for item in sorted_items:
            parent_key = self._nearest_existing_parent_key(item, key_to_id)
            parent_id = key_to_id.get(parent_key, root_id)
            node = node_by_key[item["key"]]
            node["parent_id"] = parent_id
            children_by_parent.setdefault(parent_id, []).append(node)
            edges.append(
                {
                    "id": f"contains-{parent_id}-{node['id']}",
                    "source_node_id": parent_id,
                    "target_node_id": node["id"],
                    "relation_type": "contains",
                    "reason": "根据教材目录层级建立包含关系。",
                    "confidence": 0.9,
                }
            )

        for siblings in children_by_parent.values():
            ordered = sorted(siblings, key=lambda node: int(node.get("order", 0)))
            for previous, current in zip(ordered, ordered[1:]):
                edges.append(
                    {
                        "id": f"prerequisite-{previous['id']}-{current['id']}",
                        "source_node_id": previous["id"],
                        "target_node_id": current["id"],
                        "relation_type": "prerequisite",
                        "reason": "教材目录顺序显示前一知识点通常应先学习。",
                        "confidence": 0.72,
                    }
                )

        return {"nodes": nodes, "edges": edges}

    def _extract_outline_items(self, chunks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        items: dict[str, dict[str, Any]] = {}
        toc_cutoff = self._first_actual_chapter_index(chunks)
        for position, chunk in enumerate(chunks):
            heading = self._clean_text(chunk.get("heading"))
            content = self._clean_text(chunk.get("content"))
            if heading in {"内容简介", "出版说明", "前言"}:
                continue

            in_toc_area = heading == "目录" or (toc_cutoff is not None and position < toc_cutoff and self._looks_like_toc_text(content))
            raw_items = self._toc_raw_items(f"{heading} {content}") if in_toc_area else self._body_heading_items(heading, content)
            for raw_item in raw_items:
                item = self._parse_outline_item(raw_item)
                if item is None:
                    continue
                chunk_id = str(chunk.get("id")) if chunk.get("id") is not None else ""
                existing = items.get(item["key"])
                if existing is None:
                    item["source_chunk_ids"] = [chunk_id] if chunk_id else []
                    item["summary"] = self._summary_for_outline_item(item["name"], chunk)
                    items[item["key"]] = item
                    continue
                if self._prefer_outline_name(item["name"], existing["name"]):
                    existing["name"] = item["name"]
                    existing["summary"] = self._summary_for_outline_item(item["name"], chunk)
                if chunk_id and chunk_id not in existing["source_chunk_ids"]:
                    existing["source_chunk_ids"].append(chunk_id)
        return items

    def _first_actual_chapter_index(self, chunks: list[dict[str, Any]]) -> int | None:
        for index, chunk in enumerate(chunks):
            content = self._normalize_outline_text(self._clean_text(chunk.get("content")))
            if re.match(r"第\s*1\s*章\s+\S+", content) and "目录" not in content[:30]:
                return index
        return None

    def _looks_like_toc_text(self, text: str) -> bool:
        normalized = self._normalize_outline_text(text)
        return "目录" in normalized[:20] or len(re.findall(r"第\s*\d+\s*章|\b\d{1,2}\.\d{1,2}\b", normalized)) >= 3

    def _toc_raw_items(self, text: str) -> Iterable[str]:
        normalized = self._normalize_outline_text(text)
        matches = list(re.finditer(r"第\s*\d+\s*章|\b\d{1,2}(?:\.\d{1,2}){1,3}\b", normalized))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else min(len(normalized), match.start() + 180)
            yield normalized[match.start() : end]

    def _body_heading_items(self, heading: str, content: str) -> Iterable[str]:
        heading_text = self._normalize_outline_text(heading)
        content_text = self._normalize_outline_text(content)
        for candidate in [heading_text, content_text[:120]]:
            if re.match(r"^第\s*\d+\s*章\s*\S+", candidate) or re.match(r"^\d{1,2}(?:\.\d{1,2}){1,3}\s+\S+", candidate):
                yield candidate
        for candidate in self._inline_body_section_items(content_text):
            yield candidate

    def _inline_body_section_items(self, text: str) -> Iterable[str]:
        matches = list(
            re.finditer(r"(?<![A-Za-z0-9\u4e00-\u9fff.])(\d{1,2}(?:\.\d{1,2}){1,3})\s*(?=[A-Za-z\u4e00-\u9fff])\S*", text)
        )
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else min(len(text), match.start() + 120)
            candidate = self._trim_inline_body_section_item(text[match.start() : end])
            if self._looks_like_exercise_choice(candidate):
                continue
            follows_sequence = self._follows_outline_sequence(matches, index, text)
            if self._looks_like_non_outline_number(text, match) and not follows_sequence:
                continue
            if (
                not self._is_inline_section_boundary(text, match.start())
                and not follows_sequence
                and not self._looks_like_standalone_inline_section(candidate)
            ):
                continue
            yield candidate

    def _follows_outline_sequence(self, matches: list[re.Match[str]], index: int, text: str) -> bool:
        if index <= 0:
            return False
        previous = matches[index - 1]
        current = matches[index]
        previous_number = previous.group(1)
        current_number = current.group(1)
        if not self._outline_number_progresses(previous_number, current_number):
            return False

        between = text[previous.end() : current.start()].strip()
        if len(between) > 120:
            return False
        if self._looks_like_exercise_choice(between):
            return False
        return True

    def _outline_number_progresses(self, previous_number: str, current_number: str) -> bool:
        previous = self._outline_number_parts(previous_number)
        current = self._outline_number_parts(current_number)
        if len(previous) < 2 or len(current) < 2:
            return False

        if len(current) == len(previous) + 1 and current[:-1] == previous and current[-1] == 1:
            return True
        if len(current) == len(previous) and current[:-1] == previous[:-1] and current[-1] == previous[-1] + 1:
            return True
        if len(current) < len(previous):
            ancestor_depth = len(current) - 1
            return (
                current[:-1] == previous[:ancestor_depth]
                and ancestor_depth < len(previous)
                and current[-1] == previous[ancestor_depth] + 1
            )
        return False

    def _outline_number_parts(self, number: str) -> list[int]:
        try:
            return [int(part) for part in number.split(".")]
        except ValueError:
            return []

    def _is_inline_section_boundary(self, text: str, start: int) -> bool:
        prefix = text[:start].rstrip()
        if not prefix:
            return True
        if prefix[-1] in "。；;！？!?":
            return True
        if re.search(r"(?:程序分析|注意|例如|如|说明)：\s*$", prefix):
            return True
        return bool(re.search(r"第\s*\d+\s*章\s*\S{0,40}$", prefix))

    def _looks_like_non_outline_number(self, text: str, match: re.Match[str]) -> bool:
        prefix = text[: match.start()].rstrip()
        if re.search(r"(?:图|表|例)\s*$", prefix):
            return True
        if re.search(r"(?:Python|Visual\s+C\+\+|Turbo\s+C\+\+|GCC|Windows)\s*$", prefix):
            return True
        suffix = text[match.end() : match.end() + 20]
        if re.match(r"\s*(?:中|所示|可以看到|表示|为|是)", suffix):
            return True
        return False

    def _looks_like_standalone_inline_section(self, candidate: str) -> bool:
        item = self._parse_outline_item(candidate)
        return bool(item and int(item.get("level", 0)) >= 3)

    def _looks_like_exercise_choice(self, text: str) -> bool:
        return bool(re.search(r"\bA\s*[.．、]\s*", text) and re.search(r"\bB\s*[.．、]\s*", text))

    def _trim_inline_body_section_item(self, text: str) -> str:
        section_match = re.match(r"(\d{1,2}(?:\.\d{1,2}){1,3})\s+(.+)", text)
        if section_match is None:
            return text

        number = section_match.group(1)
        title = section_match.group(2).strip()
        title = re.split(r"[。；;：:]", title, maxsplit=1)[0]
        title = re.split(r"\s+[\(（]\d+[\)）]", title, maxsplit=1)[0]
        body_starter_pattern = (
            r"\s+(?:"
            r"有人|所谓|人和|为了|下面|以上|现在|从|如果|一般|本章|本节|"
            r"计算机|程序|要|可以|使用|例如|图\s*\d|表\s*\d|"
            r"解题思路|编写程序|运行结果|程序分析|注意|首先|双击|常用|具体规则|这些规则|"
            r"用|在|前面|若|由于|其中|有时|一个|随机读写|自增|自减|最常用|C\s*语言提供|"
            r"Python\s+在不同|Python\s+的安装过程如下|在不同|在给变量|由\s+Guido|目前主要|过程如下|"
            r"在\s+Python|Python\s+语言(?:是|由|目前|本身|具有|凭借|提供|开发|的特点总结)|"
            r"Python\s+开发环境|Python\s+提供"
            r")"
        )
        title = re.split(body_starter_pattern, title, maxsplit=1)[0]
        return f"{number} {title.strip()}"

    def _parse_outline_item(self, raw_item: str) -> dict[str, Any] | None:
        item = self._normalize_outline_text(raw_item)
        chapter_match = re.match(r"第\s*(\d+)\s*章\s*(.+)", item)
        if chapter_match:
            chapter = int(chapter_match.group(1))
            title = self._clean_outline_title(chapter_match.group(2))
            if not self._valid_outline_title(title):
                return None
            return {
                "key": f"chapter-{chapter}",
                "number": str(chapter),
                "name": f"第 {chapter} 章 {title}",
                "level": 1,
                "sort_key": (chapter, 0, 0, 0),
            }

        section_match = re.match(r"(\d{1,2}(?:\.\d{1,2}){1,3})\s*(.+)", item)
        if section_match:
            number = section_match.group(1)
            if self._looks_like_version_or_decimal(number):
                return None
            title = self._clean_outline_title(section_match.group(2))
            if not self._valid_outline_title(title):
                return None
            parts = tuple(int(part) for part in number.split("."))
            padded_sort_key = parts + (0,) * (4 - len(parts))
            return {
                "key": f"section-{number}",
                "number": number,
                "name": f"{number} {title}",
                "level": len(parts),
                "sort_key": padded_sort_key,
            }
        return None

    def _looks_like_version_or_decimal(self, number: str) -> bool:
        parts = [int(part) for part in number.split(".")]
        return len(parts) >= 3 and (parts[1] > 20 or parts[-1] > 9)

    def _nearest_existing_parent_key(self, item: dict[str, Any], key_to_id: dict[str, str]) -> str:
        number = str(item.get("number", ""))
        if item.get("level") == 1 or "." not in number:
            return "course"

        parent_number = number.rsplit(".", 1)[0]
        while parent_number:
            parent_key = f"section-{parent_number}" if "." in parent_number else f"chapter-{parent_number}"
            if parent_key in key_to_id:
                return parent_key
            if "." not in parent_number:
                break
            parent_number = parent_number.rsplit(".", 1)[0]
        return "course"

    def _prefer_outline_name(self, candidate: str, current: str) -> bool:
        if self._noisy_outline_title(candidate):
            return False
        if "介绍" in current and "介绍" not in candidate:
            return True
        return False

    def _course_name(self, chunks: list[dict[str, Any]]) -> str:
        for chunk in chunks[:5]:
            heading = self._clean_text(chunk.get("heading"))
            if heading and heading not in {"目录", "内容简介", "出版说明"}:
                return heading[:40]
            content = self._clean_text(chunk.get("content"))
            if content:
                return self._first_sentence(content)[:40] or "课程知识图谱"
        return "课程知识图谱"

    def _first_chunk_ids(self, chunks: list[dict[str, Any]]) -> list[str]:
        chunk_ids = [str(chunk.get("id")) for chunk in chunks[:3] if chunk.get("id") is not None]
        return chunk_ids[:1] or ["course-root"]

    def _summary_for_outline_item(self, name: str, chunk: dict[str, Any]) -> str:
        sentence = self._first_sentence(chunk.get("content"))
        if sentence:
            return sentence[:220]
        return f"教材目录中的知识点：{name}。"

    def _outline_node_type(self, name: str) -> str:
        if any(token in name for token in ["实验", "习题", "练习", "案例"]):
            return "case"
        if any(token in name for token in ["安装", "环境", "工具", "文件", "模块"]):
            return "tool"
        if any(token in name for token in ["函数", "语句", "操作", "算法", "正则"]):
            return "method"
        return "concept"

    def _normalize_outline_text(self, value: str) -> str:
        value = value.replace("……", " ... ").replace("…", " ... ")
        value = value.replace("．", ".").replace("。", " 。 ")
        return re.sub(r"\s+", " ", value).strip()

    def _clean_outline_title(self, value: str) -> str:
        value = self._normalize_outline_text(value)
        value = re.sub(r"^介绍", "", value)
        value = re.sub(r"^\)、[^A-Za-z\u4e00-\u9fff]*", "", value)
        value = re.split(r"\s+(?:A|B|C|D)\s*[.．]", value, maxsplit=1)[0]
        value = re.split(r"\s+\d{1,2}\s*[.．、]\s+", value, maxsplit=1)[0]
        value = re.split(r"\s+习题\s*\d*", value, maxsplit=1)[0]
        value = re.split(r"\s+Python\s+\d+(?:\.\d+){1,3}", value, maxsplit=1)[0]
        value = re.split(r"\s*(?:\.{2,}|[-—]+)\s*\d{1,4}\s+(?=上机实验|实验|习题|第\s*\d+\s*章|\d{1,2}(?:\.\d{1,2}){1,3}\b)", value, maxsplit=1)[0]
        value = re.sub(r"\s*(?:\.{2,}|[-—]+)\s*\d{1,4}\s*$", "", value)
        value = re.sub(r"\s+\d{1,4}\s*$", "", value)
        value = re.split(r"\s+(?:第\s*\d+\s*章|\d{1,2}(?:\.\d{1,2}){1,3})\s+", value, maxsplit=1)[0]
        value = re.split(r"\s+(?:Python 程序设计|目录|习题\d*)\s*$", value, maxsplit=1)[0]
        return value.strip(" .·-—:：；;")

    def _valid_outline_title(self, title: str) -> bool:
        if len(title) < 2 or len(title) > 60:
            return False
        if self._noisy_outline_title(title):
            return False
        blocked = ["目录", "出版社", "内容简介", "出版说明", "参考文献"]
        if any(token in title for token in blocked):
            return False
        return bool(re.search(r"[\u4e00-\u9fffA-Za-z]", title))

    def _noisy_outline_title(self, title: str) -> bool:
        return any(token in title for token in ["作者", "编者"])

    def _representative_chunks(self, chunks: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        seen_headings: set[str] = set()
        for chunk in chunks:
            heading = self._clean_text(chunk.get("heading"))
            content = self._clean_text(chunk.get("content"))
            if not heading and not content:
                continue
            key = heading.lower() or content[:30].lower()
            if key in seen_headings:
                continue
            seen_headings.add(key)
            selected.append(
                {
                    "id": chunk.get("id"),
                    "source_locator": chunk.get("source_locator"),
                    "heading": heading[:80],
                    "content": content[:600],
                }
            )
            if len(selected) >= limit:
                break
        return selected

    def _normalize_graph(
        self, data: dict[str, Any], chunks: list[dict[str, Any]] | None = None
    ) -> dict[str, list[dict[str, Any]]]:
        available_chunk_ids = [
            str(chunk.get("id"))
            for chunk in (chunks or [])
            if chunk.get("id") is not None
        ]
        raw_nodes = data.get("nodes") if isinstance(data, dict) else None
        raw_edges = data.get("edges") if isinstance(data, dict) else None

        nodes: list[dict[str, Any]] = []
        emitted_node_ids: set[str] = set()
        for index, raw_node in enumerate(raw_nodes if isinstance(raw_nodes, list) else []):
            if not isinstance(raw_node, dict):
                continue

            node_id = self._clean_text(raw_node.get("id")) or f"node-{index}"
            if node_id in emitted_node_ids:
                node_id = f"node-{index}"
            emitted_node_ids.add(node_id)

            node_type = self._clean_text(raw_node.get("node_type"))
            if node_type not in ALLOWED_NODE_TYPES:
                node_type = "concept"

            difficulty = self._clean_text(raw_node.get("difficulty"))
            if difficulty not in ALLOWED_DIFFICULTIES:
                difficulty = "basic"

            nodes.append(
                {
                    "id": node_id,
                    "name": self._clean_text(raw_node.get("name")),
                    "node_type": node_type,
                    "difficulty": difficulty,
                    "summary": self._clean_text(raw_node.get("summary")),
                    "source_chunk_ids": self._normalize_source_chunk_ids(
                        raw_node.get("source_chunk_ids"), available_chunk_ids
                    ),
                    "confidence": self._normalize_confidence(raw_node.get("confidence")),
                    "level": self._normalize_int(raw_node.get("level"), 1),
                    "order": self._normalize_int(raw_node.get("order"), index),
                    "parent_id": self._clean_text(raw_node.get("parent_id")),
                }
            )

        edges: list[dict[str, Any]] = []
        for index, raw_edge in enumerate(raw_edges if isinstance(raw_edges, list) else []):
            if not isinstance(raw_edge, dict):
                continue

            relation_type = self._clean_text(raw_edge.get("relation_type"))
            if relation_type not in ALLOWED_RELATION_TYPES:
                continue

            source_node_id = self._clean_text(raw_edge.get("source_node_id"))
            target_node_id = self._clean_text(raw_edge.get("target_node_id"))
            if source_node_id not in emitted_node_ids or target_node_id not in emitted_node_ids:
                continue

            edges.append(
                {
                    "id": self._clean_text(raw_edge.get("id")) or f"edge-{index}",
                    "source_node_id": source_node_id,
                    "target_node_id": target_node_id,
                    "relation_type": relation_type,
                    "reason": self._clean_text(raw_edge.get("reason")),
                    "confidence": self._normalize_confidence(raw_edge.get("confidence")),
                }
            )

        return {"nodes": nodes, "edges": edges}

    def _normalize_source_chunk_ids(self, value: Any, available_chunk_ids: list[str]) -> list[str]:
        if isinstance(value, list):
            source_chunk_ids = [str(item) for item in value if item is not None]
        elif value is not None:
            source_chunk_ids = [str(value)]
        else:
            source_chunk_ids = []

        if available_chunk_ids:
            valid_chunk_ids = [chunk_id for chunk_id in source_chunk_ids if chunk_id in available_chunk_ids]
            return valid_chunk_ids or available_chunk_ids
        return source_chunk_ids

    def _merge_outline_and_semantic_graphs(
        self,
        outline_graph: dict[str, list[dict[str, Any]]],
        semantic_graph: dict[str, list[dict[str, Any]]],
    ) -> dict[str, list[dict[str, Any]]]:
        if not outline_graph.get("nodes"):
            return semantic_graph

        nodes: list[dict[str, Any]] = []
        node_ids: set[str] = set()
        for node in outline_graph.get("nodes", []) + semantic_graph.get("nodes", []):
            node_id = self._clean_text(node.get("id"))
            if not node_id:
                continue
            if node_id in node_ids:
                continue
            next_node = dict(node)
            next_node["id"] = node_id
            nodes.append(next_node)
            node_ids.add(node_id)

        edges: list[dict[str, Any]] = []
        edge_ids: set[str] = set()
        for edge in outline_graph.get("edges", []) + semantic_graph.get("edges", []):
            source_node_id = self._clean_text(edge.get("source_node_id"))
            target_node_id = self._clean_text(edge.get("target_node_id"))
            if source_node_id not in node_ids or target_node_id not in node_ids:
                continue
            edge_id = self._clean_text(edge.get("id")) or f"edge-{source_node_id}-{target_node_id}"
            if edge_id in edge_ids:
                edge_id = f"{edge_id}-{len(edge_ids)}"
            next_edge = dict(edge)
            next_edge["id"] = edge_id
            next_edge["source_node_id"] = source_node_id
            next_edge["target_node_id"] = target_node_id
            edges.append(next_edge)
            edge_ids.add(edge_id)

        return {"nodes": nodes, "edges": edges}

    def _normalize_confidence(self, value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.0
        return min(1.0, max(0.0, confidence))

    def _normalize_int(self, value: Any, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _first_sentence(self, value: Any) -> str:
        text = self._clean_text(value)
        if not text:
            return ""
        for delimiter in ["。", ".", "\n"]:
            if delimiter in text:
                return text.split(delimiter, 1)[0].strip()[:160]
        return text[:160]

    def _slug(self, value: str) -> str:
        slug = "".join(char.lower() if char.isalnum() else "-" for char in value)
        return "-".join(part for part in slug.split("-") if part)[:80]
