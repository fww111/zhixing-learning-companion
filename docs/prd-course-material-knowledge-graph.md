# 课程材料知识库与知识图谱 PRD

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 产品模块 | 多课程本地知识库、课程知识图谱、学习路径与资源生成基础能力 |
| 所属系统 | 多智能体协同个性化学习平台 |
| 目标用户 | 学生、教师、课程建设者、竞赛演示评审 |
| 当前版本 | v0.2 |
| 文档状态 | 当前实现与后续优化基线 |

## 2. 背景与问题

当前系统已经具备登录注册、课程选择、课程专属画像访谈、课程知识库、知识图谱、学习路径、OpenMAIC 标准课堂、学习评估、错题集和智能辅导闭环。为了让个性化学习资源不是大模型凭空生成，系统必须先把课程 PDF/PPT/PPTX 材料解析为本地知识库，再抽取课程知识图谱，用知识图谱约束学习顺序、资源生成边界、即时辅导和错题补救。

用户的学习过程也不再是单课程静态流程。平台需要支持 `C语言程序设计` 和 `Python程序设计` 两门课程，并保证同一用户在不同课程下的画像、知识库、图谱、路径、课堂和评估数据完全隔离。

## 3. 产品目标

1. 用户登录后先选择课程，当前固定支持 `C语言程序设计` 与 `Python程序设计`。
2. 每门课程都有独立学生画像，画像通过对话式访谈构建，并能随学习行为持续更新。
3. 用户可以上传当前课程的多个 PDF/PPT/PPTX 文件，或确认使用当前课程的内置知识库。
4. 系统自动解析材料，写入 MySQL chunk，并用 BGE-M3 + Milvus 建立课程级向量索引。
5. 系统用 DeepSeek V4 Pro 从 MySQL chunk 中抽取课程知识结构，并写入 Neo4j。
6. 知识图谱以课程名为根节点，展示章节、知识点、前置、后续、相关和易错关系。
7. 学习路径必须由课程画像、知识图谱和掌握度共同生成。
8. 知识点学习页必须通过 Agentic RAG + 知识图谱约束生成 OpenMAIC 课堂和多模态资源。
9. 学习评估后更新画像、掌握度、图谱节点颜色和后续学习路径。
10. 学习评估错题必须归档为课程级错题集，支持选择题和编程题重做。
11. 全局智能辅导必须支持文字、图片和语音输入，回答通过本地知识库和知识图谱增强生成。

## 4. 用户角色

| 角色 | 核心诉求 |
| --- | --- |
| 学生 | 为当前课程构建画像、上传材料、查看图谱、按个性化路径学习 |
| 教师 | 提供课程材料，理解系统抽取的课程知识结构 |
| 课程建设者 | 维护课程、材料、知识库构建状态和图谱质量 |
| 系统 Agent | 读取课程画像、MySQL 原文证据、Milvus 召回和 Neo4j 约束，生成资源与路径 |

## 5. 范围定义

### 5.1 MVP 范围

- 固定课程选择：`C语言程序设计`、`Python程序设计`。
- 当前用户当前课程的画像访谈、确认和持久化。
- 课程材料 PDF/PPT/PPTX 多文件上传。
- 上传文件绑定当前登录用户和当前课程。
- MinerU 精准解析优先；本地 PDF/PPTX 解析和 OCR 只作为显式兜底。
- 解析文本按章节、页码、标题和语义长度切分 chunk，并写入 MySQL。
- 使用本地 BGE-M3 生成 embedding，模型缓存目录可配置到 D 盘。
- 使用 Milvus 保存课程级向量索引，支持语义召回和从 MySQL chunk 重建索引。
- 使用 DeepSeek V4 Pro 抽取知识点、层级、前置、后续、相关和易错关系。
- 使用 Neo4j 持久化当前用户当前课程子图。
- 前端展示材料状态、chunk、检索结果、知识图谱、节点详情和来源引用。
- 学习路径读取课程画像、知识图谱和掌握度。
- 知识点学习页读取本地知识库证据和图谱约束，生成 OpenMAIC 标准课堂和多模态资源。
- 学习评估更新画像、掌握度和后续路径。
- 错题集从课程级评估事件中提取错题，按知识图谱章节/小节归档，并支持重做后重新评分。
- 全局智能辅导从当前页面和课程上下文出发，执行 Agentic RAG 检索和 Qwen3.7-Plus 图片理解。

### 5.2 暂不纳入

- 多教师协作审核。
- 大规模课程运营后台。
- 视频课程解析。
- 完整人工图谱编辑器。
- 图谱节点人工拖拽后保存布局。

## 6. 核心流程

### 6.1 课程选择

