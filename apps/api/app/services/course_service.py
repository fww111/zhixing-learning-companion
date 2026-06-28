from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.agents.knowledge_graph_agent import KnowledgeGraphAgent
from app.core.config import settings
from app.core.storage import course_upload_dir, safe_upload_name
from app.models.course import Course, CourseMaterial, GraphBuildJob, KnowledgeChunk, KnowledgeNodeMastery
from app.schemas.course import CourseCreate
from app.services.chunking_service import chunk_pages
from app.services.graph_store import Neo4jGraphStore
from app.services.material_parser import MaterialParseError, parse_material
from app.services.vector_service import MilvusVectorService


logger = logging.getLogger(__name__)


class CourseNotFoundError(RuntimeError):
    pass


class UnsupportedMaterialTypeError(ValueError):
    pass


class MaterialNotFoundError(RuntimeError):
    pass


DEFAULT_PYTHON_COURSE_NAME = "Python 程序设计"
DEFAULT_PYTHON_MARKER = "built-in:python"
DEFAULT_PYTHON_MATERIAL_DELETED_MARKER = "built-in:python:material-deleted"
DEFAULT_PYTHON_MATERIAL_FILENAME = "python-default-knowledge-base.md"
DEFAULT_PYTHON_MATERIAL_STORAGE_PATH = "built-in://python/default-knowledge-base"
DEFAULT_C_COURSE_NAME = "C语言程序设计"
DEFAULT_C_MARKER = "built-in:c"
DEFAULT_C_MATERIAL_DELETED_MARKER = "built-in:c:material-deleted"
DEFAULT_C_MATERIAL_FILENAME = "c-default-knowledge-base.md"
DEFAULT_C_MATERIAL_STORAGE_PATH = "built-in://c/default-knowledge-base"

_COMPACT_PYTHON_OUTLINE = [
    {
        "id": "py-course-intro",
        "name": "Python 课程导论",
        "summary": "建立 Python 程序设计的整体认知，理解解释器、运行方式、代码规范和基础调试流程。",
        "children": [
            {
                "id": "py-runtime-environment",
                "name": "开发环境与解释器",
                "node_type": "tool",
                "difficulty": "basic",
                "summary": "掌握 Python 解释器、虚拟环境、编辑器和命令行运行环境的基本配置方法。",
            },
            {
                "id": "py-program-execution",
                "name": "程序执行过程",
                "node_type": "concept",
                "difficulty": "basic",
                "summary": "理解源代码、解释执行、语句顺序和程序入口，能解释一段脚本从编写到运行的过程。",
            },
            {
                "id": "py-code-style",
                "name": "代码书写规范",
                "node_type": "method",
                "difficulty": "basic",
                "summary": "掌握缩进、命名、注释和可读性规范，形成清晰、可维护的代码书写习惯。",
            },
            {
                "id": "py-input-output",
                "name": "输入输出基础",
                "node_type": "method",
                "difficulty": "basic",
                "summary": "使用 input 和 print 完成交互式输入输出，理解字符串输入与显示格式的关系。",
            },
            {
                "id": "py-debugging-basics",
                "name": "基础调试方法",
                "node_type": "method",
                "difficulty": "basic",
                "summary": "通过错误信息、断点、变量观察和小步运行定位语法错误与简单逻辑错误。",
            },
        ],
    },
    {
        "id": "py-data-expression",
        "name": "数据类型与表达式",
        "summary": "围绕变量、基础类型、运算符和表达式建立程序计算的核心基础。",
        "children": [
            {
                "id": "py-variables",
                "name": "变量与赋值",
                "node_type": "concept",
                "difficulty": "basic",
                "summary": "理解变量名、对象引用和赋值语句，能用变量保存并更新程序运行中的状态。",
            },
            {
                "id": "py-number-types",
                "name": "数值类型",
                "node_type": "concept",
                "difficulty": "basic",
                "summary": "掌握整数、浮点数和常见数值运算，理解精度、取整、取余和幂运算的使用场景。",
            },
            {
                "id": "py-string-bool-none",
                "name": "字符串、布尔值与空值",
                "node_type": "concept",
                "difficulty": "basic",
                "summary": "区分 str、bool 和 None，理解文本、真假判断和缺失值在程序中的表达方式。",
            },
            {
                "id": "py-operators-expressions",
                "name": "运算符与表达式",
                "node_type": "formula",
                "difficulty": "basic",
                "summary": "掌握算术、比较、逻辑和赋值运算符，能按优先级分析表达式求值结果。",
            },
            {
                "id": "py-format-conversion",
                "name": "类型转换与格式化输出",
                "node_type": "method",
                "difficulty": "basic",
                "summary": "使用 int、float、str 和 f-string 完成类型转换与格式化展示，避免输入类型错误。",
            },
        ],
    },
    {
        "id": "py-control-flow",
        "name": "程序控制结构",
        "summary": "通过条件、循环和流程控制语句表达分支决策与重复执行逻辑。",
        "children": [
            {
                "id": "py-if-branch",
                "name": "条件分支",
                "node_type": "method",
                "difficulty": "basic",
                "summary": "使用 if、elif 和 else 根据条件执行不同路径，能处理互斥分支和默认分支。",
            },
            {
                "id": "py-boolean-conditions",
                "name": "布尔表达式设计",
                "node_type": "formula",
                "difficulty": "basic",
                "summary": "用比较、逻辑组合和短路求值构造清晰的判断条件，避免条件遗漏和歧义。",
            },
            {
                "id": "py-for-loop",
                "name": "for 循环",
                "node_type": "method",
                "difficulty": "basic",
                "summary": "使用 for、range 和可迭代对象完成确定次数或集合遍历任务。",
            },
            {
                "id": "py-while-loop",
                "name": "while 循环",
                "node_type": "method",
                "difficulty": "basic",
                "summary": "使用 while 表达条件驱动的重复执行，关注循环初值、更新和终止条件。",
            },
            {
                "id": "py-loop-control",
                "name": "break、continue 与嵌套循环",
                "node_type": "method",
                "difficulty": "intermediate",
                "summary": "使用 break 和 continue 改变循环流程，能分析嵌套循环的执行顺序和边界。",
            },
        ],
    },
    {
        "id": "py-collections",
        "name": "序列、映射与集合",
        "summary": "学习 Python 常用容器，掌握字符串、列表、元组、字典、集合和推导式的组织方式。",
        "children": [
            {
                "id": "py-string-slicing",
                "name": "字符串索引与切片",
                "node_type": "method",
                "difficulty": "basic",
                "summary": "通过索引、切片和常用字符串方法完成文本定位、截取、查找和清洗。",
            },
            {
                "id": "py-list",
                "name": "列表",
                "node_type": "concept",
                "difficulty": "basic",
                "summary": "使用列表保存有序可变数据，掌握增删改查、遍历、排序和嵌套列表。",
            },
            {
                "id": "py-tuple",
                "name": "元组",
                "node_type": "concept",
                "difficulty": "basic",
                "summary": "理解元组的不可变特性，能在多返回值、固定记录和解包场景中使用元组。",
            },
            {
                "id": "py-dict-set",
                "name": "字典与集合",
                "node_type": "concept",
                "difficulty": "intermediate",
                "summary": "使用字典表达键值映射，使用集合完成去重、成员判断和集合运算。",
            },
            {
                "id": "py-comprehension",
                "name": "推导式",
                "node_type": "method",
                "difficulty": "intermediate",
                "summary": "使用列表、字典和集合推导式简洁表达筛选、映射和数据转换过程。",
            },
        ],
    },
    {
        "id": "py-functions-modules",
        "name": "函数与模块化",
        "summary": "通过函数、参数、作用域、递归和模块组织提升程序结构化与复用能力。",
        "children": [
            {
                "id": "py-function-definition",
                "name": "函数定义与调用",
                "node_type": "method",
                "difficulty": "basic",
                "summary": "使用 def 定义函数，通过调用封装重复逻辑，理解函数名、函数体和调用栈。",
            },
            {
                "id": "py-parameters-return",
                "name": "参数与返回值",
                "node_type": "method",
                "difficulty": "basic",
                "summary": "掌握位置参数、默认参数、关键字参数和 return，能设计清晰的函数输入输出。",
            },
            {
                "id": "py-scope",
                "name": "变量作用域",
                "node_type": "concept",
                "difficulty": "intermediate",
                "summary": "区分局部变量、全局变量和命名空间，避免函数内部状态污染和变量遮蔽。",
            },
            {
                "id": "py-recursion-lambda",
                "name": "递归与匿名函数",
                "node_type": "formula",
                "difficulty": "advanced",
                "summary": "理解递归基例、递归递推和 lambda 表达式，能判断递归问题的终止条件。",
            },
            {
                "id": "py-modules-packages",
                "name": "模块与包",
                "node_type": "tool",
                "difficulty": "intermediate",
                "summary": "使用 import 复用标准库、第三方库和自定义模块，理解包结构和模块搜索路径。",
            },
        ],
    },
    {
        "id": "py-files-exceptions",
        "name": "文件、异常与数据交换",
        "summary": "围绕文件系统、编码、结构化数据和异常处理，建立可靠的数据读写能力。",
        "children": [
            {
                "id": "py-path-encoding",
                "name": "路径与编码",
                "node_type": "concept",
                "difficulty": "basic",
                "summary": "理解相对路径、绝对路径、字符编码和换行符，避免跨平台文件访问问题。",
            },
            {
                "id": "py-text-file-io",
                "name": "文本文件读写",
                "node_type": "method",
                "difficulty": "basic",
                "summary": "使用 open、read、write 和迭代读取完成文本文件输入输出。",
            },
            {
                "id": "py-csv-json",
                "name": "CSV 与 JSON 数据处理",
                "node_type": "tool",
                "difficulty": "intermediate",
                "summary": "使用 csv 和 json 模块读写结构化数据，能完成简单数据交换和持久化。",
            },
            {
                "id": "py-exception-handling",
                "name": "异常处理",
                "node_type": "method",
                "difficulty": "intermediate",
                "summary": "使用 try、except、else 和 finally 处理运行时错误，提升程序健壮性。",
            },
            {
                "id": "py-context-manager",
                "name": "with 上下文管理",
                "node_type": "method",
                "difficulty": "intermediate",
                "summary": "使用 with 管理文件和外部资源，确保资源在异常情况下也能被正确释放。",
            },
        ],
    },
    {
        "id": "py-oop",
        "name": "面向对象基础",
        "summary": "学习类、对象、属性、方法、构造、封装、继承和多态等面向对象核心概念。",
        "children": [
            {
                "id": "py-class-object",
                "name": "类与对象",
                "node_type": "concept",
                "difficulty": "intermediate",
                "summary": "理解类是抽象模板、对象是具体实例，能用类描述具有属性和行为的实体。",
            },
            {
                "id": "py-attributes-methods",
                "name": "属性与方法",
                "node_type": "concept",
                "difficulty": "intermediate",
                "summary": "用属性保存对象状态，用方法表达对象行为，理解实例方法的调用方式。",
            },
            {
                "id": "py-constructor-self",
                "name": "构造方法与 self",
                "node_type": "method",
                "difficulty": "intermediate",
                "summary": "使用 __init__ 初始化对象状态，理解 self 与当前实例之间的绑定关系。",
            },
            {
                "id": "py-encapsulation",
                "name": "封装与接口",
                "node_type": "concept",
                "difficulty": "intermediate",
                "summary": "通过方法封装内部状态变化，设计清晰的对象接口并降低外部耦合。",
            },
            {
                "id": "py-inheritance-polymorphism",
                "name": "继承与多态",
                "node_type": "method",
                "difficulty": "advanced",
                "summary": "使用继承复用和扩展类能力，理解重写、父类调用和多态调用场景。",
            },
        ],
    },
    {
        "id": "py-project-practice",
        "name": "综合项目与工程实践",
        "summary": "将 Python 语言知识组织为可运行、可测试、可维护的小型课程项目。",
        "children": [
            {
                "id": "py-problem-decomposition",
                "name": "问题分解与流程设计",
                "node_type": "case",
                "difficulty": "intermediate",
                "summary": "将综合任务拆解为输入、处理、输出、数据结构和函数模块，形成实现路线。",
            },
            {
                "id": "py-third-party-library",
                "name": "第三方库使用",
                "node_type": "tool",
                "difficulty": "intermediate",
                "summary": "理解 pip、依赖安装和库文档阅读方式，能在项目中引入常用第三方能力。",
            },
            {
                "id": "py-testing-debugging",
                "name": "测试与调试",
                "node_type": "method",
                "difficulty": "intermediate",
                "summary": "通过样例测试、边界测试、断言和调试工具验证程序行为并定位问题。",
            },
            {
                "id": "py-code-quality",
                "name": "代码质量与重构",
                "node_type": "method",
                "difficulty": "intermediate",
                "summary": "关注命名、重复代码、函数粒度和模块边界，逐步提升代码可读性和维护性。",
            },
            {
                "id": "py-mini-project",
                "name": "课程综合案例",
                "node_type": "case",
                "difficulty": "advanced",
                "summary": "综合使用数据结构、控制结构、函数、文件和异常处理完成一个可演示的小型项目。",
            },
        ],
    },
]


