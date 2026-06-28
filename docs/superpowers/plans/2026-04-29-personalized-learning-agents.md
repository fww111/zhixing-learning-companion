# 基于大模型的个性化学习多智能体系统实施计划

> 状态说明：这是早期实施计划归档，保留用于追溯开发过程。当前项目已经升级为多课程、课程级隔离架构，向量检索主链路已从 ChromaDB 调整为 Milvus，课堂使用 OpenMAIC + Qwen TTS，并新增智能辅导和错题集闭环。当前事实以 `README.md`、`AGENTS.md` 和 `docs/current-technical-overview.md` 为准。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个面向高校课程学习的 AI Native 多智能体系统，完成对话式学生画像、个性化资源生成、学习路径规划、资源推荐、智能辅导与学习效果评估的可运行演示原型。

**Architecture:** 采用 Web 前端 + FastAPI 后端 + LangGraph 多智能体编排 + MySQL/SQLite 结构化存储 + ChromaDB 向量检索 + Redis/内存任务队列的模块化架构。以“机器学习”或“数据结构”作为首个垂直课程场景，避免泛化过宽导致演示效果稀释。

**Tech Stack:** React/Vite/Ant Design、FastAPI、LangGraph、SQLAlchemy、ChromaDB、SSE、Markdown/Markmap、DeepSeek/讯飞星火兼容 LLM 接口、可选 SeeDance/Manim/Remotion 视频生成。

---

## 一、需求解读与优先级

### 必达功能

1. **对话式学习画像构建**
   - 通过自然语言对话采集学生专业、年级、目标、基础、偏好、薄弱点等信息。
   - 画像维度不少于 6 个，建议固定为 8 个：专业背景、课程目标、知识基础、学习风格、认知风格、薄弱知识点、时间投入、资源偏好。
   - 支持画像随学习行为、答题结果、资源反馈动态更新。

2. **多智能体协同资源生成**
   - 至少 5 个专业 Agent，并有明确协作流程。
   - 至少生成 5 类资源，建议直接实现 6 类：课程讲解文档、思维导图、练习题、拓展阅读、教学动画/视频脚本、代码实操案例。

3. **个性化学习路径规划与资源推荐**
   - 根据画像、目标、薄弱点、学习历史规划阶段化路径。
   - 推荐资源时给出可解释原因，例如“因你的薄弱点为梯度下降，优先推荐可视化动画与基础练习”。

4. **现代 AI 产品交互**
   - 支持流式输出。
   - 支持 Markdown 渲染、思维导图展示、练习题交互、代码高亮、视频/动画资源卡片。
   - 显示 Agent 协作状态，让评审能直观看到多智能体不是单 Prompt。

5. **提交材料**
   - 可运行源码。
   - 技术方案文档。
   - 部署说明、测试说明、AI Coding 工具说明。
   - 7 分钟以内演示视频脚本与 PPT 大纲。

### 加分功能

1. **智能辅导 Agent**
   - 基于当前学习路径、资源和题目结果进行针对性答疑。
   - 支持文字解答、图解说明、视频脚本或动画脚本。

2. **学习效果评估 Agent**
   - 跟踪题目正确率、资源完成率、反馈评分、停留时间。
   - 输出掌握度雷达图、短板列表、下一步调整建议。

3. **创新展示**
   - Agent 协作可视化。
   - 画像可解释推荐。
   - 资源质量评估。
   - 跨模态一致性检查。

---

## 二、总体交付范围

### 课程场景

首个演示课程建议选择 **机器学习基础**，原因是：

- 适合生成文档、导图、题目、代码案例和动画。
- 有清晰知识路径：线性回归、梯度下降、过拟合、分类、评价指标。
- 便于演示不同基础学生的差异化推荐。

### 演示主线

使用一个具体学生案例贯穿演示：

> 小明，计算机专业大二，Python 基础一般，想在 4 周内入门机器学习，但对线性代数和梯度下降比较薄弱，偏好图解和代码实操。

演示流程：

1. 学生通过对话说明背景和目标。
2. 画像 Agent 抽取并展示 8 维画像。
3. 编排器启动多个 Agent 生成资源。
4. 前端实时显示 Agent 进度。
5. 系统生成学习路径与推荐理由。
6. 学生完成练习后，评估 Agent 更新画像和下一步计划。

---

## 三、建议项目结构

