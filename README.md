# 个性化学习多智能体系统

这是一个面向“基于大模型的个性化资源生成与学习多智能体系统开发”赛题的可运行原型。当前项目已经升级为多课程、课程级隔离的个性化学习平台，支持 JWT 登录注册、课程专属学生画像、课程本地知识库、Milvus 向量检索、Neo4j 知识图谱、Agentic RAG、多智能体资源生成、OpenMAIC 标准课堂、智能辅导、错题集和动态学习路径。

当前技术总览见 [docs/current-technical-overview.md](docs/current-technical-overview.md)。

## 华为 ICT 大赛赛题二（AgentArts）迁移

本项目正作为底座迁移到华为云 AgentArts 平台参赛，相关设计、蓝图与 MCP 服务：

- [docs/agentarts/01-场景定义与Agent架构.md](docs/agentarts/01-场景定义与Agent架构.md) — 场景识别、多 Agent 架构、模型与资产选择
- [docs/agentarts/02-AgentArts工作流搭建蓝图.md](docs/agentarts/02-AgentArts工作流搭建蓝图.md) — 平台侧节点级搭建说明
- [docs/agentarts/03-MCP服务接口契约.md](docs/agentarts/03-MCP服务接口契约.md) — 三个自定义 MCP Server 的工具契约
- [apps/mcp/](apps/mcp/README.md) — MCP Server 实现（uv 项目，`uv run pytest` 验证）
- [docs/agentarts/05-技术借鉴与增强.md](docs/agentarts/05-技术借鉴与增强.md) — 源自"伯乐"项目的分块预设体系与知识库检索自动评估闭环

## 核心能力

- 用户注册、登录、JWT 鉴权和当前用户查询。
- 固定支持 `C语言程序设计` 与 `Python程序设计` 两门展示课程。
- 用户选择课程后，构建该课程专属学生画像；不同课程的画像互相隔离。
- 对话式多轮访谈构建画像，首问固定，后续由 DeepSeek V4 Pro 基于画像缺口动态追问，画像完整后自动确认并持久化到 MySQL。
- 支持课程材料 PDF/PPT/PPTX 多文件上传，MinerU 精准解析优先，本地解析/OCR 仅作为显式兜底。
- 课程材料切片写入 MySQL，文本向量化使用本地 BGE-M3，向量召回层使用 Milvus。
- 使用 DeepSeek V4 Pro 从本地知识库抽取课程知识结构，写入 Neo4j 并在前端展示知识图谱。
- 资源生成采用 Agentic RAG + 知识图谱约束：Milvus 召回候选，最终证据回表 MySQL 原文 chunk。
- 文档、思维导图、视频脚本、代码实验、练习题、拓展阅读分别由独立 Agent 生成，并经过事实校验、教学适配、辩论交叉验证和决策。
- 知识点学习页以 OpenMAIC 标准课堂为主学习表面，课堂语音默认使用 OpenMAIC 侧配置的阿里云百炼 Qwen TTS。
- 题库 Agent 会围绕当前知识点生成专业练习题，选择题保存 `correct_answer_index`，编程题只给任务要求和期望输出，由学生在浏览器编辑器中完成。
- 学习评估会综合课堂完成、文档/思维导图、题库、编程运行、耗时和重试等维度，更新知识点掌握度、知识图谱节点颜色、学生画像和后续学习路径；未达标时插入薄弱点专项补救任务。
- 学习评估页提供错题集入口，错题按知识图谱章节/小节归档；选择题和编程题重做正确后，会重新写入评估结果并触发画像、掌握度和路径更新。
- 登录后的全局页面右下角提供智能辅导悬浮窗，支持文字、图片和浏览器语音输入；回答通过 Agentic RAG 增强生成，图片理解默认使用 Qwen3.7-Plus 配置。
- Mock LLM 模式保留为无 API Key 演示兜底。

## 目录结构

```text
apps/api/      FastAPI 后端
apps/web/      React + Vite + TypeScript 前端
data/seed/     演示课程和资源种子数据
docs/          技术方案、部署、测试、设计稿和需求文档
OpenMAIC-main/ OpenMAIC 标准课堂前端与生成服务
```

## 本机运行

先确认本地 MySQL 已创建数据库：

```sql
CREATE DATABASE IF NOT EXISTS softbei DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

后端：

```powershell
conda activate a3
cd D:\softbei\a3\apps\api
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

前端：

```powershell
cd D:\softbei\a3\apps\web
npm install
npm run dev
```

访问 `http://127.0.0.1:5173`。

OpenMAIC 默认运行在：

```text
http://127.0.0.1:3000
```

如果需要完整标准课堂能力，请先启动 OpenMAIC，并在 OpenMAIC 自身 `.env.local` 或设置页中配置模型 provider 和阿里云百炼 Qwen TTS。

## 当前产品流程