def _default_python_topic(
    node_id: str,
    name: str,
    *,
    node_type: str = "concept",
    difficulty: str = "basic",
    summary: str = "",
    children: list[dict] | None = None,
    level: int | None = None,
) -> dict:
    topic = {
        "id": node_id,
        "name": name,
        "node_type": node_type,
        "difficulty": difficulty,
        "summary": summary or f"围绕{name}梳理概念、语法规则、典型用法和易错点，支撑课程知识图谱中的分层学习。",
    }
    if children:
        topic["children"] = children
    if level is not None:
        topic["level"] = level
    return topic


def _default_python_textbook_outline() -> list[dict]:
    topic = _default_python_topic
    return [
        topic(
            "outline-chapter-1",
            "第 1 章 Python 概述",
            summary="建立 Python 语言、开发环境、运行方式和学习路径的整体认知。",
            children=[
                topic("outline-section-1-1", "1.1 初识 Python"),
                topic(
                    "outline-section-1-2",
                    "1.2 Python 版本和开发环境",
                    children=[
                        topic("outline-section-1-2-1", "1.2.1 Python 的版本"),
                        topic("outline-section-1-2-2", "1.2.2 Python 的集成开发环境"),
                    ],
                ),
                topic(
                    "outline-section-1-3",
                    "1.3 Python 的安装和设置",
                    node_type="tool",
                    children=[
                        topic("outline-section-1-3-1", "1.3.1 Python 安装包的下载", node_type="tool"),
                        topic("outline-section-1-3-2", "1.3.2 Python 安装过程和环境变量设置", node_type="tool"),
                        topic("outline-section-1-3-3", "1.3.3 Python 扩展包的安装和管理", node_type="tool"),
                    ],
                ),
                topic(
                    "outline-section-1-4",
                    "1.4 执行 Python 程序",
                    node_type="method",
                    children=[
                        topic("outline-section-1-4-1", "1.4.1 命令行方式执行 Python 程序", node_type="method"),
                        topic("outline-section-1-4-2", "1.4.2 Python 集成开发环境 IDLE", node_type="tool"),
                        topic("outline-section-1-4-3", "1.4.3 Anaconda Python 科学计算环境", node_type="tool"),
                    ],
                ),
                topic("outline-section-1-5", "1.5 本章小结"),
                topic("outline-section-1-6", "1.6 上机实验", node_type="case"),
            ],
        ),
        topic(
            "outline-chapter-2",
            "第 2 章 Python 的基础语法",
            summary="掌握 Python 文件类型、代码规范、变量常量、数据类型和运算符等基础语法。",
            children=[
                topic("outline-section-2-1", "2.1 Python 的文件类型"),
                topic(
                    "outline-section-2-2",
                    "2.2 Python 代码书写规范",
                    node_type="method",
                    children=[
                        topic("outline-section-2-2-1", "2.2.1 Python 语句与代码行", node_type="method"),
                        topic("outline-section-2-2-2", "2.2.2 代码缩进与冒号", node_type="method"),
                        topic("outline-section-2-2-3", "2.2.3 使用空行分隔代码", node_type="method"),
                        topic("outline-section-2-2-4", "2.2.4 正确的注释", node_type="method"),
                    ],
                ),
                topic(
                    "outline-section-2-3",
                    "2.3 变量和常量",
                    children=[
                        topic("outline-section-2-3-1", "2.3.1 变量"),
                        topic("outline-section-2-3-2", "2.3.2 局部变量和全局变量"),
                        topic("outline-section-2-3-3", "2.3.3 常量"),
                    ],
                ),
                topic("outline-section-2-4", "2.4 数据类型"),
                topic(
                    "outline-section-2-5",
                    "2.5 运算符",
                    node_type="formula",
                    children=[
                        topic("outline-section-2-5-1", "2.5.1 算术运算符", node_type="formula"),
                        topic("outline-section-2-5-2", "2.5.2 关系运算符", node_type="formula"),
                        topic("outline-section-2-5-3", "2.5.3 逻辑运算符", node_type="formula"),
                    ],
                ),
                topic("outline-section-2-6", "2.6 本章小结"),
                topic("outline-section-2-7", "2.7 上机实验", node_type="case"),
            ],
        ),
        topic(
            "outline-chapter-3",
            "第 3 章 列表和元组",
            summary="围绕序列、列表、元组和生成器推导式建立 Python 容器基础。",
            children=[
                topic(
                    "outline-section-3-1",
                    "3.1 序列简介",
                    children=[
                        topic("outline-section-3-1-1", "3.1.1 索引", node_type="method"),
                        topic("outline-section-3-1-2", "3.1.2 切片", node_type="method"),
                        topic("outline-section-3-1-3", "3.1.3 序列相加", node_type="method"),
                        topic("outline-section-3-1-4", "3.1.4 序列相乘", node_type="method"),
                        topic("outline-section-3-1-5", "3.1.5 成员资格", node_type="method"),
                        topic("outline-section-3-1-6", "3.1.6 序列比较", node_type="formula"),
                        topic("outline-section-3-1-7", "3.1.7 序列排序", node_type="method"),
                    ],
                ),
                topic(
                    "outline-section-3-2",
                    "3.2 列表",
                    children=[
                        topic("outline-section-3-2-1", "3.2.1 列表的创建与删除", node_type="method"),
                        topic("outline-section-3-2-2", "3.2.2 列表元素的访问", node_type="method"),
                        topic("outline-section-3-2-3", "3.2.3 列表元素的删除", node_type="method"),
                        topic("outline-section-3-2-4", "3.2.4 列表元素的添加", node_type="method"),
                        topic("outline-section-3-2-5", "3.2.5 成员资格判断", node_type="method"),
                        topic("outline-section-3-2-6", "3.2.6 列表推导式", node_type="method"),
                        topic("outline-section-3-2-7", "3.2.7 列表排序", node_type="method"),
                    ],
                ),
                topic(
                    "outline-section-3-3",
                    "3.3 元组",
                    children=[
                        topic("outline-section-3-3-1", "3.3.1 元组的创建与删除", node_type="method"),
                        topic("outline-section-3-3-2", "3.3.2 元组的基本操作", node_type="method"),
                        topic("outline-section-3-3-3", "3.3.3 元组与列表的区别"),
                        topic("outline-section-3-3-4", "3.3.4 生成器推导式", node_type="method"),
                    ],
                ),
                topic("outline-section-3-4", "3.4 本章小结"),
            ],
        ),
        topic(
            "outline-chapter-4",
            "第 4 章 字符串与正则表达式",
            summary="掌握字符串常量、转义、格式化、常用方法和正则表达式处理。",
            children=[
                topic(
                    "outline-section-4-1",
                    "4.1 字符串",
                    children=[
                        topic("outline-section-4-1-1", "4.1.1 字符串常量"),
                        topic("outline-section-4-1-2", "4.1.2 字符串的转义符"),
                        topic("outline-section-4-1-3", "4.1.3 字符串的基本操作", node_type="method"),
                        topic("outline-section-4-1-4", "4.1.4 字符串方法", node_type="method"),
                        topic("outline-section-4-1-5", "4.1.5 字符串的格式化", node_type="method"),
                    ],
                ),
                topic(
                    "outline-section-4-2",
                    "4.2 正则表达式",
                    difficulty="intermediate",
                    children=[
                        topic("outline-section-4-2-1", "4.2.1 简单的正则表达式", node_type="formula"),
                        topic("outline-section-4-2-2", "4.2.2 re 模块主要方法", node_type="tool"),
                        topic("outline-section-4-2-3", "4.2.3 使用正则表达式对象", node_type="method"),
                        topic("outline-section-4-2-4", "4.2.4 子模式与 match 对象", node_type="concept"),
                    ],
                ),
                topic("outline-section-4-3", "4.3 本章小结"),
            ],
        ),
        topic(
            "outline-chapter-5",
            "第 5 章 字典和集合",
            summary="学习字典、集合、不可变集合和常见键值/去重场景。",
            children=[
                topic(
                    "outline-section-5-1",
                    "5.1 字典",
                    children=[
                        topic("outline-section-5-1-1", "5.1.1 字典的创建与删除", node_type="method"),
                        topic("outline-section-5-1-2", "5.1.2 字典元素的访问", node_type="method"),
                        topic("outline-section-5-1-3", "5.1.3 字典元素的修改与添加", node_type="method"),
                        topic("outline-section-5-1-4", "5.1.4 有序字典", node_type="concept"),
                    ],
                ),
                topic(
                    "outline-section-5-2",
                    "5.2 集合",
                    children=[
                        topic("outline-section-5-2-1", "5.2.1 集合的创建与删除", node_type="method"),
                        topic("outline-section-5-2-2", "5.2.2 集合操作", node_type="formula"),
                        topic("outline-section-5-2-3", "5.2.3 不可变集合", node_type="concept"),
                    ],
                ),
                topic("outline-section-5-3", "5.3 本章小结"),
                topic("outline-section-5-4", "5.4 上机实验", node_type="case"),
            ],
        ),
        topic(
            "outline-chapter-6",
            "第 6 章 函数与模块",
            summary="通过程序结构、函数、参数、返回值、作用域、模块和包组织可复用代码。",
            children=[
                topic("outline-section-6-1", "6.1 Python 的程序结构"),
                topic(
                    "outline-section-6-2",
                    "6.2 函数",
                    node_type="method",
                    children=[
                        topic("outline-section-6-2-1", "6.2.1 函数的定义", node_type="method"),
                        topic("outline-section-6-2-2", "6.2.2 函数的参数", node_type="method"),
                        topic("outline-section-6-2-3", "6.2.3 函数的返回值", node_type="method"),
                        topic("outline-section-6-2-4", "6.2.4 函数的嵌套", node_type="method"),
                        topic("outline-section-6-2-5", "6.2.5 递归函数", node_type="formula", difficulty="intermediate"),
                        topic("outline-section-6-2-6", "6.2.6 Lambda 函数", node_type="formula", difficulty="intermediate"),
                        topic("outline-section-6-2-7", "6.2.7 变量作用域", difficulty="intermediate"),
                    ],
                ),
                topic(
                    "outline-section-6-3",
                    "6.3 模块",
                    node_type="tool",
                    children=[
                        topic("outline-section-6-3-1", "6.3.1 模块的创建", node_type="tool"),
                        topic("outline-section-6-3-2", "6.3.2 模块的导入", node_type="tool"),
                        topic("outline-section-6-3-3", "6.3.3 模块的属性", node_type="tool"),
                        topic("outline-section-6-3-4", "6.3.4 模块的内置函数", node_type="tool"),
                        topic("outline-section-6-3-5", "6.3.5 自定义包", node_type="tool", difficulty="intermediate"),
                    ],
                ),
                topic("outline-section-6-4", "6.4 本章小结"),
                topic("outline-section-6-5", "6.5 上机实验", node_type="case"),
            ],
        ),
        topic(
            "outline-chapter-7",
            "第 7 章 Python 的控制语句",
            summary="学习输出、赋值、条件、循环和流程控制语句，形成结构化控制能力。",
            children=[
                topic("outline-section-7-1", "7.1 print 语句", node_type="method"),
                topic("outline-section-7-2", "7.2 赋值语句", node_type="method"),
                topic(
                    "outline-section-7-3",
                    "7.3 条件语句",
                    node_type="method",
                    children=[
                        topic("outline-section-7-3-1", "7.3.1 if 语句", node_type="method"),
                        topic("outline-section-7-3-2", "7.3.2 else 子句", node_type="method"),
                        topic("outline-section-7-3-3", "7.3.3 elif 子句", node_type="method"),
                        topic("outline-section-7-3-4", "7.3.4 if 语句的嵌套代码块", node_type="method"),
                        topic("outline-section-7-3-5", "7.3.5 条件语句程序举例", node_type="case"),
                    ],
                ),
                topic(
                    "outline-section-7-4",
                    "7.4 循环语句",
                    node_type="method",
                    children=[
                        topic("outline-section-7-4-1", "7.4.1 while 循环", node_type="method"),
                        topic("outline-section-7-4-2", "7.4.2 for 循环", node_type="method"),
                        topic("outline-section-7-4-3", "7.4.3 Python break 和 continue 语句", node_type="method"),
                        topic("outline-section-7-4-4", "7.4.4 Python 循环嵌套", node_type="method"),
                    ],
                ),
                topic("outline-section-7-5", "7.5 本章小结"),
                topic("outline-section-7-6", "7.6 上机实验", node_type="case"),
            ],
        ),
        topic(
            "outline-chapter-8",
            "第 8 章 文件操作",
            summary="掌握控制台数据输入输出、文件打开关闭、读写、属性和文件管理操作。",
            children=[
                topic(
                    "outline-section-8-1",
                    "8.1 显示和输入数据",
                    node_type="method",
                    children=[
                        topic("outline-section-8-1-1", "8.1.1 显示数据", node_type="method"),
                        topic("outline-section-8-1-2", "8.1.2 输入数据", node_type="method"),
                    ],
                ),
                topic(
                    "outline-section-8-2",
                    "8.2 文件操作",
                    node_type="method",
                    children=[
                        topic("outline-section-8-2-1", "8.2.1 打开文件", node_type="method"),
                        topic("outline-section-8-2-2", "8.2.2 关闭文件", node_type="method"),
                        topic("outline-section-8-2-3", "8.2.3 从文件中读取数据", node_type="method"),
                        topic("outline-section-8-2-4", "8.2.4 向文件中写入数据", node_type="method"),
                        topic("outline-section-8-2-5", "8.2.5 文件属性", node_type="concept"),
                        topic("outline-section-8-2-6", "8.2.6 文件定位", node_type="method"),
                        topic("outline-section-8-2-7", "8.2.7 重命名文件", node_type="method"),
                        topic("outline-section-8-2-8", "8.2.8 删除文件", node_type="method"),
                        topic("outline-section-8-2-9", "8.2.9 移动文件", node_type="method"),
                    ],
                ),
                topic("outline-section-8-3", "8.3 使用 os 模块管理文件和目录", node_type="tool", difficulty="intermediate"),
                topic("outline-section-8-4", "8.4 本章小结"),
                topic("outline-section-8-5", "8.5 上机实验", node_type="case"),
            ],
        ),
        topic(
            "outline-chapter-9",
            "第 9 章 异常处理",
            summary="理解异常类型、捕获策略和带异常处理的文件读写实践。",
            children=[
                topic("outline-section-9-1", "9.1 异常", difficulty="intermediate"),
                topic(
                    "outline-section-9-2",
                    "9.2 捕获异常",
                    node_type="method",
                    difficulty="intermediate",
                    children=[
                        topic("outline-section-9-2-1", "9.2.1 捕获指定异常", node_type="method", difficulty="intermediate"),
                        topic("outline-section-9-2-2", "9.2.2 捕获多种异常", node_type="method", difficulty="intermediate"),
                        topic("outline-section-9-2-3", "9.2.3 捕获所有异常", node_type="method", difficulty="intermediate"),
                    ],
                ),
                topic("outline-section-9-3", "9.3 else 和 finally 子句", node_type="method", difficulty="intermediate"),
                topic("outline-section-9-4", "9.4 本章小结"),
            ],
        ),
    ]


