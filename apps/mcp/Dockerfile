# Single-port MCP Server image for the Huawei Cloud AgentArts runtime.
#
# Build context must be the repository root:
#   docker build --platform linux/arm64 -t zhixing-mcp:latest -f apps/mcp/Dockerfile .
#
# AgentArts runtime requirements (highcode-agentarts/agentarts_10_069 + _10_080):
#   - ARM64 image, pushed to an SWR organisation in the SAME region as AgentArts
#     (the service currently runs in cn-southwest-2 / 西南-贵阳一)
#   - Host 0.0.0.0, one port, POST /mcp plus GET /ping
#   - stateless Streamable HTTP, tolerating the gateway's Mcp-Session-Id
#
# Deploy the runtime with 入栈协议 = MCP, then register the runtime access URL
# in "我的资产 > MCP > 自定义接入" (Streamable HTTP).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /build
COPY apps/api /build/apps/api
COPY apps/mcp /build/apps/mcp

WORKDIR /build/apps/mcp
RUN uv sync --frozen --no-dev

ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    MCP_AUTH_MODE=platform

EXPOSE 8080

CMD ["sh", "-c", "exec uv run --no-sync uvicorn mcp_servers.server:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips=*"]
