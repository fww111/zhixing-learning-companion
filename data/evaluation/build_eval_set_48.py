"""构造 AgentArts 平台评测集 48 条（issue #12）。

输入空间：data/seed/cpp_algorithms/cpp_algorithms.json 中《C++算法学习》8 章真实小节。
构造规则：每章选 2 个知识点 × 3 种学生画像（零基础 / 有C基础 / 冲刺竞赛）= 48 条。
输出：
  - agentarts_eval_set_48.json：人读/存档的完整结构（含 meta 与字段说明）
  - agentarts_eval_set_48.jsonl：平台导入用，每行一条扁平用例

运行：python data/evaluation/build_eval_set_48.py
脚本自带校验：用例数必须为 48，且完整覆盖 8 章 × 2 知识点 × 3 画像、字段非空。
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
SPEC_PATH = REPO_ROOT / "data" / "seed" / "cpp_algorithms" / "cpp_algorithms.json"
JSON_OUT = HERE / "agentarts_eval_set_48.json"
JSONL_OUT = HERE / "agentarts_eval_set_48.jsonl"

# 每章选取的 2 个知识点（section id），均来自教材真实小节
PICKED_POINTS: dict[str, tuple[str, str]] = {
    "cpp-1": ("cpp-1-2", "cpp-1-4"),
    "cpp-2": ("cpp-2-2", "cpp-2-5"),
    "cpp-3": ("cpp-3-1", "cpp-3-3"),
    "cpp-4": ("cpp-4-1", "cpp-4-2"),
    "cpp-5": ("cpp-5-1", "cpp-5-3"),
    "cpp-6": ("cpp-6-1", "cpp-6-3"),
    "cpp-7": ("cpp-7-1", "cpp-7-3"),
    "cpp-8": ("cpp-8-1", "cpp-8-3"),
}

# 知识点级配置：期望资源类型偏好 + 关键内容点（期望资源包必须覆盖）+ 证据/易错约束
POINT_DETAIL: dict[str, dict[str, object]] = {
    "cpp-1-2": {
        "resources": ["document", "exercise", "mind_map"],
        "key_points": ["大O表示法的含义与上界思想", "常见复杂度 O(1)/O(log n)/O(n)/O(n^2) 的比较", "循环嵌套与基本语句执行次数估算"],
        "evidence_constraint": "复杂度排序结论必须与教材一致，不得编造增长率",
    },
    "cpp-1-4": {
        "resources": ["document", "code_lab", "reading"],
        "key_points": ["容器/迭代器/算法三大组件", "vector 的常用操作与复杂度", "编译运行单文件 C++ 的基本流程"],
        "evidence_constraint": "只讲标准库 STL，示例需可编译，不引入第三方库",
    },
    "cpp-2-2": {
        "resources": ["document", "code_lab", "exercise"],
        "key_points": ["栈 LIFO 与队列 FIFO 特性", "STL stack/queue 接口", "括号匹配等典型应用场景"],
        "evidence_constraint": "接口名与行为以 STL 为准，应用示例需可运行",
    },
    "cpp-2-5": {
        "resources": ["document", "exercise", "code_lab"],
        "key_points": ["哈希思想与平均 O(1) 查找", "unordered_map/set 用法", "哈希冲突与最坏情况复杂度"],
        "evidence_constraint": "区分平均与最坏复杂度，不得承诺恒为 O(1)",
    },
    "cpp-3-1": {
        "resources": ["document", "mind_map", "exercise"],
        "key_points": ["冒泡/插入/选择/快排的思想", "时间/空间复杂度与稳定性对比", "排序适用场景"],
        "evidence_constraint": "复杂度与稳定性数据以教材对比表为准",
    },
    "cpp-3-3": {
        "resources": ["document", "code_lab", "exercise"],
        "key_points": ["单调性前提与折半思想", "循环不变量与边界处理", "查找区间更新与终止条件"],
        "evidence_constraint": "必须处理边界与死循环风险（off-by-one）",
    },
    "cpp-4-1": {
        "resources": ["document", "mind_map", "code_lab"],
        "key_points": ["递归三要素：基准情形/递归情形/收敛", "调用栈与栈帧", "递归改写与栈溢出风险"],
        "evidence_constraint": "示例必须有明确基准情形且能终止",
    },
    "cpp-4-2": {
        "resources": ["document", "code_lab", "reading"],
        "key_points": ["分/治/合三步框架", "递归式与复杂度分析", "问题可分性与合并代价"],
        "evidence_constraint": "复杂度分析需对应递归树，不臆造结论",
    },
    "cpp-5-1": {
        "resources": ["document", "code_lab", "exercise"],
        "key_points": ["图/树的深度优先遍历顺序", "递归与显式栈两种实现", "访问标记与状态恢复"],
        "evidence_constraint": "必须有 visited 标记避免重复访问",
    },
    "cpp-5-3": {
        "resources": ["document", "code_lab", "exercise"],
        "key_points": ["队列驱动的层序扩展", "BFS 与最短路径的关系", "入队即标记的时机"],
        "evidence_constraint": "无权图最短路结论需注明边权为 1 的前提",
    },
    "cpp-6-1": {
        "resources": ["document", "mind_map", "code_lab"],
        "key_points": ["重叠子问题与最优子结构", "状态定义与转移方程", "记忆化搜索与自顶向下"],
        "evidence_constraint": "状态转移必须有基准情形，避免无限递归",
    },
    "cpp-6-3": {
        "resources": ["document", "code_lab", "exercise"],
        "key_points": ["0/1 背包与完全背包区别", "状态压缩与遍历方向", "容量/重量/价值的建模"],
        "evidence_constraint": "遍历方向差异（正序/逆序）结论以教材为准",
    },
    "cpp-7-1": {
        "resources": ["document", "code_lab", "mind_map"],
        "key_points": ["邻接矩阵与邻接表", "空间复杂度与适用场景", "有向/无向边的存储方式"],
        "evidence_constraint": "两种表示的复杂度对比需与教材一致",
    },
    "cpp-7-3": {
        "resources": ["document", "code_lab", "reading"],
        "key_points": ["BFS 单源最短路与 Dijkstra 思想", "松弛操作", "负权边的限制条件"],
        "evidence_constraint": "Dijkstra 不适用负权的限制必须明确写出",
    },
    "cpp-8-1": {
        "resources": ["document", "exercise", "reading"],
        "key_points": ["贪心选择性质与局部最优", "交换论证/反证可行性", "贪心与 DP 的边界"],
        "evidence_constraint": "必须给出贪心正确性论证，不能只靠直觉",
    },
    "cpp-8-3": {
        "resources": ["document", "code_lab", "exercise"],
        "key_points": ["集合的合并与查找", "路径压缩与按秩合并", "近常数时间复杂度来源"],
        "evidence_constraint": "复杂度结论按教材表述，不夸大到严格 O(1)",
    },
}

# 画像级配置：讲解风格、深度、资源侧重与输入口吻
PROFILES: dict[str, dict[str, str | list[str]]] = {
    "zero_basic": {
        "label": "零基础",
        "depth": "从生活类比和最基础概念讲起，避免前置术语，逐步引入",
        "style": "通俗、多比喻、小步前进，配可运行最小示例",
        "preferred": "document,code_lab",
        "ask": "我完全没接触过这个，能不能从零开始、用大白话给我讲清楚「{point}」？",
    },
    "c_basic": {
        "label": "有C基础",
        "depth": "默认掌握 C 语法与基本流程控制，重点讲 C++/STL 差异与算法本身",
        "style": "对比 C 与 C++ 写法，强调接口与复杂度，给中等难度示例",
        "preferred": "document,exercise,code_lab",
        "ask": "我有 C 语言基础，想系统理解「{point}」，请重点讲 STL 用法和复杂度，再给练习。",
    },
    "competition": {
        "label": "冲刺竞赛",
        "depth": "跳过入门铺垫，聚焦边界条件、易错点、模板与竞赛题型迁移",
        "style": "精炼、给模板和复杂度上界，强调 off-by-one/溢出/超时等实战坑",
        "preferred": "code_lab,exercise,reading",
        "ask": "我在备赛，需要「{point}」的竞赛模板、边界与常见坑，最好有可迁移的题目和复杂度分析。",
    },
}

EVALUATION_DIMENSIONS = [
    {"name": "正确性", "pass_rule": "关键内容点全部正确，可执行代码可编译且输出符合预期", "weight": 0.4},
    {"name": "幻觉", "pass_rule": "无证据外的知识性断言，复杂度/接口结论与教材一致，幻觉率 < 5%", "weight": 0.3},
    {"name": "任务完成度", "pass_rule": "产出对应资源类型且结构完整，含可执行的下一步", "weight": 0.15},
    {"name": "教学适配度", "pass_rule": "深度与风格匹配该画像，资源侧重与画像偏好一致", "weight": 0.15},
]


def build_cases(spec: dict) -> list[dict]:
    section_index: dict[str, dict] = {}
    for ch in spec["chapters"]:
        for sec in ch["sections"]:
            section_index[sec["id"]] = sec

    cases: list[dict] = []
    seq = 0
    for ch in spec["chapters"]:
        for point_id in PICKED_POINTS[ch["id"]]:
            sec = section_index[point_id]
            detail = POINT_DETAIL[point_id]
            for profile_key, profile in PROFILES.items():
                seq += 1
                case_id = f"E{seq:02d}"
                user_message = str(profile["ask"]).format(point=sec["name"])
                cases.append(
                    {
                        "case_id": case_id,
                        "chapter_id": ch["id"],
                        "chapter_name": ch["name"],
                        "knowledge_point_id": point_id,
                        "knowledge_point_name": sec["name"],
                        "learner_profile": profile_key,
                        "learner_profile_label": profile["label"],
                        "input": {
                            "user_id": "{{user_id}}",
                            "course_id": "{{course_id}}",
                            "node_id": point_id,
                            "message": user_message,
                        },
                        "expected_resource": {
                            "resource_types": detail["resources"],
                            "preferred_for_profile": profile["preferred"],
                            "key_points": detail["key_points"],
                            "evidence_constraint": detail["evidence_constraint"],
                            "pedagogy": {
                                "depth": profile["depth"],
                                "style": profile["style"],
                            },
                        },
                        "evaluation": EVALUATION_DIMENSIONS,
                    }
                )
    return cases


def flatten(case: dict) -> dict:
    """扁平化为平台导入的单行结构（JSONL）。"""
    return {
        "case_id": case["case_id"],
        "chapter_id": case["chapter_id"],
        "chapter_name": case["chapter_name"],
        "knowledge_point_id": case["knowledge_point_id"],
        "knowledge_point_name": case["knowledge_point_name"],
        "learner_profile": case["learner_profile"],
        "node_id": case["input"]["node_id"],
        "user_message": case["input"]["message"],
        "expected_resource_types": "|".join(case["expected_resource"]["resource_types"]),
        "expected_key_points": "|".join(case["expected_resource"]["key_points"]),
        "evidence_constraint": case["expected_resource"]["evidence_constraint"],
        "evaluation_dimensions": "|".join(dim["name"] for dim in case["evaluation"]),
    }


def validate(cases: list[dict]) -> None:
    assert len(cases) == 48, f"用例数应为 48，实际 {len(cases)}"
    combos = {(c["chapter_id"], c["knowledge_point_id"], c["learner_profile"]) for c in cases}
    assert len(combos) == 48, "存在重复的 章×知识点×画像 组合"
    assert len({c["chapter_id"] for c in cases}) == 8, "应覆盖 8 章"
    for c in cases:
        assert c["input"]["message"].strip(), f"{c['case_id']} 输入为空"
        assert c["expected_resource"]["key_points"], f"{c['case_id']} 缺少关键内容点"
        assert c["expected_resource"]["resource_types"], f"{c['case_id']} 缺少期望资源类型"
        assert len(c["evaluation"]) == 4, f"{c['case_id']} 评估维度应为 4 个"


def main() -> None:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    cases = build_cases(spec)
    validate(cases)

    payload = {
        "meta": {
            "course": spec["course"],
            "issue": "#12",
            "total": len(cases),
            "structure": "8 章 × 2 知识点 × 3 画像",
            "profiles": {k: v["label"] for k, v in PROFILES.items()},
            "evaluation_dimensions": [d["name"] for d in EVALUATION_DIMENSIONS],
            "source_spec": str(SPEC_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        },
        "cases": cases,
    }
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with JSONL_OUT.open("w", encoding="utf-8", newline="\n") as fh:
        for case in cases:
            fh.write(json.dumps(flatten(case), ensure_ascii=False) + "\n")

    print(f"[ok] 生成 {len(cases)} 条评测用例")
    print(f"[ok] {JSON_OUT.relative_to(REPO_ROOT)}")
    print(f"[ok] {JSONL_OUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