DEFAULT_PYTHON_OUTLINE = _default_python_textbook_outline()


def _default_python_entries() -> list[dict]:
    entries: list[dict] = []
    chunk_order = 1
    order = 1

    def visit(nodes: list[dict], parent_id: str, level: int) -> None:
        nonlocal chunk_order, order
        for node in nodes:
            node_level = int(node.get("level") or level)
            entries.append(
                {
                    "id": node["id"],
                    "name": node["name"],
                    "node_type": node.get("node_type", "concept"),
                    "difficulty": node.get("difficulty", "basic" if node_level <= 2 else "intermediate"),
                    "summary": node["summary"],
                    "source_chunk_ids": [],
                    "confidence": 0.96 if node_level == 1 else 0.94,
                    "level": node_level,
                    "order": order,
                    "parent_id": parent_id,
                    "chunk_order": chunk_order,
                }
            )
            chunk_order += 1
            order += 1
            visit(node.get("children", []), str(node["id"]), node_level + 1)

    visit(DEFAULT_PYTHON_OUTLINE, "course-root", 1)
    return entries


DEFAULT_PYTHON_ENTRIES = _default_python_entries()
DEFAULT_PYTHON_CHUNKS = [
    {
        "node_id": entry["id"],
        "heading": entry["name"],
        "content": entry["summary"],
    }
    for entry in DEFAULT_PYTHON_ENTRIES
]
DEFAULT_PYTHON_CHUNK_ORDER_BY_NODE_ID = {
    str(entry["id"]): int(entry["chunk_order"])
    for entry in DEFAULT_PYTHON_ENTRIES
}
DEFAULT_PYTHON_NODES = [
    {
        "id": "course-root",
        "name": "Python 程序设计",
        "node_type": "concept",
        "difficulty": "basic",
        "summary": "Python 程序设计课程知识结构总览，覆盖教材章节、节、小节和前置学习关系。",
        "source_chunk_ids": [],
        "confidence": 0.98,
        "level": 0,
        "order": 0,
        "parent_id": "",
    },
    *[
        {
            "id": entry["id"],
            "name": entry["name"],
            "node_type": entry["node_type"],
            "difficulty": entry["difficulty"],
            "summary": entry["summary"],
            "source_chunk_ids": [],
            "confidence": entry["confidence"],
            "level": entry["level"],
            "order": entry["order"],
            "parent_id": entry["parent_id"],
        }
        for entry in DEFAULT_PYTHON_ENTRIES
    ],
]