```text
D:\softbei\a3
├── apps
│   ├── api
│   │   ├── app
│   │   │   ├── main.py
│   │   │   ├── core
│   │   │   │   ├── config.py
│   │   │   │   └── security.py
│   │   │   ├── agents
│   │   │   │   ├── graph.py
│   │   │   │   ├── base.py
│   │   │   │   ├── profile_agent.py
│   │   │   │   ├── document_agent.py
│   │   │   │   ├── exercise_agent.py
│   │   │   │   ├── multimodal_agent.py
│   │   │   │   ├── coding_agent.py
│   │   │   │   ├── path_agent.py
│   │   │   │   ├── tutor_agent.py
│   │   │   │   └── evaluator_agent.py
│   │   │   ├── llm
│   │   │   │   ├── client.py
│   │   │   │   ├── prompts.py
│   │   │   │   └── schemas.py
│   │   │   ├── models
│   │   │   │   ├── user.py
│   │   │   │   ├── profile.py
│   │   │   │   ├── resource.py
│   │   │   │   ├── learning_path.py
│   │   │   │   └── assessment.py
│   │   │   ├── routers
│   │   │   │   ├── chat.py
│   │   │   │   ├── profiles.py
│   │   │   │   ├── resources.py
│   │   │   │   ├── paths.py
│   │   │   │   └── assessments.py
│   │   │   ├── services
│   │   │   │   ├── resource_service.py
│   │   │   │   ├── recommendation_service.py
│   │   │   │   ├── retrieval_service.py
│   │   │   │   └── safety_service.py
│   │   │   └── db.py
│   │   ├── tests
│   │   │   ├── test_profile_agent.py
│   │   │   ├── test_resource_generation.py
│   │   │   ├── test_path_planning.py
│   │   │   └── test_api_smoke.py
│   │   ├── pyproject.toml
│   │   └── README.md
│   └── web
│       ├── src
│       │   ├── App.tsx
│       │   ├── api
│       │   │   └── client.ts
│       │   ├── components
│       │   │   ├── AgentTimeline.tsx
│       │   │   ├── ChatPanel.tsx
│       │   │   ├── ProfilePanel.tsx
│       │   │   ├── ResourceCard.tsx
│       │   │   ├── LearningPath.tsx
│       │   │   ├── AssessmentPanel.tsx
│       │   │   └── MindMapViewer.tsx
│       │   ├── pages
│       │   │   └── Workspace.tsx
│       │   └── styles
│       │       └── app.css
│       ├── package.json
│       └── README.md
├── data
│   ├── seed
│   │   ├── course_machine_learning.json
│   │   ├── student_profiles.json
│   │   └── resources.json
│   └── generated
├── docs
│   ├── technical-solution.md
│   ├── agent-design.md
│   ├── deployment.md
│   ├── testing.md
│   ├── ai-coding-tools.md
│   ├── demo-script.md
│   └── ppt-outline.md
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 四、实施里程碑

### Milestone 0：项目定向与基础资料

**目标：** 明确课程范围、演示故事、测试数据和提交材料目录。

- [ ] 选择演示课程为“机器学习基础”。
- [ ] 编写 20 个学生画像样本，覆盖基础薄弱型、目标冲刺型、实践偏好型、理论强化型。
- [ ] 编写 100 条基础学习资源种子数据，包含知识点、难度、资源类型、前置知识、适合画像标签。
- [ ] 确定 LLM Provider 优先级：讯飞星火兼容接口优先，DeepSeek/OpenAI-compatible 接口作为备用。
- [ ] 输出 `docs/technical-solution.md` 初稿，包含架构图、技术选型、多 Agent 协作机制。

**验收标准：**

- 有明确课程、学生案例、资源样本和技术方案初稿。
- 后续开发不再临时扩展课程范围。

### Milestone 1：后端骨架与数据模型

**目标：** 建立可运行 API 服务和核心数据结构。

- [ ] 创建 FastAPI 项目。
- [ ] 配置 `.env.example`，包含 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`、`DATABASE_URL`。
- [ ] 定义学生画像 Schema：

```json
{
  "major": "计算机科学与技术",
  "grade": "大二",
  "learning_goal": "4周内入门机器学习",
  "knowledge_foundation": "Python基础一般，线性代数薄弱",
  "learning_style": "偏好图解和案例",
  "cognitive_style": "先直观理解再公式推导",
  "weak_points": ["梯度下降", "矩阵运算", "模型评估"],
  "time_preference": "每天晚间45分钟",
  "resource_preference": ["动画", "代码实操", "短练习"],
  "updated_evidence": []
}
```