1. 用户登录。
2. 进入 `/courses`。
3. 选择 `C语言程序设计` 或 `Python程序设计`。
4. 系统确保当前用户的课程记录存在。
5. 系统读取 `GET /api/profiles/me?course_id=<id>`。
6. 如果该课程没有画像，进入课程画像访谈；如果已有画像，进入课程知识库。

### 6.2 课程画像

1. 后端创建 `profile_interview`，绑定 `user_id + course_id`。
2. 首问固定，后续问题由 DeepSeek V4 Pro 根据画像缺口动态生成。
3. 每轮用户回答后，系统更新画像证据和完成度。
4. 画像维度齐全或接近 10 轮上限时自动确认。
5. `student_profiles` 写入当前课程画像。

### 6.3 上传并解析材料

```text
上传 PDF/PPT/PPTX
 -> 保存文件和 CourseMaterial，状态 queued
 -> MaterialTaskQueue 后台执行
 -> MinerU 精准解析
 -> 本地解析/OCR 显式兜底
 -> 章节语义分块
 -> KnowledgeChunk 写入 MySQL
 -> BGE-M3 向量化
 -> Milvus course-scoped upsert
 -> parsed / index_failed / failed
```

上传接口只负责保存和入队，不能同步等待完整解析。几百页教材属于长任务，前端应轮询材料状态。

### 6.4 生成知识图谱

1. 系统读取当前课程的 MySQL chunk。
2. DeepSeek V4 Pro 抽取候选知识点、章节层级和关系。
3. 知识点合并 Agent 合并同义、近义和重复节点。
4. 图谱质检 Agent 检查孤立节点、缺失层级、重复节点和无证据关系。
5. Neo4j 写入 Agent 按 `user_id + course_id` 替换课程子图。
6. 前端渲染图谱。

图谱根节点必须是课程名，例如 `Python程序设计` 或 `C语言程序设计`。节点颜色只表达掌握状态，不表达章节或知识类型。

### 6.5 学习规划和资源生成

1. 路径规划 Agent 读取课程画像、Neo4j 图谱和掌握度。
2. 有三级知识点时，学习任务规划三级知识点；二级节点只作为结构上下文。
3. 任务排期必须尊重画像中的时间偏好和约束。
4. 点击路径任务后进入知识点学习页。
5. Agentic RAG 读取图谱约束，Milvus 召回候选 chunk，MySQL 回表取得原文证据。
6. 多智能体生成文档、思维导图、视频脚本、代码实验、练习和拓展阅读。
7. 闭环校验通过后，后端提交 OpenMAIC 标准课堂。

### 6.6 学习评估和动态调整

1. 学生完成课堂、文档、思维导图、编程练习和测试。
2. 评估 Agent 综合选择题、编程题、课堂行为、耗时和重试情况评分。
3. 掌握度写入当前 `user_id + course_id + node_id`。
4. 图谱节点颜色更新。
5. 画像更新 Agent 写回薄弱点、行为和能力变化。
6. 路径规划 Agent 重新规划后续任务。
7. 未达标时插入薄弱点专项补救任务，通过后回到主线。
8. 错题集归档未答对选择题和未通过编程题；学生重做正确后，系统重新提交评估并更新当前知识点状态。

## 7. 功能需求

### 7.1 课程与数据隔离

| 编号 | 需求 | 优先级 |
| --- | --- | --- |
| C-001 | 用户登录后首先进入课程选择页 | P0 |
| C-002 | 固定展示 `C语言程序设计` 和 `Python程序设计` | P0 |
| C-003 | 用户可以将某门课设置为当前课程 | P0 |
| C-004 | 两门课的画像、材料、chunk、Milvus、Neo4j、路径、课堂和评估数据完全隔离 | P0 |
| C-005 | 内置课程需要用户点击确认后才挂载到当前用户 | P0 |

### 7.2 材料上传

| 编号 | 需求 | 优先级 |
| --- | --- | --- |
| F-001 | 支持 PDF、PPT、PPTX 多文件上传 | P0 |
| F-002 | 单文件大小限制可配置，默认 100MB | P1 |
| F-003 | 上传后立即返回 `queued`，解析异步执行 | P0 |
| F-004 | 文件只能由上传者和当前课程访问 | P0 |
| F-005 | 文件名必须清洗，禁止路径穿越 | P0 |
| F-006 | 删除材料时清理原文件、MySQL chunk、Milvus 向量和旧图谱任务 | P0 |

### 7.3 材料解析

| 编号 | 需求 | 优先级 |
| --- | --- | --- |
| P-001 | MinerU 精准解析 PDF/PPT/PPTX | P0 |
| P-002 | MinerU 结果转换为页码/幻灯片级内部结构 | P0 |
| P-003 | 缺少 MinerU Token 时快速失败 | P0 |
| P-004 | 本地解析/OCR 仅作为显式 fallback | P0 |
| P-005 | 解析状态支持 `queued/processing/mineru_submitted/mineru_polling/ocr_running/chunking/indexing/parsed/index_failed/failed` | P0 |