DEFAULT_PYTHON_CONTAINS_EDGES = [
    {
        "id": f"py-contains-{node['parent_id']}-{node['id']}",
        "source_node_id": node["parent_id"],
        "target_node_id": node["id"],
        "relation_type": "contains",
        "reason": "课程结构包含该章节或知识点。",
        "confidence": 0.96,
    }
    for node in DEFAULT_PYTHON_NODES
    if node["id"] != "course-root" and node["parent_id"]
]

def _default_python_prerequisite_edges(nodes: list[dict]) -> list[dict]:
    edges: list[dict] = []

    def visit(siblings: list[dict]) -> None:
        previous_id = ""
        for sibling in siblings:
            current_id = str(sibling["id"])
            if previous_id:
                edges.append(
                    {
                        "id": f"py-prereq-{previous_id}-{current_id}",
                        "source_node_id": previous_id,
                        "target_node_id": current_id,
                        "relation_type": "prerequisite",
                        "reason": "教材目录顺序显示前一知识点通常应先学习。",
                        "confidence": 0.92,
                    }
                )
            visit(sibling.get("children", []))
            previous_id = current_id

    visit(nodes)
    return edges


DEFAULT_PYTHON_PREREQUISITE_EDGES = _default_python_prerequisite_edges(DEFAULT_PYTHON_OUTLINE)

DEFAULT_PYTHON_CROSS_EDGES: list[dict] = []

DEFAULT_PYTHON_EDGES = (
    DEFAULT_PYTHON_CONTAINS_EDGES
    + DEFAULT_PYTHON_PREREQUISITE_EDGES
    + DEFAULT_PYTHON_CROSS_EDGES
)

DEFAULT_C_NODES = [
    {
        "id": "c-course-root",
        "name": "C语言程序设计",
        "node_type": "concept",
        "difficulty": "basic",
        "summary": "C语言程序设计课程知识结构总览，覆盖语法基础、控制结构、函数、数组、指针、结构体和文件操作。",
        "source_chunk_ids": [],
        "confidence": 0.98,
        "level": 0,
        "order": 0,
        "parent_id": "",
    },
    {
        "id": "c-chapter-1",
        "name": "第 1 章 C语言概述",
        "node_type": "chapter",
        "difficulty": "basic",
        "summary": "理解 C 语言的发展、程序结构、编译链接运行流程和基础开发环境。",
        "source_chunk_ids": [],
        "confidence": 0.96,
        "level": 1,
        "order": 1,
        "parent_id": "c-course-root",
    },
    {
        "id": "c-section-1-1",
        "name": "1.1 初识 C 语言",
        "node_type": "knowledge_point",
        "difficulty": "basic",
        "summary": "认识 C 语言的特点、适用场景和第一个 C 程序的基本组成。",
        "source_chunk_ids": [],
        "confidence": 0.94,
        "level": 2,
        "order": 2,
        "parent_id": "c-chapter-1",
    },
    {
        "id": "c-section-1-2",
        "name": "1.2 编译、链接与运行",
        "node_type": "knowledge_point",
        "difficulty": "basic",
        "summary": "理解源文件、目标文件、可执行文件之间的关系，掌握基本编译运行流程。",
        "source_chunk_ids": [],
        "confidence": 0.94,
        "level": 2,
        "order": 3,
        "parent_id": "c-chapter-1",
    },
    {
        "id": "c-chapter-2",
        "name": "第 2 章 数据类型与表达式",
        "node_type": "chapter",
        "difficulty": "basic",
        "summary": "掌握基本数据类型、常量变量、运算符、表达式和类型转换。",
        "source_chunk_ids": [],
        "confidence": 0.96,
        "level": 1,
        "order": 4,
        "parent_id": "c-course-root",
    },
    {
        "id": "c-section-2-1",
        "name": "2.1 基本数据类型",
        "node_type": "knowledge_point",
        "difficulty": "basic",
        "summary": "理解 int、float、double、char 等基本类型的表示范围和使用场景。",
        "source_chunk_ids": [],
        "confidence": 0.94,
        "level": 2,
        "order": 5,
        "parent_id": "c-chapter-2",
    },
    {
        "id": "c-section-2-2",
        "name": "2.2 运算符与表达式",
        "node_type": "knowledge_point",
        "difficulty": "basic",
        "summary": "掌握算术、关系、逻辑、赋值和自增自减运算符，理解优先级与结合性。",
        "source_chunk_ids": [],
        "confidence": 0.94,
        "level": 2,
        "order": 6,
        "parent_id": "c-chapter-2",
    },
    {
        "id": "c-chapter-3",
        "name": "第 3 章 控制结构",
        "node_type": "chapter",
        "difficulty": "basic",
        "summary": "掌握顺序、选择和循环三种基本程序控制结构。",
        "source_chunk_ids": [],
        "confidence": 0.96,
        "level": 1,
        "order": 7,
        "parent_id": "c-course-root",
    },
    {
        "id": "c-section-3-1",
        "name": "3.1 条件分支",
        "node_type": "knowledge_point",
        "difficulty": "basic",
        "summary": "掌握 if、else if、switch 语句的使用和分支条件设计。",
        "source_chunk_ids": [],
        "confidence": 0.94,
        "level": 2,
        "order": 8,
        "parent_id": "c-chapter-3",
    },
    {
        "id": "c-section-3-2",
        "name": "3.2 循环结构",
        "node_type": "knowledge_point",
        "difficulty": "basic",
        "summary": "掌握 for、while、do while 循环，理解循环变量、边界条件和循环退出。",
        "source_chunk_ids": [],
        "confidence": 0.94,
        "level": 2,
        "order": 9,
        "parent_id": "c-chapter-3",
    },
    {
        "id": "c-chapter-4",
        "name": "第 4 章 函数与模块化",
        "node_type": "chapter",
        "difficulty": "intermediate",
        "summary": "理解函数定义、参数传递、返回值、作用域和模块化设计。",
        "source_chunk_ids": [],
        "confidence": 0.96,
        "level": 1,
        "order": 10,
        "parent_id": "c-course-root",
    },
    {
        "id": "c-section-4-1",
        "name": "4.1 函数定义与调用",
        "node_type": "knowledge_point",
        "difficulty": "intermediate",
        "summary": "掌握函数声明、定义、调用、形参实参和返回值。",
        "source_chunk_ids": [],
        "confidence": 0.94,
        "level": 2,
        "order": 11,
        "parent_id": "c-chapter-4",
    },
    {
        "id": "c-section-4-2",
        "name": "4.2 变量作用域与生命周期",
        "node_type": "knowledge_point",
        "difficulty": "intermediate",
        "summary": "理解局部变量、全局变量、静态变量以及变量生命周期。",
        "source_chunk_ids": [],
        "confidence": 0.94,
        "level": 2,
        "order": 12,
        "parent_id": "c-chapter-4",
    },
    {
        "id": "c-chapter-5",
        "name": "第 5 章 数组与字符串",
        "node_type": "chapter",
        "difficulty": "intermediate",
        "summary": "掌握一维数组、二维数组、字符数组和字符串处理。",
        "source_chunk_ids": [],
        "confidence": 0.96,
        "level": 1,
        "order": 13,
        "parent_id": "c-course-root",
    },
    {
        "id": "c-section-5-1",
        "name": "5.1 一维数组与二维数组",
        "node_type": "knowledge_point",
        "difficulty": "intermediate",
        "summary": "理解数组定义、初始化、下标访问、遍历和二维数组存储方式。",
        "source_chunk_ids": [],
        "confidence": 0.94,
        "level": 2,
        "order": 14,
        "parent_id": "c-chapter-5",
    },
    {
        "id": "c-section-5-2",
        "name": "5.2 字符数组与字符串",
        "node_type": "knowledge_point",
        "difficulty": "intermediate",
        "summary": "理解字符串以字符数组和结束符表示，掌握常用字符串处理函数。",
        "source_chunk_ids": [],
        "confidence": 0.94,
        "level": 2,
        "order": 15,
        "parent_id": "c-chapter-5",
    },
    {
        "id": "c-chapter-6",
        "name": "第 6 章 指针",
        "node_type": "chapter",
        "difficulty": "advanced",
        "summary": "掌握地址、指针变量、指针运算、数组指针关系和函数指针基础。",
        "source_chunk_ids": [],
        "confidence": 0.96,
        "level": 1,
        "order": 16,
        "parent_id": "c-course-root",
    },
    {
        "id": "c-section-6-1",
        "name": "6.1 地址与指针变量",
        "node_type": "knowledge_point",
        "difficulty": "advanced",
        "summary": "理解变量地址、取地址运算符、间接访问运算符和指针变量类型。",
        "source_chunk_ids": [],
        "confidence": 0.94,
        "level": 2,
        "order": 17,
        "parent_id": "c-chapter-6",
    },
    {
        "id": "c-section-6-2",
        "name": "6.2 指针与数组",
        "node_type": "knowledge_point",
        "difficulty": "advanced",
        "summary": "理解数组名、首元素地址、指针移动和数组遍历之间的关系。",
        "source_chunk_ids": [],
        "confidence": 0.94,
        "level": 2,
        "order": 18,
        "parent_id": "c-chapter-6",
    },
    {
        "id": "c-chapter-7",
        "name": "第 7 章 结构体与文件",
        "node_type": "chapter",
        "difficulty": "advanced",
        "summary": "掌握结构体组织复杂数据，理解文件读写和课程综合实践。",
        "source_chunk_ids": [],
        "confidence": 0.96,
        "level": 1,
        "order": 19,
        "parent_id": "c-course-root",
    },
    {
        "id": "c-section-7-1",
        "name": "7.1 结构体",
        "node_type": "knowledge_point",
        "difficulty": "advanced",
        "summary": "理解结构体定义、成员访问、结构体数组和结构体指针。",
        "source_chunk_ids": [],
        "confidence": 0.94,
        "level": 2,
        "order": 20,
        "parent_id": "c-chapter-7",
    },
    {
        "id": "c-section-7-2",
        "name": "7.2 文件读写",
        "node_type": "knowledge_point",
        "difficulty": "advanced",
        "summary": "掌握文件打开、读写、关闭和错误处理，理解文本文件与二进制文件差异。",
        "source_chunk_ids": [],
        "confidence": 0.94,
        "level": 2,
        "order": 21,
        "parent_id": "c-chapter-7",
    },
]