```text
/auth 登录注册
 -> /courses 选择 C语言程序设计 或 Python程序设计
 -> /courses/:courseId/profile/interview 构建该课程专属画像
 -> /courses/:courseId/knowledge-base 上传材料或确认内置知识库
 -> /courses/:courseId/graph 构建并查看知识图谱
 -> /courses/:courseId/learning-path 生成动态学习路径
 -> /courses/:courseId/knowledge/:nodeId 进入知识点学习页
 -> OpenMAIC 标准课堂、文档、思维导图、代码练习、随堂测试
 -> 学习评估
 -> /courses/:courseId/assessment/wrong-questions 错题重做与评分回写
 -> 更新画像、掌握度、图谱颜色和学习路径
```

多课程隔离是核心约束。课程画像、材料、MySQL chunk、Milvus collection、Neo4j 子图、学习路径、课堂缓存、评估记录和掌握度都必须绑定当前 `user_id + course_id`。

## 知识库构建链路

```text
PDF/PPT/PPTX 上传
 -> 保存文件和 CourseMaterial，返回 queued
 -> MaterialTaskQueue 后台解析
 -> MinerU 精准解析，或显式本地解析/OCR 兜底
 -> 章节语义分块
 -> KnowledgeChunk 写入 MySQL
 -> BGE-M3 本地向量化
 -> Milvus 写入课程级 collection
 -> DeepSeek V4 Pro 抽取知识点和关系
 -> Neo4j 写入当前用户当前课程子图
```

材料状态包括 `queued`、`processing`、`mineru_submitted`、`mineru_polling`、`ocr_running`、`chunking`、`indexing`、`parsed`、`index_failed` 和 `failed`。`index_failed` 表示 MySQL chunk 已保留，但向量写入失败；修复 Milvus 后可点击“重建向量索引”或调用 `POST /api/courses/{course_id}/vector-index/rebuild`。

## 关键接口

认证：

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`

课程级画像：

- `POST /api/profile-interviews`，请求体携带 `{ "course_id": <id> }`
- `POST /api/profile-interviews/{id}/messages`
- `POST /api/profile-interviews/{id}/confirm`
- `GET /api/profiles/me?course_id=<id>`

课程和知识库：

- `POST /api/courses/default-python`
- `POST /api/courses/default-c`
- `POST /api/courses/{course_id}/materials`
- `DELETE /api/courses/{course_id}/materials/{material_id}`
- `POST /api/courses/{course_id}/vector-index/rebuild`
- `POST /api/courses/{course_id}/graph/build`
- `POST /api/courses/{course_id}/profile-events`
- `GET /api/courses/{course_id}/profile-events`

学习与资源：

- `POST /api/courses/{course_id}/learning-paths/plan`
- `POST /api/resources/generate`
- `GET /api/resources/openmaic-jobs/{job_id}`
- `PATCH /api/resources/lessons/state`
- `POST /api/assessments/submit`
- `POST /api/tutor/chat`
- `POST /tts/upload`，仅用于可选 VoxCPM2 实验兜底

## 环境变量

复制 `.env.example` 到本地 `.env`，真实密钥只写 `.env`，不要提交仓库。

```text
MOCK_LLM=false
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-v4-pro
TUTOR_VISION_API_KEY=
TUTOR_VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
TUTOR_VISION_MODEL=qwen3.7-plus
DATABASE_URL=mysql+pymysql://root:123456@127.0.0.1:3306/softbei?charset=utf8mb4
JWT_SECRET_KEY=replace-with-a-long-random-secret
UPLOAD_DIR=data/uploads
MAX_UPLOAD_SIZE_MB=100
MILVUS_URI=http://127.0.0.1:19530
OPENMAIC_BASE_URL=http://127.0.0.1:3000
TTS_QWEN_API_KEY=
TTS_QWEN_BASE_URL=
VOXCPM_MODEL_ID=D:/softbei/a3/data/models/voxcpm/VoxCPM2
VOXCPM_CACHE_DIR=D:/softbei/a3/data/models/voxcpm
VOXCPM_LOCAL_FILES_ONLY=true
EMBEDDING_PROVIDER=local_bge
EMBEDDING_MODEL=D:/softbei/a3/data/models/embeddings/BAAI/bge-m3
EMBEDDING_DEVICE=cpu
EMBEDDING_CACHE_DIR=D:/softbei/a3/data/models/embeddings
MINERU_ENABLED=false
MINERU_API_TOKEN=
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=
```

BGE-M3 缓存变量 `HF_HOME` 和 `SENTENCE_TRANSFORMERS_HOME` 已在 `apps/api/app/services/vector_service.py` 中于导入 `sentence_transformers` 前设置。正常通过后端触发向量化时不需要手动配置。

## 测试

```powershell
cd D:\softbei\a3
conda activate a3
python -m pytest apps/api/tests -q

cd D:\softbei\a3\apps\web
npm run build
```

端到端验收应分别测试 `C语言程序设计` 与 `Python程序设计`，确认两门课的画像、知识库、图谱、路径、课堂状态和评估记录互相隔离。

## 设计稿

商业级学习网站视觉方案已生成为 HTML：

- [docs/design/commercial-learning-site-design-options.html](docs/design/commercial-learning-site-design-options.html)

该文件只作为设计稿，不包含功能代码修改，也不需要转为 PDF。