- [ ] 定义资源 Schema：文档、导图、题目、阅读、视频/动画、代码案例。
- [ ] 定义学习路径 Schema：阶段、目标、前置条件、推荐资源、验收任务、推荐理由。
- [ ] 定义学习事件 Schema：资源浏览、练习提交、反馈评分、辅导问题。
- [ ] 提供 API：
  - `POST /api/chat/profile`
  - `GET /api/profiles/{student_id}`
  - `POST /api/resources/generate`
  - `GET /api/resources/{resource_id}`
  - `POST /api/paths/plan`
  - `POST /api/assessments/submit`

**验收标准：**

- `uvicorn app.main:app --reload` 可启动。
- OpenAPI 页面可访问。
- 单元测试能验证画像、资源、路径 Schema 的字段完整性。

### Milestone 2：LLM 接入与结构化输出

**目标：** 封装统一模型客户端，保证所有 Agent 可切换模型供应商。

- [ ] 实现 `llm/client.py`，支持 OpenAI-compatible Chat Completions。
- [ ] 实现流式响应封装，用于前端 SSE 展示。
- [ ] 实现 JSON 结构化输出解析与重试。
- [ ] 实现 Safety Guard：
  - 禁止输出违法违规内容。
  - 对学生画像中的敏感隐私字段做最小化采集。
  - 资源生成前后做基本内容审查。
- [ ] 为无 API Key 场景提供 Mock LLM，保证本地演示仍可运行。

**验收标准：**

- 有真实模式和 Mock 模式。
- Agent 测试不依赖外部网络也能跑通。
- 流式输出在 API 层可被消费。

### Milestone 3：画像构建 Agent

**目标：** 通过对话生成并更新 8 维学生画像。

- [ ] 实现 `ProfileAgent.extract_profile(conversation)`。
- [ ] 实现 `ProfileAgent.update_profile(profile, learning_event)`。
- [ ] 提示词要求模型输出固定 JSON，不允许自由文本混入。
- [ ] 前端展示画像维度和证据来源。
- [ ] 每次答题、资源反馈后自动追加 `updated_evidence`。

**验收标准：**

- 输入一段学生自述后，可生成不少于 8 个画像字段。
- 输入一次错题记录后，画像中的薄弱点和推荐偏好会更新。
- 前端能展示“画像来自哪些对话或学习行为”。

### Milestone 4：多智能体编排

**目标：** 使用 LangGraph 或等价工作流实现 Agent 协作，而不是单接口串行调用。

- [ ] 定义共享状态 `AgentState`：
  - `student_profile`
  - `course_topic`
  - `generation_goal`
  - `agent_messages`
  - `resources`
  - `quality_scores`
  - `learning_path`
- [ ] 实现工作流：
  1. 画像 Agent 读取学生画像。
  2. 文档 Agent 生成讲解文档。
  3. 题库 Agent 生成练习题。
  4. 多模态 Agent 生成思维导图和视频脚本。
  5. 代码 Agent 生成代码案例。
  6. 路径 Agent 汇总资源并规划学习路径。
  7. 评估 Agent 给资源打分并提出改进建议。
- [ ] 为每个 Agent 输出事件：
  - `agent_started`
  - `agent_streaming`
  - `agent_completed`
  - `agent_failed`
- [ ] 前端使用 AgentTimeline 实时展示协作状态。

**验收标准：**

- 点击“生成学习方案”后，至少 5 个 Agent 依次或并行产生可见状态。
- 生成结果里能看到每个 Agent 的贡献。
- 失败的 Agent 不影响已完成资源展示，并给出可重试入口。

### Milestone 5：资源生成能力

**目标：** 完成至少 6 类资源生成并可展示。

- [ ] 文档 Agent 输出 Markdown 讲解文档，结构包括：学习目标、直观解释、核心概念、公式/代码示例、常见误区、总结。
- [ ] 思维导图输出 Markmap Markdown，例如：

```markdown
# 梯度下降
## 目标
### 最小化损失函数
## 核心步骤
### 初始化参数
### 计算梯度
### 更新参数
## 常见问题
### 学习率过大
### 陷入局部最优
```

- [ ] 题库 Agent 输出选择题、填空题、简答题、编程题，每题包含答案、解析、难度、知识点标签。
- [ ] 拓展阅读 Agent 输出阅读材料摘要、适合原因、阅读顺序、检查问题。
- [ ] 多模态 Agent 输出教学视频/动画脚本；如果 SeeDance API 不可用，则先生成 Manim/Remotion 可执行脚本或视频分镜作为降级实现。
- [ ] 代码 Agent 输出可运行 Python 案例，例如线性回归梯度下降 demo，并附运行说明。
- [ ] 资源质量评估 Agent 对每个资源输出准确性、适配度、完整性、可操作性评分。

