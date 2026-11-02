# 知行学习伙伴 · Zhixing Learning Companion

> 面向高等教育的个性化学习多智能体系统 —— 华为 ICT 大赛赛题二（基于华为云 AgentArts 智能体开发平台的 Agent 设计和应用）参赛作品。
>
> 以《C++算法学习》为演示课程，通过多智能体协作把"教材语料 + 知识图谱 + 学生画像"变成会看、会说、会因材施教的 AI 学习伙伴。

## 作品简介

学生面对海量课程资料难以筛选、集体授课难以因材施教，而直接使用通用大模型答疑又存在幻觉风险。**知行学习伙伴**用多智能体协作解决这三个痛点：

1. **对话式学习画像**：14 维学生画像（专业/目标/基础/薄弱点/时间约束等）通过自然语言访谈构建，随学随新；
2. **证据约束的资源生成**：讲解文档、思维导图、视频脚本、代码实验、练习题、拓展阅读 6 类资源由独立 Agent 并行生成，全部**可回溯到教材原文**，经事实校验、教学适配、双模型辩论交叉验证后才交付；
3. **动态学习路径**：知识点掌握度驱动，未达标自动插入薄弱点专项补救任务；
4. **智能辅导**：结合课程知识库与知识图谱约束的多轮答疑，支持追问选项与语音/图片输入；
5. **学习状态感知**（创新点）：MediaPipe 在浏览器本地分析摄像头画面（专注/困惑/走神/疲劳），AI 感知学生卡住时**主动介入换一种讲法**——画面永不上传，只上报状态指标；
6. **学习评估与错题闭环**：多维评估写入掌握度与画像，错题按章节归档、重做回写。

演示课程《C++算法学习》含 8 章 33 节自建教材语料（每节含可编译 C++17 示例，33/33 通过 g++ 校验）与知识图谱种子。

## 系统架构

```text
学生（React 前端 / AgentArts 网页发布）
        │
        ▼
华为云 AgentArts 多智能体应用（平台侧编排：意图路由 → 画像访谈 / 资源生成 / 辅导 / 路径评估）
        │  平台知识库（教材语料语义检索）   │  MaaS：DeepSeek-V4 系 + GLM-5（校验/辩论双模型）
        │  MCP 调用                        │  效果评估（正确性/幻觉评估器）
        ▼
本仓库业务层（MCP Server 三件套，streamableHttp）
 ├─ profile-server     画像持久化 / 访谈记录 / 画像随学随新事件
 ├─ graph-server       Neo4j 知识图谱约束导出 / MySQL 原文证据回表（防幻觉的最终证据源）
 └─ assessment-server  综合评估 / 掌握度 / 学习路径规划 / 错题归档
        │
        ▼
FastAPI 业务 API（JWT 鉴权、材料解析、学习事件） + MySQL + Neo4j + OpenMAIC 标准课堂
```

- **平台侧**（AgentArts 工作流/知识库/评估/发布）承载智能体编排，搭建蓝图见 [docs/agentarts/02](docs/agentarts/02-AgentArts工作流搭建蓝图.md)；
- **本仓库**承载平台不具备的业务深度：知识图谱约束、掌握度驱动重规划、课程级多用户数据隔离；
- 两侧通过 **MCP（streamableHttp）** 连接，工具契约见 [docs/agentarts/03](docs/agentarts/03-MCP服务接口契约.md)。

## 核心技术

| 层 | 选型 |
| --- | --- |
| 前端 | React 19 + Vite + TypeScript + React Router |
| 智能体编排 | 华为云 AgentArts 低代码工作流（并行聚合 + 反思精炼循环 + 双模型辩论） |
| 业务服务 | FastAPI + SQLAlchemy（JWT 鉴权） |
| MCP | 官方 Python SDK，三个业务 Server（apps/mcp，uv 管理） |
| 数据 | MySQL（业务/原文 chunk）+ Neo4j（课程知识图谱，user_id + course_id 隔离） |
| 检索 | AgentArts 平台知识库语义检索 + 本地分块预设（general/qa/book）+ 检索质量评估闭环（recall/f1@k、坏例分析） |
| 课堂 | OpenMAIC 多智能体互动课堂（3D 可视化/仿真/在线编程） |
| 学习状态感知 | MediaPipe FaceLandmarker 纯浏览器推理（任何视频帧不出本机） |
| 大模型 | 华为云 MaaS DeepSeek-V4 系（主推理）+ GLM-5（校验/辩论）；本地开发可配任意 OpenAI 兼容端点 |

## 快速开始

### 0. 环境要求