### 7.4 本地知识库

| 编号 | 需求 | 优先级 |
| --- | --- | --- |
| K-001 | 将解析文本切分为 chunk | P0 |
| K-002 | chunk 保存来源文件、页码/幻灯片编号、章节标题和正文 | P0 |
| K-003 | 使用本地 BGE-M3 生成 chunk 向量 | P0 |
| K-004 | 使用 Milvus 保存 chunk 向量并支持语义召回 | P0 |
| K-005 | Milvus collection 按课程、provider 和模型隔离 | P0 |
| K-006 | 支持从 MySQL 已有 chunk 重建 Milvus 索引 | P1 |
| K-007 | Milvus 不可用时保留 MySQL chunk，并允许 MySQL fallback | P0 |

### 7.5 知识图谱

| 编号 | 需求 | 优先级 |
| --- | --- | --- |
| G-001 | DeepSeek V4 Pro 从 MySQL chunk 抽取知识点 | P0 |
| G-002 | 根节点必须为课程名 | P0 |
| G-003 | 保留章节、节、小节和知识点层级 | P0 |
| G-004 | 每个节点保留来源 chunk 引用 | P0 |
| G-005 | 关系包含 `contains/prerequisite/related/successor/common_mistake/case_supports` 等 | P0 |
| G-006 | Neo4j 节点和边必须带 `user_id + course_id` | P0 |
| G-007 | 图谱可视化不支持人工拖拽编辑 | P0 |
| G-008 | 节点颜色只表达掌握状态 | P0 |

### 7.6 学习路径

| 编号 | 需求 | 优先级 |
| --- | --- | --- |
| L-001 | 路径规划必须读取当前课程画像、知识图谱和掌握度 | P0 |
| L-002 | 按知识图谱前置关系和章节顺序推进 | P0 |
| L-003 | 有子知识点的章节节点不能作为学习任务 | P0 |
| L-004 | 排期必须尊重画像时间约束 | P0 |
| L-005 | 评估未达标后插入薄弱点专项补救任务 | P0 |
| L-006 | `掌握基础` 视为未达标，`达标良好` 和 `精通` 才算通过 | P0 |

### 7.7 资源生成与评估

| 编号 | 需求 | 优先级 |
| --- | --- | --- |
| R-001 | 资源生成必须走 Agentic RAG + 知识图谱约束 | P0 |
| R-002 | Milvus 只做召回，最终证据来自 MySQL chunk | P0 |
| R-003 | 文档、思维导图、视频脚本、代码实验、练习、阅读分别由独立 Agent 生成 | P0 |
| R-004 | 输出分析、检索、校验、辩论和决策报告 | P0 |
| R-005 | OpenMAIC 标准课堂作为学习页主表面 | P0 |
| R-006 | TTS 默认使用 OpenMAIC 侧阿里云百炼 Qwen TTS | P0 |
| R-007 | 编程题只给题目要求，用户在浏览器编辑器中完成并运行 | P0 |
| R-008 | 评估结束后更新画像、掌握度、图谱颜色和路径 | P0 |
| R-009 | 题库 Agent 必须生成当前知识点的专业题，不能生成泛化主观题或学习行为题 | P0 |
| R-010 | 错题集按章节归档，支持选择题和编程题重做，重做正确后重新评分 | P0 |
| R-011 | 智能辅导支持文字、图片、语音输入，并通过课程 RAG 增强回答 | P0 |
| R-012 | 图片辅导默认使用 Qwen3.7-Plus，文本回答不得直接展示原始 RAG 调试块 | P1 |

## 8. 非功能需求

- 课程材料解析和索引必须异步执行。
- 100MB 以下文件上传应稳定完成。
- 单课程建议支持 500-2000 个 chunk、50-300 个知识点。
- 所有核心接口必须使用 JWT。
- 密钥、Token、Neo4j 密码、Qwen TTS Key 只放本地 `.env`。
- 运行产物如上传文件、模型缓存、OpenMAIC 课堂生成结果不得提交 Git。
- Mock LLM 必须可用，保证无外部 API 时仍能演示主要流程。

## 9. 数据模型建议

### 9.1 MySQL

MySQL 保存：

- `users`
- `courses`
- `profile_interviews`
- `profile_interview_messages`
- `student_profiles`
- `course_materials`
- `knowledge_chunks`
- `graph_build_jobs`
- `learning_paths`
- `lesson_sessions`
- `assessment_events`
- `knowledge_node_masteries`
- `learning_profile_events`
- `profile_update_logs`
- `learning_path_revisions`