**验收标准：**

- 同一知识点至少能生成 6 类资源。
- 资源之间内容一致，例如文档、题目、代码案例都围绕同一个知识点。
- 前端按资源类型展示不同卡片和交互控件。

### Milestone 6：学习路径与推荐

**目标：** 让系统从“生成资源”升级为“个性化学习方案”。

- [ ] 路径 Agent 根据画像规划 3-5 个学习阶段。
- [ ] 每个阶段包含：
  - 阶段目标
  - 推荐资源
  - 学习顺序
  - 预计时长
  - 练习任务
  - 推荐理由
- [ ] 推荐算法采用规则 + LLM 混合：
  - 规则层按知识点前置关系、难度、资源类型过滤。
  - LLM 层根据画像生成解释和微调顺序。
- [ ] 前端展示时间线式学习路径。
- [ ] 每个资源卡片展示“为什么推荐”。

**验收标准：**

- 基础薄弱学生优先收到图解、入门文档和低难度练习。
- 实践偏好学生优先收到代码案例和项目任务。
- 完成练习后重新规划路径，能看到推荐变化。

### Milestone 7：智能辅导与学习评估

**目标：** 实现加分项闭环。

- [ ] 智能辅导 Agent 接收学生问题、当前画像、当前资源、学习路径上下文。
- [ ] 输出分层解答：
  - 简短结论
  - 图解/类比
  - 关键步骤
  - 推荐复习资源
  - 检查题
- [ ] 学习评估 Agent 汇总学习事件：
  - 资源完成率
  - 题目正确率
  - 错题知识点
  - 反馈评分
- [ ] 输出掌握度矩阵和下一步调整建议。
- [ ] 前端展示评估面板和画像变化记录。

**验收标准：**

- 学生答错“学习率过大导致震荡”相关题目后，系统能把“梯度下降参数调优”加入薄弱点。
- 学习路径会推荐对应复习资源和练习。

### Milestone 8：前端可演示工作台

**目标：** 做成一个评委可直接理解价值的工作台，而不是接口集合。

- [ ] 首页即进入学习工作台，不做营销落地页。
- [ ] 左侧：学生对话与当前任务输入。
- [ ] 中间：资源生成结果与学习路径。
- [ ] 右侧：学生画像、Agent 状态、评估指标。
- [ ] 支持：
  - Markdown 渲染。
  - Markmap 思维导图。
  - 练习题提交与解析。
  - 代码高亮。
  - 视频/动画脚本或播放器。
  - SSE 流式输出。
- [ ] 使用克制的教育产品视觉风格，信息密度适中，避免装饰性过强。

**验收标准：**

- 评委无需阅读说明即可完成主流程。
- 页面中能明确看到学生画像、多 Agent 协作、生成资源、路径推荐、评估更新。
- 桌面端和移动端基本可用。

### Milestone 9：测试、部署与文档

**目标：** 满足提交要求和现场复现要求。

- [ ] 编写后端单元测试：
  - 画像抽取。
  - 画像更新。
  - 资源生成 Schema。
  - 学习路径规划。
  - API smoke test。
- [ ] 编写前端 smoke test 或手工测试清单。
- [ ] 编写 `docker-compose.yml`：
  - api
  - web
  - db
  - redis
  - chroma
- [ ] 同时编写本机运行方式：
  - `conda activate a3`
  - 后端启动命令。
  - 前端启动命令。
- [ ] 完成文档：
  - `docs/technical-solution.md`
  - `docs/agent-design.md`
  - `docs/deployment.md`
  - `docs/testing.md`
  - `docs/ai-coding-tools.md`
  - `docs/demo-script.md`
  - `docs/ppt-outline.md`

**验收标准：**

- 新机器按文档能运行。
- 无 API Key 时 Mock 模式可完成演示。
- 有 API Key 时可调用真实模型生成内容。

---

## 五、开发顺序建议

1. 先做 **Mock 全流程闭环**，不要一开始卡在真实模型和视频生成接口。
2. 再替换真实 LLM，并保留 Mock 模式兜底。
3. 先做文档、题目、导图、路径规划，这四类最容易稳定展示。
4. 视频/动画先做“分镜脚本 + Manim/Remotion 降级方案”，真实 SeeDance 接入作为增强。
5. 最后打磨 Agent 可视化、推荐解释和演示材料。

