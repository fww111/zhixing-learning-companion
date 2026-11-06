# zhixing-mcp-servers

把 challengecup 业务层（画像 / 知识图谱 / 评估与路径）以 **MCP Streamable HTTP** 工具暴露给华为云 AgentArts 工作流调用。工具契约、Schema 见 [`docs/agentarts/03-MCP服务接口契约.md`](../../docs/agentarts/03-MCP服务接口契约.md)，官方契约核查见 [`06-技术核查与打磨报告.md`](../../docs/agentarts/06-技术核查与打磨报告.md)。

## 部署形态（重要）

AgentArts 运行时**一个容器只暴露一个端口、只对一个端口探活**。因此云端部署采用**统一单端口入口**：

| 项 | 值 |
| --- | --- |
| 入口 | `mcp_servers.server:app` |
| 端点 | `POST /mcp`（JSON-RPC 2.0）+ `GET /ping`（健康检查） |
| 工具 | 17 个，全部注册在同一个 `FastMCP("zhixing-learning-mcp")`，`stateless_http=True` |
| 端口 | `PORT`（默认 8080），必须与运行时控制台配置一致 |
| 鉴权 | `MCP_AUTH_MODE=platform`（默认，交给运行时网关）；独立部署用 `local` + `MCP_ACCESS_TOKEN` |

旧的 8100 / 8101 / 8102 三进程单镜像方案**不适用于运行时**，三个模块仍保留供本地单独调试（`MCP_SERVER=profile|graph|assessment`）。

| 模块 | 工具数 | 职责 |
| --- | --- | --- |
| `mcp_servers.profile_server` | 8 | 画像持久化、访谈对话记录、画像随学随新事件 |
| `mcp_servers.graph_server` | 4 | 知识图谱约束、原文证据回表、关键词检索兜底 |
| `mcp_servers.assessment_server` | 5 | 综合评估、掌握度、学习路径规划、错题归档 |

## 本地运行

依赖仓库根目录 `.env` 中的 `DATABASE_URL` 与 `NEO4J_*`（与 FastAPI 后端共用一套配置）。

```bash
cd apps/mcp
uv sync
PORT=8080 uv run python -m mcp_servers.server     # http://0.0.0.0:8080/mcp + /ping
```

环境变量：`PORT` / `MCP_PORT`（端口）、`MCP_HOST`（默认 0.0.0.0）、`MCP_SERVER`（all/profile/graph/assessment）、`MCP_AUTH_MODE`（platform/local/none）、`MCP_ACCESS_TOKEN`、`MCP_LOG_LEVEL`。完整示例见仓库根 `.env.example`。

## 测试（不需要云服务器）

```bash
cd apps/mcp
uv run python scripts/protocol_smoke.py   # 真实子进程 + HTTP：/ping、initialize、tools/list、tools/call、跨用户隔离、406
uv run pytest -q                          # 11 个既有单元测试
```

`protocol_smoke.py` 复现官方《制作MCP Server镜像》的 curl 调测，并模拟网关 Host / Origin / `Mcp-Session-Id` / 平台 apikey，当前实测 **6/6 通过**。

## Docker / 云端部署

```bash
# 构建上下文为仓库根目录；AgentArts 要求 ARM64 镜像
docker build --platform linux/arm64 -f apps/mcp/Dockerfile -t zhixing-mcp:latest .
docker run -d --env-file .env -p 8080:8080 zhixing-mcp:latest

# 推送到与 AgentArts 同区域的 SWR（cn-southwest-2 / 西南-贵阳一）
docker tag zhixing-mcp:latest swr.cn-southwest-2.myhuaweicloud.com/<组织>/zhixing-mcp:latest
docker push swr.cn-southwest-2.myhuaweicloud.com/<组织>/zhixing-mcp:latest
```

随后在控制台「智能体运行时」部署，**入栈协议选 MCP**、端口 8080、探活 `/ping`；平台给出公网域名后，在「我的资产 > MCP > 自定义接入」用 Streamable HTTP 登记该域名即可。**运行时由平台托管，不需要自购 ECS。**