DEFAULT_C_CHUNKS = [
    {
        "node_id": node["id"],
        "heading": node["name"],
        "content": node["summary"],
    }
    for node in DEFAULT_C_NODES
    if node["id"] != "c-course-root"
]
DEFAULT_C_CHUNK_ORDER_BY_NODE_ID = {
    str(chunk["node_id"]): index + 1
    for index, chunk in enumerate(DEFAULT_C_CHUNKS)
}
DEFAULT_C_CONTAINS_EDGES = [
    {
        "id": f"c-contains-{node['parent_id']}-{node['id']}",
        "source_node_id": node["parent_id"],
        "target_node_id": node["id"],
        "relation_type": "contains",
        "reason": "课程结构包含该章节或知识点。",
        "confidence": 0.96,
    }
    for node in DEFAULT_C_NODES
    if node["id"] != "c-course-root" and node["parent_id"]
]
DEFAULT_C_PREREQUISITE_EDGES = [
    {
        "id": f"c-prereq-{left['id']}-{right['id']}",
        "source_node_id": left["id"],
        "target_node_id": right["id"],
        "relation_type": "prerequisite",
        "reason": "教材目录顺序显示前一知识点通常应先学习。",
        "confidence": 0.9,
    }
    for left, right in zip(DEFAULT_C_NODES[1:], DEFAULT_C_NODES[2:])
    if int(left["level"]) >= 1 and int(right["level"]) >= 1
]
DEFAULT_C_EDGES = DEFAULT_C_CONTAINS_EDGES + DEFAULT_C_PREREQUISITE_EDGES