---

## 六、风险与应对

| 风险 | 影响 | 应对 |
| :--- | :--- | :--- |
| LLM API 不稳定 | 演示中断 | 保留 Mock LLM 和预生成样例 |
| 视频生成耗时过长 | 现场等待 | 使用异步任务、进度展示、预生成视频或脚本降级 |
| 多 Agent 只停留在概念 | 评分受损 | 前端必须展示每个 Agent 的状态、输入、输出摘要 |
| 资源质量不稳定 | 实用性受损 | 增加资源质量评估 Agent 和人工精选种子数据 |
| 范围过大 | 无法完成 | 首期只深做“机器学习基础”一门课 |
| 部署环境差异 | 提交后无法运行 | 提供本机 conda 方案和 Docker 方案两套说明 |

---

## 七、评分对齐检查

### 创新价值与实用性 35%

- 多 Agent 协作可视化：对应创新性。
- 画像解释推荐：对应实用性和个性化。
- 资源质量评估：对应实用性。
- 跨模态一致性：对应资源生成策略创新。

### 功能实现及技术要求 45%

- 画像维度 8 个，大于赛题要求 6 个。
- Agent 数量 7-8 个，大于建议最低 5 个。
- 资源类型 6 类，满足至少 5 类。
- LangGraph 编排、SSE 流式、Markdown/Markmap/代码高亮/视频脚本展示，覆盖技术实现质量。

### 配套文档 10%

- 技术方案、Agent 设计、部署、测试、AI Coding 工具说明全部列入交付。

### 演示视频/PPT 10%

- 以“小明学习机器学习”为主线，完整展示对话画像、资源生成、路径推荐、评估更新。

---

## 八、初版任务清单

### Task 1：建立项目骨架

**Files:**
- Create: `apps/api/app/main.py`
- Create: `apps/api/app/core/config.py`
- Create: `apps/api/pyproject.toml`
- Create: `apps/web/package.json`
- Create: `apps/web/src/App.tsx`
- Create: `.env.example`

- [ ] 创建 FastAPI 最小服务，提供 `/health`。
- [ ] 创建 Vite React 最小前端。
- [ ] 添加 `.env.example`。
- [ ] 运行后端健康检查。
- [ ] 运行前端页面。
- [ ] 提交：`chore: scaffold api and web apps`

### Task 2：实现核心 Schema 与测试

**Files:**
- Create: `apps/api/app/llm/schemas.py`
- Create: `apps/api/app/models/profile.py`
- Create: `apps/api/app/models/resource.py`
- Create: `apps/api/app/models/learning_path.py`
- Create: `apps/api/tests/test_schemas.py`

- [ ] 定义画像、资源、学习路径、学习事件 Pydantic 模型。
- [ ] 写测试验证画像字段不少于 8 个。
- [ ] 写测试验证资源类型包含 6 类。
- [ ] 运行测试。
- [ ] 提交：`feat: define learning schemas`

### Task 3：实现 LLM 客户端与 Mock 模式

**Files:**
- Create: `apps/api/app/llm/client.py`
- Create: `apps/api/app/llm/prompts.py`
- Create: `apps/api/tests/test_llm_client.py`

- [ ] 实现 OpenAI-compatible 客户端。
- [ ] 实现 Mock 响应。
- [ ] 实现 JSON 解析失败重试。
- [ ] 测试 Mock 模式稳定输出。
- [ ] 提交：`feat: add llm client with mock fallback`

### Task 4：实现画像 Agent

**Files:**
- Create: `apps/api/app/agents/base.py`
- Create: `apps/api/app/agents/profile_agent.py`
- Create: `apps/api/app/routers/profiles.py`
- Create: `apps/api/tests/test_profile_agent.py`

- [ ] 写画像抽取测试。
- [ ] 实现画像抽取。
- [ ] 写画像更新测试。
- [ ] 实现画像随学习事件更新。
- [ ] 暴露画像 API。
- [ ] 提交：`feat: add profile agent`

### Task 5：实现资源生成 Agent

**Files:**
- Create: `apps/api/app/agents/document_agent.py`
- Create: `apps/api/app/agents/exercise_agent.py`
- Create: `apps/api/app/agents/multimodal_agent.py`
- Create: `apps/api/app/agents/coding_agent.py`
- Create: `apps/api/app/services/resource_service.py`
- Create: `apps/api/app/routers/resources.py`
- Create: `apps/api/tests/test_resource_generation.py`