### 9.2 Milvus

Milvus 保存 chunk embedding。Collection 命名应包含课程、provider 和模型标识，并对长本地模型路径做 hash 缩短。

### 9.3 Neo4j

Neo4j 保存课程知识图谱。节点和边必须包含：

- `user_id`
- `course_id`
- `node_id`
- `name`
- `node_type`
- `difficulty`
- `source_chunk_ids`
- `confidence`

## 10. API 草案

```text
POST /api/auth/register
POST /api/auth/login
GET /api/auth/me

POST /api/profile-interviews
POST /api/profile-interviews/{id}/messages
POST /api/profile-interviews/{id}/confirm
GET /api/profiles/me?course_id=<id>

POST /api/courses/default-python
POST /api/courses/default-c
GET /api/courses
POST /api/courses/{course_id}/materials
DELETE /api/courses/{course_id}/materials/{material_id}
POST /api/courses/{course_id}/vector-index/rebuild
POST /api/courses/{course_id}/graph/build
GET /api/courses/{course_id}/graph
POST /api/courses/{course_id}/learning-paths/plan

POST /api/resources/generate
GET /api/resources/openmaic-jobs/{job_id}
PATCH /api/resources/lessons/state

POST /api/assessments/submit
POST /api/tutor/chat
POST /tts/upload
```

## 11. 验收标准

1. 用户登录后先进入课程选择页。
2. C/Python 两门课的数据完全隔离。
3. 用户未确认内置知识库时，系统不会默认挂载内置课程材料。
4. 支持多文件上传并进入异步解析流程。
5. MinerU 解析成功后生成 MySQL chunk。
6. BGE-M3 能将 chunk 写入 Milvus。
7. Milvus 失败时 MySQL chunk 保留，并可重建索引。
8. 知识图谱根节点为课程名，章节和三级节点尽量完整。
9. 节点颜色只表达掌握状态。
10. 学习路径基于当前课程画像、图谱和掌握度生成。
11. 评估未达标后插入薄弱点专项补救任务。
12. 学习页资源生成响应包含 Agentic RAG 证据、图谱约束、校验、辩论和决策报告。
13. OpenMAIC 课堂可通过后端代理轮询并嵌入学习页。
14. 学习评估能更新画像、掌握度、图谱颜色和路径。
15. 错题集能从历史评估事件中提取错题，并在重做正确后更新评分。
16. 智能辅导能针对当前课程执行 RAG 增强回答，图片问题走 Qwen3.7-Plus。

## 12. 已确认产品决策

1. 固定展示课程为 `C语言程序设计` 和 `Python程序设计`。
2. 每门课程都有独立画像、知识库、图谱、路径、课堂和评估数据。
3. 图谱可视化不支持人工拖拽编辑。
4. 解析优先使用 MinerU，OCR 作为显式兜底。
5. 向量检索使用 Milvus，ChromaDB 仅保留历史兼容代码，不作为当前主链路。
6. 知识图谱采用 Neo4j。
7. OpenMAIC 标准课堂使用阿里云百炼 Qwen TTS 作为默认语音方案。
8. 智能辅导图片理解使用 `TUTOR_VISION_MODEL=qwen3.7-plus`，普通学生 UI 不展示原始 RAG 证据块。
9. VoxCPM2 是可选实验兜底，不是默认安装依赖。

## 13. 建议环境变量

```text
MILVUS_URI=http://127.0.0.1:19530
MILVUS_TOKEN=
MILVUS_DB_NAME=
EMBEDDING_PROVIDER=local_bge
EMBEDDING_MODEL=D:/softbei/a3/data/models/embeddings/BAAI/bge-m3
EMBEDDING_DEVICE=cpu
EMBEDDING_CACHE_DIR=D:/softbei/a3/data/models/embeddings
MINERU_ENABLED=true
MINERU_API_TOKEN=
MINERU_BASE_URL=https://mineru.net
MINERU_MODEL_VERSION=vlm
MINERU_LANGUAGE=ch
MINERU_ENABLE_TABLE=true
MINERU_ENABLE_FORMULA=true
MINERU_IS_OCR=true
MINERU_POLL_INTERVAL_SECONDS=3
MINERU_POLL_TIMEOUT_SECONDS=900
MINERU_FALLBACK_TO_LOCAL=false
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=
OPENMAIC_BASE_URL=http://127.0.0.1:3000
TTS_QWEN_API_KEY=
TTS_QWEN_BASE_URL=
TUTOR_VISION_API_KEY=
TUTOR_VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
TUTOR_VISION_MODEL=qwen3.7-plus
```

MinerU Token、Neo4j 密码、大模型密钥和 Qwen TTS Key 只保存在本地 `.env`，不得提交到 Git。
