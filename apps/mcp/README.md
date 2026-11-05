# zhixing-mcp-servers

把 challengecup 业务层（画像 / 知识图谱 / 评估与路径）以 **MCP streamableHttp** 工具暴露给华为云 AgentArts 工作流调用的三个服务。工具契约、Schema 与部署说明见 [`docs/agentarts/03-MCP服务接口契约.md`](../../docs/agentarts/03-MCP服务接口契约.md)。

| Server | 模块 | 默认端口 | 职责 |
| --- | --- | --- | --- |
| profile-server | `mcp_servers.profile_server` | 8100 | 画像持久化、访谈对话记录、画像随学随新事件 |
| graph-server | `mcp_servers.graph_server` | 8101 | 知识图谱约束、原文证据回表、关键词检索兜底 |
| assessment-server | `mcp_servers.assessment_server` | 8102 | 综合评估、掌握度、学习路径规划、错题归档 |

## 本地运行

依赖仓库根目录 `.env` 中的 `DATABASE_URL` 与 `NEO4J_*`（与 FastAPI 后端共用一套配置）：

```bash
cd apps/mcp
uv sync
uv run python -m mcp_servers.profile_server      # http://0.0.0.0:8100/mcp
uv run python -m mcp_servers.graph_server        # http://0.0.0.0:8101/mcp
uv run python -m mcp_servers.assessment_server   # http://0.0.0.0:8102/mcp
```

环境变量：`MCP_HOST`（默认 0.0.0.0）、`MCP_PORT`（覆盖默认端口）、`MCP_ACCESS_TOKEN`（设置后要求 `Authorization: Bearer <token>`）、`MCP_AUTO_INIT_DB`（设为 true 时启动前自动建表）。

本机 MySQL 未启动时，可用 sqlite 先联调 profile-server（graph-server 仍必须 Neo4j）：

```bash
cd apps/mcp
DATABASE_URL=sqlite:///./data/mcp_local.db MCP_AUTO_INIT_DB=true \
  uv run python -m mcp_servers.profile_server
# HTTP 端到端冒烟脚本（initialize + get/save 工具调用）：
uv run python scripts/smoke_http.py
```

## 测试

```bash
cd apps/mcp
uv run pytest -q
```

测试使用独立 sqlite 数据库，不依赖本地 MySQL/Neo4j；知识图谱用例通过 monkeypatch 注入图谱夹具。

## Docker

```bash
docker build -t zhixing-mcp-servers -f apps/mcp/Dockerfile .
docker run -d --env-file .env -p 8100:8100 -p 8101:8101 -p 8102:8102 zhixing-mcp-servers
```

或在仓库根目录使用 compose（变量与数据库布局见 `docs/agentarts/06-MCP 配置手册.md`）：

```bash
docker compose up -d mcp
```

构建上下文为仓库根目录。镜像同时暴露三个 `/mcp` 端点，可在 AgentArts「MCP → 自定义接入」逐一登记调试。