- [ ] 为每种资源写 Schema 测试。
- [ ] 实现文档生成。
- [ ] 实现题目生成。
- [ ] 实现思维导图生成。
- [ ] 实现拓展阅读生成。
- [ ] 实现视频/动画脚本生成。
- [ ] 实现代码案例生成。
- [ ] 暴露资源生成 API。
- [ ] 提交：`feat: add resource generation agents`

### Task 6：实现 LangGraph 编排与 Agent 状态流

**Files:**
- Create: `apps/api/app/agents/graph.py`
- Modify: `apps/api/app/routers/resources.py`
- Create: `apps/api/tests/test_agent_graph.py`

- [ ] 定义共享状态。
- [ ] 串接画像、文档、题库、多模态、代码、路径 Agent。
- [ ] 输出 Agent 事件流。
- [ ] 实现失败降级。
- [ ] 提交：`feat: orchestrate agents with workflow events`

### Task 7：实现路径规划与推荐解释

**Files:**
- Create: `apps/api/app/agents/path_agent.py`
- Create: `apps/api/app/services/recommendation_service.py`
- Create: `apps/api/app/routers/paths.py`
- Create: `apps/api/tests/test_path_planning.py`

- [ ] 写路径规划测试。
- [ ] 实现规则过滤。
- [ ] 实现 LLM 推荐解释。
- [ ] 暴露路径 API。
- [ ] 提交：`feat: add personalized learning path planning`

### Task 8：实现智能辅导与效果评估

**Files:**
- Create: `apps/api/app/agents/tutor_agent.py`
- Create: `apps/api/app/agents/evaluator_agent.py`
- Create: `apps/api/app/routers/assessments.py`
- Create: `apps/api/tests/test_assessment.py`

- [ ] 实现上下文答疑。
- [ ] 实现练习提交。
- [ ] 实现掌握度评估。
- [ ] 实现画像更新触发。
- [ ] 提交：`feat: add tutoring and assessment loop`

### Task 9：实现前端工作台

**Files:**
- Create: `apps/web/src/pages/Workspace.tsx`
- Create: `apps/web/src/components/ChatPanel.tsx`
- Create: `apps/web/src/components/ProfilePanel.tsx`
- Create: `apps/web/src/components/AgentTimeline.tsx`
- Create: `apps/web/src/components/ResourceCard.tsx`
- Create: `apps/web/src/components/LearningPath.tsx`
- Create: `apps/web/src/components/AssessmentPanel.tsx`
- Create: `apps/web/src/components/MindMapViewer.tsx`
- Create: `apps/web/src/api/client.ts`
- Create: `apps/web/src/styles/app.css`

- [ ] 实现三栏工作台布局。
- [ ] 实现对话输入与流式输出。
- [ ] 实现 Agent 状态时间线。
- [ ] 实现画像面板。
- [ ] 实现资源卡片。
- [ ] 实现学习路径时间线。
- [ ] 实现练习提交和评估面板。
- [ ] 提交：`feat: build learning agent workspace`

### Task 10：补齐文档与演示材料

**Files:**
- Create: `docs/technical-solution.md`
- Create: `docs/agent-design.md`
- Create: `docs/deployment.md`
- Create: `docs/testing.md`
- Create: `docs/ai-coding-tools.md`
- Create: `docs/demo-script.md`
- Create: `docs/ppt-outline.md`
- Create: `docker-compose.yml`
- Create: `README.md`

- [ ] 写技术方案。
- [ ] 写 Agent 协作设计。
- [ ] 写本机 conda 运行说明。
- [ ] 写 Docker 部署说明。
- [ ] 写测试说明。
- [ ] 写 AI Coding 工具说明。
- [ ] 写 7 分钟演示视频脚本。
- [ ] 写 PPT 大纲。
- [ ] 提交：`docs: add submission documentation`

---

## 九、完成定义

项目达到以下条件时，可认为初赛可提交：

- [ ] 本地可以启动前后端。
- [ ] Mock 模式可完整演示主流程。
- [ ] 真实 LLM 模式至少可完成画像、文档、题目、路径规划。
- [ ] 前端清楚展示 Agent 协作、画像、资源、路径、评估。
- [ ] 资源类型不少于 6 类。
- [ ] 画像维度不少于 8 个。
- [ ] 文档、部署说明、测试说明、AI Coding 说明齐全。
- [ ] PPT 大纲和 7 分钟演示脚本齐全。
