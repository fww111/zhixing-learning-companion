"""Smoke-test the AgentArts prompt pack with the Zhipu cheap model (glm-4-flash).

Validates that the doc-04 prompts produce parseable, schema-conformant JSON,
and runs one end-to-end chain: LLM extract_profile -> MCP save_student_profile
-> MCP get_student_profile (sqlite backend).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="zhixing-prompt-e2e-")
os.environ["DATABASE_URL"] = f"sqlite:///{(Path(_TMP) / 'e2e.db').as_posix()}"
os.environ.setdefault("MOCK_LLM", "false")

import httpx  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp_servers._bootstrap import ensure_api_importable  # noqa: E402

ensure_api_importable()

from app.core.config import settings  # noqa: E402
from app.db import init_db  # noqa: E402
from mcp_servers import profile_server  # noqa: E402

URL = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
MODEL = settings.llm_model


def chat(prompt: str, max_tokens: int = 3000) -> str:
    response = httpx.post(
        URL,
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        timeout=120,
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": "你是严格的 JSON 生成器，只输出 JSON，不要输出任何其他文字或代码块围栏。"},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        },
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in: {text[:120]}")
    return json.loads(text[start : end + 1])


def test_extract_profile() -> dict:
    conversation = [
        ("assistant", "请介绍一下你的专业、年级和学习目标（例如这学期想达到什么水平）？"),
        ("user", "我是计算机科学专业大二学生，这学期想系统学完C++算法，能独立做蓝桥杯的题"),
        ("assistant", "好的！那你目前C++和算法的基础怎么样？比如学过哪些数据结构，哪里最容易卡住？"),
        ("user", "学过C语言基础，链表那块理解还行，但是动态规划完全没思路，二分边界老是写错"),
        ("assistant", "明白。你平时每天能安排多少时间学习？更喜欢看动画演示、图解还是直接上手写代码？"),
        ("user", "每天晚上大概45分钟吧，我喜欢先看图理解然后马上写代码练一下"),
    ]
    prompt = f"""从对话历史中抽取学生画像，严格输出如下 JSON（缺失字段按规则推断填充，不要留空）：
{{
  "major": "字符串", "grade": "字符串", "learning_goal": "一句话学习目标",
  "knowledge_foundation": "一句话概括已有基础",
  "weak_points": ["薄弱知识点数组，2-4 个，尽量来自《C++算法学习》内容"],
  "learning_style": "偏好描述", "cognitive_style": "描述",
  "time_preference": "如 每天晚间45分钟",
  "resource_preference": ["动画/图解/代码实操/短练习/阅读材料 中选 1-3 个"],
  "motivation": "一句话", "constraints": ["数组，可为空"],
  "assessment_preference": "如 短练习和阶段测验",
  "knowledge_graph_focus": ["从薄弱点中选 1-2 个"]
}}
只输出 JSON。

【对话历史】
""" + "\n".join(f"{role}：{content}" for role, content in conversation)

    profile = parse_json(chat(prompt))
    required = {"major", "grade", "learning_goal", "knowledge_foundation", "weak_points",
                "time_preference", "resource_preference", "knowledge_graph_focus"}
    missing = required - profile.keys()
    assert not missing, f"missing fields: {missing}"
    assert isinstance(profile["weak_points"], list) and profile["weak_points"], "weak_points empty"
    print(f"[ok] extract_profile -> weak_points={profile['weak_points']}, "
          f"time={profile['time_preference']}, resource={profile['resource_preference']}")
    return profile


def test_fact_check() -> None:
    evidence = [
        {"chunk_id": 1, "heading": "3.3 二分查找",
         "content": "二分查找在有序序列上每次把搜索范围减半，O(log n)。lower_bound 返回第一个 >= x 的迭代器。"
                    "mid 应写 lo + (hi - lo) / 2 防止溢出。"},
    ]
    resource = """## 二分查找讲解
二分查找要求数组有序，时间复杂度 O(log n)，每次把范围缩小一半。
在 C++ 中手写 mid 时推荐 `int mid = lo + (hi - lo) / 2;` 防止整数溢出。
注意：二分查找的时间复杂度是 O(n log n)。
延伸内容：跳表也可以实现类似的对数级查找。"""
    prompt = f"""你是事实校验 Agent。你的职责是【找错】，宁可误报不可漏报，绝不能默认资源是正确的。
按以下两阶段严格执行：
阶段一：把【待审资源】拆成原子断言清单（每个知识性句子一条，含每条复杂度结论、每个代码行为结论），编号 C1、C2……
阶段二：对每条断言，在【原文证据】中找到逐字支撑的引文；找不到逐字引文的一律判 supported=false，并把该断言加入 unsupported_claims。特别注意：断言中的复杂度、边界行为、语法结论必须与证据逐字一致，数值或量级不同即为错误。
输出 JSON：
{{"assertions": [{{"id": "C1", "claim": "...", "supported": true/false, "evidence_quote": "逐字引文或空", "chunk_id": 数字或null}}], "code_ok": true/false, "unsupported_claims": ["C编号+断言内容"], "violations": ["每一条 supported=false 的断言都必须出现在这里，格式：编号+断言+错误原因"], "pass": true/false}}
violations 必须由断言结果机械推导：任何 supported=false 的断言都要进 violations，一条不漏；violations 与 unsupported_claims 数量不一致即为你的错误。只有 violations 为空且 code_ok 为 true 时 pass 才为 true。只输出 JSON。

【原文证据】
{json.dumps(evidence, ensure_ascii=False, indent=2)}

【待审资源】
{resource}"""

    report = parse_json(chat(prompt))
    violations = report.get("violations", [])
    print(f"[ok] fact_check -> pass={report.get('pass')}, "
          f"unsupported={report.get('unsupported_claims')}, violations={violations}")
    assert report.get("pass") is False, "expected pass=false for the wrong complexity claim"
    assert violations or report.get("unsupported_claims"), "expected at least one flagged claim"
    return violations or report.get("unsupported_claims")


def test_e2e_llm_to_mcp(profile: dict) -> None:
    init_db()
    from app.db import SessionLocal
    from app.models.course import Course
    from app.models.user import User

    with SessionLocal() as db:
        user = User(username="e2e_glm", email="e2e-glm@zhixing.local", password_hash="x")
        db.add(user)
        db.flush()
        course = Course(user_id=user.id, name="C++算法学习", status="ready")
        db.add(course)
        db.commit()
        user_id, course_id = user.id, course.id

    saved = profile_server.save_student_profile_impl(
        user_id=user_id, course_id=course_id, profile=profile, source="e2e_glm"
    )
    assert saved["ok"] is True, saved
    assert saved["completion_score"] and saved["completion_score"] > 0

    got = profile_server.get_student_profile_impl(user_id=user_id, course_id=course_id)
    assert got["ok"] is True and got["exists"] is True
    assert got["profile"]["learning_goal"] == profile["learning_goal"]
    print(f"[ok] e2e: LLM 画像 -> save_student_profile -> get_student_profile "
          f"(completion_score={saved['completion_score']}, student_id={got['student_id']})")


if __name__ == "__main__":
    profile = test_extract_profile()
    test_fact_check()
    test_e2e_llm_to_mcp(profile)
    print("\nall prompt-pack smoke tests passed")
