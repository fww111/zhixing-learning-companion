"""RAG 检索词法工具：领域术语表 + 查询扩展（纯函数）。

术语表自 tutor_service 的 DOMAIN_TERMS / ENGLISH_TERM_SYNONYMS 抽出复用，
供 Agentic RAG 的查询扩展与句级压缩共用（单一事实源）。
"""

from __future__ import annotations

import re

DOMAIN_TERMS = [
    "计算机",
    "程序",
    "指令",
    "算法",
    "变量名",
    "变量",
    "标识符",
    "输入",
    "输出",
    "函数",
    "参数",
    "返回值",
    "循环",
    "分支",
    "条件",
    "数组",
    "指针",
    "地址",
    "结构体",
    "排序",
    "内存",
    "编译",
    "运行",
    "语句",
    "数据类型",
    "表达式",
    "贪心",
    "递归",
    "动态规划",
    "链表",
    "栈",
    "队列",
    "哈希",
    "二叉树",
    "图",
]

ENGLISH_TERM_SYNONYMS = {
    "computer": ["计算机"],
    "program": ["程序", "指令"],
    "programming": ["程序"],
    "instruction": ["指令"],
    "algorithm": ["算法"],
    "variable": ["变量", "变量名"],
    "variables": ["变量", "变量名"],
    "identifier": ["标识符", "变量名"],
    "identifiers": ["标识符", "变量名"],
    "naming": ["命名", "变量名"],
    "input": ["输入"],
    "output": ["输出"],
    "function": ["函数"],
    "loop": ["循环"],
    "array": ["数组"],
    "pointer": ["指针", "地址"],
    "struct": ["结构体"],
    "greedy": ["贪心"],
    "recursion": ["递归"],
    "dynamic": ["动态"],
    "programming": ["程序"],
    "linked": ["链表"],
    "list": ["链表", "列表"],
    "stack": ["栈"],
    "queue": ["队列"],
    "hash": ["哈希", "散列"],
    "tree": ["树", "二叉树"],
    "graph": ["图"],
    "sort": ["排序"],
    "memory": ["内存"],
    "compile": ["编译"],
}

GENERIC_STOP_TERMS = {
    "有人",
    "认为",
    "为什么",
    "什么",
    "怎么",
    "如何",
    "题目",
    "问题",
    "完成",
    "各种",
    "事务",
    "依据",
    "解释",
    "图片",
    "截图",
    "课程",
    "知识点",
    "please",
    "explain",
    "screenshot",
    "question",
    "answer",
    "node",
    "text",
    "only",
    "帮我",
    "看看",
    "一下",
}


def extract_query_terms(text: str) -> set[str]:
    """从查询中抽取领域术语（中文 2-6 字词 + 英文标识符），停用词过滤。"""
    normalized = re.sub(r"[-+]+", " ", (text or "").lower())
    terms: set[str] = set()
    for term in DOMAIN_TERMS:
        if term.lower() in normalized:
            terms.add(term.lower())
    for word in re.findall(r"[a-zA-Z][a-zA-Z0-9_+-]{2,}", normalized):
        if word in GENERIC_STOP_TERMS:
            continue
        terms.add(word)
        for synonym in ENGLISH_TERM_SYNONYMS.get(word, []):
            terms.add(synonym.lower())
    for sequence in re.findall(r"[\u4e00-\u9fff]{2,6}", text or ""):
        if sequence in GENERIC_STOP_TERMS or len(sequence) < 2:
            continue
        terms.add(sequence.lower())
    return {term for term in terms if term and term not in GENERIC_STOP_TERMS}


def expand_query_with_terms(query: str, *, max_expansions: int = 3) -> str:
    """查询扩展：为英文术语追加中文同义，让向量化查询同时覆盖两种表达。

    例："greedy algorithm 特点" → "greedy algorithm 特点 贪心 算法"。
    """
    terms = extract_query_terms(query)
    expansions: list[str] = []
    for word in re.findall(r"[a-zA-Z][a-zA-Z0-9_+-]{2,}", query or ""):
        for synonym in ENGLISH_TERM_SYNONYMS.get(word.lower(), []):
            if synonym not in (query or "") and synonym not in expansions:
                expansions.append(synonym)
            if len(expansions) >= max_expansions:
                break
        if len(expansions) >= max_expansions:
            break
    if not expansions:
        return query or ""
    return f"{(query or '').strip()} {' '.join(expansions)}".strip()