class CourseService:
    supported_file_types = {"pdf", "ppt", "pptx"}
    parser = staticmethod(parse_material)
    chunker = staticmethod(chunk_pages)
    vector_service_cls = MilvusVectorService
    graph_store_cls = Neo4jGraphStore
    knowledge_graph_agent_cls = KnowledgeGraphAgent

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_course(self, user_id: int, payload: CourseCreate) -> Course:
        course = Course(
            user_id=user_id,
            name=payload.name,
            major=payload.major,
            level=payload.level,
            description=payload.description,
        )
        self.db.add(course)
        self.db.commit()
        self.db.refresh(course)
        return course

    def list_courses(self, user_id: int) -> list[Course]:
        return list(
            self.db.scalars(
                select(Course)
                .where(Course.user_id == user_id)
                .order_by(Course.created_at.asc(), Course.id.asc())
            )
        )

    def get_course(self, user_id: int, course_id: int) -> Course:
        course = self.db.scalar(
            select(Course).where(Course.id == course_id, Course.user_id == user_id)
        )
        if course is None:
            raise CourseNotFoundError("course not found")
        return course

    def ensure_default_python_course(self, user_id: int) -> Course:
        course = self.db.scalar(
            select(Course).where(
                Course.user_id == user_id,
                Course.name == DEFAULT_PYTHON_COURSE_NAME,
                Course.description.contains(DEFAULT_PYTHON_MARKER),
            )
        )
        if course is None:
            course = Course(
                user_id=user_id,
                name=DEFAULT_PYTHON_COURSE_NAME,
                major="计算机科学",
                level="本科",
                description=f"{DEFAULT_PYTHON_MARKER} 内置 Python 示例课程知识库，用于稳定演示知识图谱与多智能体学习流程。",
                status="ready",
            )
            self.db.add(course)
            self.db.flush()
        else:
            course.description = self._without_marker(course.description, DEFAULT_PYTHON_MATERIAL_DELETED_MARKER)

        self._sync_default_python_course(user_id, course)
        self.db.refresh(course)
        return course

    def ensure_default_c_course(self, user_id: int) -> Course:
        course = self.db.scalar(
            select(Course).where(
                Course.user_id == user_id,
                Course.name == DEFAULT_C_COURSE_NAME,
                Course.description.contains(DEFAULT_C_MARKER),
            )
        )
        if course is None:
            course = Course(
                user_id=user_id,
                name=DEFAULT_C_COURSE_NAME,
                major="计算机科学",
                level="本科",
                description=f"{DEFAULT_C_MARKER} 内置 C 语言示例课程知识库，用于多课程隔离演示。",
                status="ready",
            )
            self.db.add(course)
            self.db.flush()
        else:
            course.description = self._without_marker(course.description, DEFAULT_C_MATERIAL_DELETED_MARKER)

        self._sync_default_c_course(user_id, course)
        self.db.refresh(course)
        return course

    def apply_builtin_knowledge_base(self, user_id: int, course_id: int, template: str) -> Course:
        course = self.get_course(user_id, course_id)
        normalized_template = template.strip().lower()
        if normalized_template == "python":
            self._delete_builtin_material_for_course(course, DEFAULT_C_MATERIAL_STORAGE_PATH)
            course.description = self._with_marker(
                self._without_marker(
                    self._without_marker(course.description, DEFAULT_C_MARKER),
                    DEFAULT_C_MATERIAL_DELETED_MARKER,
                ),
                DEFAULT_PYTHON_MARKER,
            )
            course.description = self._without_marker(course.description, DEFAULT_PYTHON_MATERIAL_DELETED_MARKER)
            course.status = "ready"
            self._sync_default_python_course(user_id, course)
        elif normalized_template == "c":
            self._delete_builtin_material_for_course(course, DEFAULT_PYTHON_MATERIAL_STORAGE_PATH)
            course.description = self._with_marker(
                self._without_marker(
                    self._without_marker(course.description, DEFAULT_PYTHON_MARKER),
                    DEFAULT_PYTHON_MATERIAL_DELETED_MARKER,
                ),
                DEFAULT_C_MARKER,
            )
            course.description = self._without_marker(course.description, DEFAULT_C_MATERIAL_DELETED_MARKER)
            course.status = "ready"
            self._sync_default_c_course(user_id, course)
        else:
            raise ValueError("unsupported built-in knowledge base template")

        self.db.refresh(course)
        return course

    def _delete_builtin_material_for_course(self, course: Course, storage_path: str) -> None:
        material = self.db.scalar(
            select(CourseMaterial).where(
                CourseMaterial.course_id == course.id,
                CourseMaterial.user_id == course.user_id,
                CourseMaterial.storage_path == storage_path,
            )
        )
        if material is None:
            return
        self.db.execute(
            delete(KnowledgeChunk).where(
                KnowledgeChunk.course_id == course.id,
                KnowledgeChunk.material_id == material.id,
            )
        )
        self.db.delete(material)
        self.db.flush()

    async def add_material_from_upload(
        self,
        user_id: int,
        course_id: int,
        file: UploadFile,
    ) -> CourseMaterial:
        content = await file.read()
        return self.add_material(
            user_id=user_id,
            course_id=course_id,
            filename=file.filename or "",
            content=content,
        )

    def add_material(
        self,
        user_id: int,
        course_id: int,
        filename: str,
        content: bytes,
    ) -> CourseMaterial:
        course = self.get_course(user_id, course_id)
        file_type = self._file_type(filename)
        if file_type not in self.supported_file_types:
            raise UnsupportedMaterialTypeError(f"unsupported file type: {file_type or 'unknown'}")

        max_bytes = settings.max_upload_size_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise ValueError(f"file exceeds {settings.max_upload_size_mb} MB upload limit")

        self._detach_builtin_knowledge_base_for_custom_upload(course)
        original_filename = self._truncate(filename or f"upload.{file_type}", 255)
        storage_path = self._save_upload(user_id, course_id, original_filename, content)
        material = CourseMaterial(
            course_id=course_id,
            user_id=user_id,
            filename=original_filename,
            file_type=file_type,
            storage_path=storage_path,
            size_bytes=len(content),
            parse_status="queued",
        )
        self.db.add(material)
        self.db.commit()
        self.db.refresh(material)

        return material

    def _detach_builtin_knowledge_base_for_custom_upload(self, course: Course) -> None:
        had_builtin_marker = DEFAULT_PYTHON_MARKER in course.description or DEFAULT_C_MARKER in course.description
        if not had_builtin_marker:
            return

        self._delete_builtin_material_for_course(course, DEFAULT_PYTHON_MATERIAL_STORAGE_PATH)
        self._delete_builtin_material_for_course(course, DEFAULT_C_MATERIAL_STORAGE_PATH)
        course.description = self._without_marker(course.description, DEFAULT_PYTHON_MARKER)
        course.description = self._without_marker(course.description, DEFAULT_C_MARKER)
        course.description = self._without_marker(course.description, DEFAULT_PYTHON_MATERIAL_DELETED_MARKER)
        course.description = self._without_marker(course.description, DEFAULT_C_MATERIAL_DELETED_MARKER)
        self.db.execute(delete(GraphBuildJob).where(GraphBuildJob.course_id == course.id))
        self._delete_course_graph(course.user_id, course.id)
        self.db.flush()

    def process_material_by_id(self, user_id: int, course_id: int, material_id: int) -> None:
        material = self.db.scalar(
            select(CourseMaterial).where(
                CourseMaterial.id == material_id,
                CourseMaterial.course_id == course_id,
                CourseMaterial.user_id == user_id,
            )
        )
        if material is None:
            return

        material.parse_status = "processing"
        material.parse_error = ""
        self.db.commit()
        self.db.refresh(material)

        chunk_models: list[KnowledgeChunk] = []

        try:
            self._validate_material_parser_configuration()
            if settings.mineru_enabled and settings.mineru_api_token:
                material.parse_status = "mineru_submitted"
                self.db.commit()
                material.parse_status = "mineru_polling"
                self.db.commit()
            elif material.file_type == "pdf":
                material.parse_status = "ocr_running"
                self.db.commit()
            pages = self.parser(material.storage_path, material.file_type, settings.ocr_lang, -1)
            material.parse_status = "chunking"
            self.db.commit()
            chunks = self.chunker(pages)
            self.db.execute(
                delete(KnowledgeChunk).where(
                    KnowledgeChunk.course_id == course_id,
                    KnowledgeChunk.material_id == material.id,
                )
            )
            chunk_models = [
                KnowledgeChunk(
                    course_id=course_id,
                    material_id=material.id,
                    chunk_index=chunk.chunk_index,
                    source_locator=chunk.source_locator,
                    heading=self._truncate(chunk.heading, 255),
                    content=chunk.content,
                    token_count=chunk.token_count,
                )
                for chunk in chunks
            ]
            self.db.add_all(chunk_models)
            self.db.flush()

            for chunk_model in chunk_models:
                chunk_model.embedding_id = f"chunk-{chunk_model.id}"

            material.parse_status = "indexing"
            material.ocr_used = any(page.ocr_used for page in pages)
            material.parse_error = ""
            self.db.commit()
            self.db.refresh(material)
        except Exception as exc:
            material.parse_status = "failed"
            material.parse_error = str(exc)
            self.db.commit()
            return

        try:
            vector_service = self.vector_service_cls()
            try:
                vector_service.upsert_chunks(
                    course_id,
                    [self._chunk_payload(chunk_model) for chunk_model in chunk_models],
                )
            finally:
                self._close_vector_service(vector_service)
        except Exception as exc:
            material.parse_status = "index_failed"
            material.parse_error = str(exc)
            self.db.commit()
            return

        material.parse_status = "parsed"
        material.parse_error = ""
        self.db.commit()

    def list_chunks(self, user_id: int, course_id: int) -> list[KnowledgeChunk]:
        course = self.get_course(user_id, course_id)
        if self._is_default_python_course(course):
            self._sync_default_python_course(user_id, course)
        elif self._is_default_c_course(course):
            self._sync_default_c_course(user_id, course)
        return list(
            self.db.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.course_id == course_id)
                .order_by(KnowledgeChunk.material_id.asc(), KnowledgeChunk.chunk_index.asc(), KnowledgeChunk.id.asc())
            )
        )

    def list_materials(self, user_id: int, course_id: int) -> list[CourseMaterial]:
        self.get_course(user_id, course_id)
        return list(
            self.db.scalars(
                select(CourseMaterial)
                .where(CourseMaterial.course_id == course_id, CourseMaterial.user_id == user_id)
                .order_by(CourseMaterial.created_at.desc(), CourseMaterial.id.desc())
            )
        )

    def delete_material(self, user_id: int, course_id: int, material_id: int) -> None:
        self.get_course(user_id, course_id)
        material = self.db.scalar(
            select(CourseMaterial).where(
                CourseMaterial.id == material_id,
                CourseMaterial.course_id == course_id,
                CourseMaterial.user_id == user_id,
            )
        )
        if material is None:
            raise MaterialNotFoundError("material not found")
        storage_path = material.storage_path
        course = self.get_course(user_id, course_id)

        chunks = list(
            self.db.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.course_id == course_id, KnowledgeChunk.material_id == material_id)
                .order_by(KnowledgeChunk.id.asc())
            )
        )
        chunk_ids = [chunk.id for chunk in chunks]

        if chunk_ids:
            try:
                vector_service = self.vector_service_cls()
                try:
                    vector_service.delete_chunks(course_id, chunk_ids)
                finally:
                    self._close_vector_service(vector_service)
            except Exception as exc:
                logger.warning(
                    "vector chunk cleanup failed; continuing material deletion",
                    extra={"course_id": course_id, "material_id": material_id, "error": str(exc)},
                )

        self.db.execute(
            delete(KnowledgeChunk).where(
                KnowledgeChunk.course_id == course_id,
                KnowledgeChunk.material_id == material_id,
            )
        )
        self.db.execute(delete(GraphBuildJob).where(GraphBuildJob.course_id == course_id))
        self._delete_course_graph(user_id, course_id)
        self._mark_default_material_deleted(course, storage_path)
        self.db.delete(material)
        self.db.commit()
        self._delete_upload_file(storage_path)

    def semantic_search(self, user_id: int, course_id: int, query: str) -> list[dict]:
        self.get_course(user_id, course_id)
        try:
            vector_service = self.vector_service_cls()
            try:
                return vector_service.search(course_id=course_id, query=query)
            finally:
                self._close_vector_service(vector_service)
        except Exception as exc:
            logger.warning(
                "vector semantic search failed; falling back to mysql chunks",
                extra={"course_id": course_id, "query": query, "error": str(exc)},
            )
            return self._fallback_semantic_search(course_id, query)

    def rebuild_vector_index(self, user_id: int, course_id: int) -> dict:
        chunks = self.list_chunks(user_id, course_id)
        self.db.query(CourseMaterial).filter(
            CourseMaterial.course_id == course_id,
            CourseMaterial.user_id == user_id,
            CourseMaterial.parse_status.in_(["index_failed", "indexing"]),
        ).update(
            {"parse_status": "indexing", "parse_error": ""},
            synchronize_session=False,
        )
        self.db.commit()
        try:
            vector_service = self.vector_service_cls()
            try:
                vector_service.upsert_chunks(
                    course_id,
                    [self._chunk_payload(chunk) for chunk in chunks],
                    skip_existing=True,
                )
            finally:
                self._close_vector_service(vector_service)
        except Exception as exc:
            self.db.query(CourseMaterial).filter(
                CourseMaterial.course_id == course_id,
                CourseMaterial.user_id == user_id,
                CourseMaterial.parse_status == "indexing",
            ).update(
                {"parse_status": "index_failed", "parse_error": str(exc)},
                synchronize_session=False,
            )
            self.db.commit()
            raise

        self.db.query(CourseMaterial).filter(
            CourseMaterial.course_id == course_id,
            CourseMaterial.user_id == user_id,
            CourseMaterial.parse_status == "indexing",
        ).update(
            {"parse_status": "parsed", "parse_error": ""},
            synchronize_session=False,
        )
        self.db.commit()
        return {"course_id": course_id, "indexed_chunks": len(chunks)}

    async def build_knowledge_graph(self, user_id: int, course_id: int) -> dict:
        course = self.get_course(user_id, course_id)
        chunk_payloads = [self._chunk_payload(chunk) for chunk in self.list_chunks(user_id, course_id)]
        job = GraphBuildJob(course_id=course_id, status="running", current_stage="extract", progress=10)
        self.db.add(job)
        self.db.flush()

        try:
            graph = await self.knowledge_graph_agent_cls().build_graph_async(chunk_payloads)
            graph = self._normalize_course_graph_root(course, graph)
            graph_store = self.graph_store_cls()
            try:
                graph_store.replace_course_graph(
                    user_id=user_id,
                    course_id=course_id,
                    nodes=graph.get("nodes", []),
                    edges=graph.get("edges", []),
                )
            finally:
                graph_store.close()
            job.status = "succeeded"
            job.current_stage = "done"
            job.progress = 100
            job.error_message = ""
            self.db.commit()
            return self._attach_mastery(user_id, course_id, graph)
        except Exception as exc:
            job.status = "failed"
            job.current_stage = "error"
            job.error_message = str(exc)
            self.db.commit()
            raise

    def get_knowledge_graph(self, user_id: int, course_id: int) -> dict:
        course = self.get_course(user_id, course_id)
        if self._is_default_python_course(course):
            self._sync_default_python_course(user_id, course)
        elif self._is_default_c_course(course):
            self._sync_default_c_course(user_id, course)
        if not self._has_successful_graph_build(course_id):
            return {"nodes": [], "edges": []}

        graph_store = self.graph_store_cls()
        try:
            graph = graph_store.get_course_graph(user_id=user_id, course_id=course_id)
        finally:
            graph_store.close()
        graph = self._repair_graph_outline_from_chunks(user_id, course_id, graph)
        graph = self._normalize_course_graph_root(course, graph)
        return self._attach_mastery(user_id, course_id, graph)

    def upsert_node_mastery(
        self,
        user_id: int,
        course_id: int,
        node_id: str,
        topic: str,
        score: float | None,
        detail: str = "",
    ) -> KnowledgeNodeMastery:
        self.get_course(user_id, course_id)
        mastery = self.db.scalar(
            select(KnowledgeNodeMastery).where(
                KnowledgeNodeMastery.user_id == user_id,
                KnowledgeNodeMastery.course_id == course_id,
                KnowledgeNodeMastery.node_id == node_id,
            )
        )
        if mastery is None:
            mastery = KnowledgeNodeMastery(
                user_id=user_id,
                course_id=course_id,
                node_id=self._truncate(node_id, 255),
            )
            self.db.add(mastery)

        mastery.topic = self._truncate(topic, 255)
        mastery.mastery_score = score
        mastery.mastery_status = self._mastery_status(score)
        mastery.detail = detail
        self.db.commit()
        self.db.refresh(mastery)
        return mastery

    def _has_successful_graph_build(self, course_id: int) -> bool:
        return (
            self.db.scalar(
                select(GraphBuildJob.id)
                .where(GraphBuildJob.course_id == course_id, GraphBuildJob.status == "succeeded")
                .limit(1)
            )
            is not None
        )

    def _ensure_default_python_material(self, course: Course) -> CourseMaterial:
        size_bytes = sum(len(chunk["content"].encode("utf-8")) for chunk in DEFAULT_PYTHON_CHUNKS)
        material = self.db.scalar(
            select(CourseMaterial).where(
                CourseMaterial.course_id == course.id,
                CourseMaterial.user_id == course.user_id,
                CourseMaterial.storage_path == DEFAULT_PYTHON_MATERIAL_STORAGE_PATH,
            )
        )
        if material is not None:
            material.filename = DEFAULT_PYTHON_MATERIAL_FILENAME
            material.file_type = "builtin"
            material.size_bytes = size_bytes
            material.parse_status = "parsed"
            material.parse_error = ""
            material.ocr_used = False
            return material

        material = CourseMaterial(
            course_id=course.id,
            user_id=course.user_id,
            filename=DEFAULT_PYTHON_MATERIAL_FILENAME,
            file_type="builtin",
            storage_path=DEFAULT_PYTHON_MATERIAL_STORAGE_PATH,
            size_bytes=size_bytes,
            parse_status="parsed",
            parse_error="",
            ocr_used=False,
        )
        self.db.add(material)
        self.db.flush()
        return material

    def _ensure_default_c_material(self, course: Course) -> CourseMaterial:
        size_bytes = sum(len(chunk["content"].encode("utf-8")) for chunk in DEFAULT_C_CHUNKS)
        material = self.db.scalar(
            select(CourseMaterial).where(
                CourseMaterial.course_id == course.id,
                CourseMaterial.user_id == course.user_id,
                CourseMaterial.storage_path == DEFAULT_C_MATERIAL_STORAGE_PATH,
            )
        )
        if material is not None:
            material.filename = DEFAULT_C_MATERIAL_FILENAME
            material.file_type = "builtin"
            material.size_bytes = size_bytes
            material.parse_status = "parsed"
            material.parse_error = ""
            material.ocr_used = False
            return material

        material = CourseMaterial(
            course_id=course.id,
            user_id=course.user_id,
            filename=DEFAULT_C_MATERIAL_FILENAME,
            file_type="builtin",
            storage_path=DEFAULT_C_MATERIAL_STORAGE_PATH,
            size_bytes=size_bytes,
            parse_status="parsed",
            parse_error="",
            ocr_used=False,
        )
        self.db.add(material)
        self.db.flush()
        return material

    def _ensure_default_python_chunks(self, course: Course, material: CourseMaterial) -> None:
        existing_chunks = list(
            self.db.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.course_id == course.id, KnowledgeChunk.material_id == material.id)
                .order_by(KnowledgeChunk.chunk_index.asc(), KnowledgeChunk.id.asc())
            )
        )
        if len(existing_chunks) == len(DEFAULT_PYTHON_CHUNKS):
            return

        if existing_chunks:
            self.db.execute(
                delete(KnowledgeChunk)
                .where(KnowledgeChunk.course_id == course.id, KnowledgeChunk.material_id == material.id)
            )
            self.db.flush()

        chunks = [
            KnowledgeChunk(
                course_id=course.id,
                material_id=material.id,
                chunk_index=index,
                source_locator=f"built-in-python:{index + 1}:{chunk['node_id']}",
                heading=self._truncate(chunk["heading"], 255),
                content=chunk["content"],
                token_count=len(chunk["content"]),
                embedding_id=f"default-python-{course.id}-{index + 1}",
            )
            for index, chunk in enumerate(DEFAULT_PYTHON_CHUNKS)
        ]
        self.db.add_all(chunks)
        self.db.flush()

    def _ensure_default_c_chunks(self, course: Course, material: CourseMaterial) -> None:
        existing_chunks = list(
            self.db.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.course_id == course.id, KnowledgeChunk.material_id == material.id)
                .order_by(KnowledgeChunk.chunk_index.asc(), KnowledgeChunk.id.asc())
            )
        )
        if len(existing_chunks) == len(DEFAULT_C_CHUNKS):
            return

        if existing_chunks:
            self.db.execute(
                delete(KnowledgeChunk)
                .where(KnowledgeChunk.course_id == course.id, KnowledgeChunk.material_id == material.id)
            )
            self.db.flush()

        chunks = [
            KnowledgeChunk(
                course_id=course.id,
                material_id=material.id,
                chunk_index=index,
                source_locator=f"built-in-c:{index + 1}:{chunk['node_id']}",
                heading=self._truncate(chunk["heading"], 255),
                content=chunk["content"],
                token_count=len(chunk["content"]),
                embedding_id=f"default-c-{course.id}-{index + 1}",
            )
            for index, chunk in enumerate(DEFAULT_C_CHUNKS)
        ]
        self.db.add_all(chunks)
        self.db.flush()

    def _ensure_default_python_graph(self, user_id: int, course_id: int, material_id: int) -> None:
        chunk_ids_by_order = {
            chunk.chunk_index + 1: chunk.id
            for chunk in self.db.scalars(
                select(KnowledgeChunk).where(
                    KnowledgeChunk.course_id == course_id,
                    KnowledgeChunk.material_id == material_id,
                )
            )
        }
        nodes = []
        for node in DEFAULT_PYTHON_NODES:
            next_node = dict(node)
            chunk_order = DEFAULT_PYTHON_CHUNK_ORDER_BY_NODE_ID.get(str(next_node["id"]))
            chunk_id = chunk_ids_by_order.get(chunk_order or 0)
            next_node["source_chunk_ids"] = [str(chunk_id)] if chunk_id else []
            nodes.append(next_node)

        graph_store = self.graph_store_cls()
        try:
            graph_store.replace_course_graph(
                user_id=user_id,
                course_id=course_id,
                nodes=nodes,
                edges=DEFAULT_PYTHON_EDGES,
            )
        finally:
            graph_store.close()

        if not self._has_successful_graph_build(course_id):
            self.db.add(
                GraphBuildJob(
                    course_id=course_id,
                    status="succeeded",
                    current_stage="done",
                    progress=100,
                    error_message="",
                )
            )

    def _ensure_default_c_graph(self, user_id: int, course_id: int, material_id: int) -> None:
        chunk_ids_by_order = {
            chunk.chunk_index + 1: chunk.id
            for chunk in self.db.scalars(
                select(KnowledgeChunk).where(
                    KnowledgeChunk.course_id == course_id,
                    KnowledgeChunk.material_id == material_id,
                )
            )
        }
        nodes = []
        for node in DEFAULT_C_NODES:
            next_node = dict(node)
            chunk_order = DEFAULT_C_CHUNK_ORDER_BY_NODE_ID.get(str(next_node["id"]))
            chunk_id = chunk_ids_by_order.get(chunk_order or 0)
            next_node["source_chunk_ids"] = [str(chunk_id)] if chunk_id else []
            nodes.append(next_node)

        graph_store = self.graph_store_cls()
        try:
            graph_store.replace_course_graph(
                user_id=user_id,
                course_id=course_id,
                nodes=nodes,
                edges=DEFAULT_C_EDGES,
            )
        finally:
            graph_store.close()

        if not self._has_successful_graph_build(course_id):
            self.db.add(
                GraphBuildJob(
                    course_id=course_id,
                    status="succeeded",
                    current_stage="done",
                    progress=100,
                    error_message="",
                )
            )

    def _attach_mastery(self, user_id: int, course_id: int, graph: dict) -> dict:
        masteries = {
            mastery.node_id: mastery
            for mastery in self.db.scalars(
                select(KnowledgeNodeMastery).where(
                    KnowledgeNodeMastery.user_id == user_id,
                    KnowledgeNodeMastery.course_id == course_id,
                )
            )
        }
        nodes = []
        for node in graph.get("nodes", []):
            next_node = dict(node)
            node_id = str(next_node.get("id", ""))
            mastery = masteries.get(node_id)
            if mastery is None:
                next_node.setdefault("mastery_status", "not_started")
            else:
                next_node["mastery_status"] = mastery.mastery_status
                if mastery.mastery_score is not None:
                    next_node["mastery_score"] = mastery.mastery_score
                if mastery.detail:
                    next_node["mastery_detail"] = mastery.detail
            nodes.append(next_node)
        return {"nodes": nodes, "edges": graph.get("edges", [])}

    def _normalize_course_graph_root(self, course: Course, graph: dict) -> dict:
        nodes = [dict(node) for node in graph.get("nodes", [])]
        if not nodes:
            return {"nodes": nodes, "edges": graph.get("edges", [])}

        root = self._find_course_root_node(nodes)
        if root is not None:
            previous_name = str(root.get("name") or "")
            root["name"] = course.name
            summary = str(root.get("summary") or "")
            if not summary or (previous_name and previous_name in summary):
                root["summary"] = f"{course.name}\u7684\u8bfe\u7a0b\u77e5\u8bc6\u7ed3\u6784\u603b\u89c8\u3002"
            nodes = [root, *[node for node in nodes if node is not root]]
        return {"nodes": nodes, "edges": graph.get("edges", [])}

    def _repair_graph_outline_from_chunks(self, user_id: int, course_id: int, graph: dict) -> dict:
        course = self.get_course(user_id, course_id)
        if self._is_default_python_course(course) or self._is_default_c_course(course):
            return graph

        existing_node_ids = {str(node.get("id")) for node in graph.get("nodes", []) if node.get("id") is not None}

        chunks = list(
            self.db.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.course_id == course_id)
                .order_by(KnowledgeChunk.material_id.asc(), KnowledgeChunk.chunk_index.asc(), KnowledgeChunk.id.asc())
            )
        )
        if not chunks:
            return graph

        agent = KnowledgeGraphAgent(mock=True)
        outline_graph = agent._build_outline_graph([self._chunk_payload(chunk) for chunk in chunks])
        outline_node_ids = {
            str(node.get("id"))
            for node in outline_graph.get("nodes", [])
            if node.get("id") is not None
        }
        if not outline_node_ids - existing_node_ids:
            return graph

        if not existing_node_ids:
            repaired = outline_graph
            graph_store = self.graph_store_cls()
            try:
                graph_store.replace_course_graph(
                    user_id=user_id,
                    course_id=course_id,
                    nodes=repaired.get("nodes", []),
                    edges=repaired.get("edges", []),
                )
            finally:
                graph_store.close()
            return repaired

        merge = getattr(agent, "_merge_outline_and_semantic_graphs", None)
        if not callable(merge):
            return graph

        repaired = merge(outline_graph, graph)
        graph_store = self.graph_store_cls()
        try:
            graph_store.replace_course_graph(
                user_id=user_id,
                course_id=course_id,
                nodes=repaired.get("nodes", []),
                edges=repaired.get("edges", []),
            )
        finally:
            graph_store.close()
        return repaired

    def _find_course_root_node(self, nodes: list[dict]) -> dict | None:
        preferred_root_ids = {"course-root", "c-course-root", "py-course-root"}
        for node in nodes:
            if str(node.get("id", "")) in preferred_root_ids:
                return node
        for node in nodes:
            if self._is_root_graph_node(node):
                return node
        return None

    def _is_root_graph_node(self, node: dict) -> bool:
        if "parent_id" in node and str(node.get("parent_id") or "") == "":
            return True
        if "level" not in node:
            return False
        try:
            return int(node.get("level", -1)) == 0
        except (TypeError, ValueError):
            return False

    def _mastery_status(self, score: float | None) -> str:
        if score is None:
            return "not_started"
        if score < 0.6:
            return "severe_weak"
        if score < 0.75:
            return "basic"
        if score < 0.9:
            return "good"
        return "proficient"

    def _is_default_python_course(self, course: Course) -> bool:
        return course.name == DEFAULT_PYTHON_COURSE_NAME and DEFAULT_PYTHON_MARKER in course.description

    def _is_default_c_course(self, course: Course) -> bool:
        return course.name == DEFAULT_C_COURSE_NAME and DEFAULT_C_MARKER in course.description

    def _sync_default_python_course(self, user_id: int, course: Course) -> None:
        if DEFAULT_PYTHON_MATERIAL_DELETED_MARKER in course.description:
            return
        material = self._ensure_default_python_material(course)
        self._ensure_default_python_chunks(course, material)
        self._ensure_default_python_graph(user_id, course.id, material.id)
        self.db.commit()

    def _sync_default_c_course(self, user_id: int, course: Course) -> None:
        if DEFAULT_C_MATERIAL_DELETED_MARKER in course.description:
            return
        material = self._ensure_default_c_material(course)
        self._ensure_default_c_chunks(course, material)
        self._ensure_default_c_graph(user_id, course.id, material.id)
        self.db.commit()

    def _mark_default_material_deleted(self, course: Course, storage_path: str) -> None:
        if storage_path == DEFAULT_PYTHON_MATERIAL_STORAGE_PATH:
            course.description = self._with_marker(course.description, DEFAULT_PYTHON_MATERIAL_DELETED_MARKER)
        elif storage_path == DEFAULT_C_MATERIAL_STORAGE_PATH:
            course.description = self._with_marker(course.description, DEFAULT_C_MATERIAL_DELETED_MARKER)

    def _with_marker(self, value: str, marker: str) -> str:
        description = value or ""
        if marker in description:
            return description
        return f"{description} {marker}".strip()

    def _without_marker(self, value: str, marker: str) -> str:
        return " ".join(part for part in (value or "").split() if part != marker)

    def _file_type(self, filename: str) -> str:
        return Path(filename).suffix.lower().lstrip(".")

    def _save_upload(self, user_id: int, course_id: int, filename: str, content: bytes) -> str:
        upload_dir = course_upload_dir(settings.upload_dir, user_id, course_id)
        storage_path = upload_dir / self._storage_filename(filename)
        storage_path.write_bytes(content)
        return str(storage_path)

    def _delete_upload_file(self, storage_path: str) -> None:
        try:
            Path(storage_path).unlink(missing_ok=True)
        except OSError:
            pass

    def _delete_course_graph(self, user_id: int, course_id: int) -> None:
        graph_store = None
        try:
            graph_store = self.graph_store_cls()
            delete_graph = getattr(graph_store, "delete_course_graph", None)
            if delete_graph is not None:
                delete_graph(user_id=user_id, course_id=course_id)
            else:
                graph_store.replace_course_graph(user_id=user_id, course_id=course_id, nodes=[], edges=[])
        except Exception as exc:
            logger.warning(
                "graph cleanup failed; continuing material deletion",
                extra={"user_id": user_id, "course_id": course_id, "error": str(exc)},
            )
        finally:
            if graph_store is not None:
                graph_store.close()

    def _truncate(self, value: str, max_length: int) -> str:
        return (value or "")[:max_length]

    def _storage_filename(self, filename: str) -> str:
        safe_name = safe_upload_name(filename)
        suffix = Path(safe_name).suffix
        max_safe_name_length = 120
        stem_limit = max_safe_name_length - len(suffix)
        if stem_limit <= 0:
            stem_limit = max_safe_name_length
            suffix = ""
        truncated_safe_name = f"{Path(safe_name).stem[:stem_limit]}{suffix}"
        return f"{uuid4().hex}_{truncated_safe_name}"

    def _validate_material_parser_configuration(self) -> None:
        if settings.mineru_enabled and not settings.mineru_api_token:
            raise MaterialParseError("MINERU_API_TOKEN is required when MINERU_ENABLED=true")

    def _chunk_payload(self, chunk: KnowledgeChunk) -> dict:
        return {
            "id": chunk.id,
            "course_id": chunk.course_id,
            "material_id": chunk.material_id,
            "chunk_index": chunk.chunk_index,
            "source_locator": chunk.source_locator,
            "heading": chunk.heading,
            "content": chunk.content,
            "token_count": chunk.token_count,
            "embedding_id": chunk.embedding_id,
        }

    def _close_vector_service(self, vector_service: object) -> None:
        close = getattr(vector_service, "close", None)
        if close is None:
            return
        close()

    def _fallback_semantic_search(self, course_id: int, query: str, limit: int = 5) -> list[dict]:
        chunks = list(
            self.db.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.course_id == course_id)
                .order_by(KnowledgeChunk.chunk_index.asc(), KnowledgeChunk.id.asc())
            )
        )
        normalized_query = query.strip().lower()
        terms = [term for term in normalized_query.replace("，", " ").replace(",", " ").split() if term]
        if not terms and normalized_query:
            terms = [normalized_query]

        def score(chunk: KnowledgeChunk) -> tuple[int, int, int]:
            haystack = f"{chunk.heading}\n{chunk.content}".lower()
            matched_terms = sum(1 for term in terms if term in haystack)
            occurrence_count = sum(haystack.count(term) for term in terms)
            heading_bonus = sum(1 for term in terms if term in chunk.heading.lower())
            return (matched_terms * 100 + occurrence_count * 10 + heading_bonus * 20, -chunk.chunk_index, -chunk.id)

        ranked = sorted(chunks, key=score, reverse=True)
        if terms:
            matched = [chunk for chunk in ranked if score(chunk)[0] > 0]
            ranked = matched or ranked

        results = []
        for index, chunk in enumerate(ranked[:limit]):
            results.append(
                {
                    "id": f"mysql-chunk-{chunk.id}",
                    "chunk_id": chunk.id,
                    "course_id": chunk.course_id,
                    "source_locator": chunk.source_locator,
                    "content": chunk.content,
                    "distance": float(index),
                }
            )
        return results
