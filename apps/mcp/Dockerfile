# 三个 MCP Server 单镜像部署（供 AgentArts 运行时 / 华为云 ECS 使用）
# 构建上下文必须是仓库根目录：
#   docker build -t zhixing-mcp-servers -f apps/mcp/Dockerfile .
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /build
COPY apps/api /build/apps/api
COPY apps/mcp /build/apps/mcp

WORKDIR /build/apps/mcp
RUN uv sync --frozen --no-dev

ENV PYTHONUNBUFFERED=1
EXPOSE 8100 8101 8102

CMD ["sh", "-c", "\
  uv run --no-sync python -m mcp_servers.profile_server & \
  uv run --no-sync python -m mcp_servers.graph_server & \
  uv run --no-sync python -m mcp_servers.assessment_server & \
  wait"]