- Python ≥ 3.11 与 [uv](https://docs.astral.sh/uv/)
- Node.js ≥ 18
- （可选）本地 MySQL 与 Neo4j：未配置时后端可用 SQLite 跑通画像与事件链路

复制 `.env.example` 为仓库根目录 `.env`，按需填写 `DATABASE_URL`、`NEO4J_*`、`LLM_API_KEY` 等；密钥只放本地 `.env`，不提交仓库。

### 1. 后端（FastAPI，端口 8000）

```bash
cd apps/api
uv venv && uv pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

### 2. 前端（Vite dev，端口 5173）

```bash
cd apps/web
npm install
npm run dev        # predev 会自动把 MediaPipe wasm 从 node_modules 拷到 public
```

访问 http://localhost:5173 。若本机 8000 端口被占用，可用 `VITE_API_TARGET=http://127.0.0.1:8010 npm run dev` 配合 `uvicorn --port 8010`。

### 3. 灌入《C++算法学习》演示课程（可选）

```bash
cd apps/mcp
uv sync
uv run python scripts/seed_cpp_course.py --dry-run   # 校验语料与图谱对齐
uv run python scripts/seed_cpp_course.py             # 写入 MySQL + Neo4j（需 .env 提供 DATABASE_URL/NEO4J_*）
```

### 4. 启动 MCP Server 三件套（供 AgentArts 工作流调用）

```bash
cd apps/mcp
uv run python -m mcp_servers.profile_server      # http://0.0.0.0:8100/mcp
uv run python -m mcp_servers.graph_server        # http://0.0.0.0:8101/mcp
uv run python -m mcp_servers.assessment_server   # http://0.0.0.0:8102/mcp
```

Docker 一键部署见 [apps/mcp/README.md](apps/mcp/README.md)。

### 5. 体验学习状态感知

登录后进入任一知识点学习页，开启左下角「学习状态感知」并允许摄像头（或任意页面使用全局悬浮窗）。困惑持续 15 秒会触发**主动介入横幅**，一键让辅导 AI 结合课程证据换一种讲法。整个过程只有 JSON 状态指标出本机，可用浏览器 DevTools 网络面板核验。

## 测试

```bash
cd apps/api && pytest tests -q                       # 后端（含分块预设、KB 检索评估闭环）
cd apps/web && npm run test:models && npm run build  # 前端模型单测 + tsc 构建
cd apps/mcp && uv run pytest -q                      # MCP Server 冒烟
```

## 目录结构

```text
apps/api        FastAPI 后端（画像/材料解析/知识图谱/路径/评估/辅导/KB 检索评估）
apps/web        React 前端（学习工作台、全局辅导窗、学习状态感知悬浮、Agent 协作轨迹）
apps/mcp        MCP Server 三件套 + 课程种子/语料校验/提示词实测脚本
data/seed       《C++算法学习》教材语料与知识图谱种子
docs/agentarts  参赛设计方案：场景与架构 / 平台搭建蓝图 / MCP 契约 / 提示词资产包 / 技术借鉴
docs            技术方案、部署、测试、PRD、设计稿
OpenMAIC-main   OpenMAIC 标准课堂（开源，见下方致谢）
```

## AgentArts 参赛设计文档

| 文档 | 内容 |
| --- | --- |
| [01 场景定义与 Agent 架构](docs/agentarts/01-场景定义与Agent架构.md) | 场景识别、多 Agent 分工、模型与资产选择、创新点 |
| [02 工作流搭建蓝图](docs/agentarts/02-AgentArts工作流搭建蓝图.md) | 平台侧节点级搭建说明（知识库/画像/资源生成/发布/评估） |
| [03 MCP 服务接口契约](docs/agentarts/03-MCP服务接口契约.md) | 17 个 MCP 工具的参数、返回、错误约定、Schema |
| [04 提示词资产包](docs/agentarts/04-提示词资产包.md) | 工作流各节点可直接粘贴的提示词与模型档位路由实测结论 |
| [05 技术借鉴与增强](docs/agentarts/05-技术借鉴与增强.md) | 分块预设体系与检索评估闭环的设计来源 |

## 开源与 AI 辅助说明

- [OpenMAIC](https://github.com/THU-MAIC/OpenMAIC)（AGPL-3.0）作为标准课堂组件集成，来源与使用方式如目录所示；
- 分块预设体系与知识库检索自动评估借鉴自开源项目"伯乐 Bole"（AI-Interview），移植与裁剪说明见 [docs/agentarts/05](docs/agentarts/05-技术借鉴与增强.md)；
- 本项目开发过程使用了 AI Coding 工具辅助，范围与协作方式见 [docs/ai-coding-tools.md](docs/ai-coding-tools.md)。
