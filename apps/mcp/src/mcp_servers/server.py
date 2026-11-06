"""Unified single-port MCP entrypoint for AgentArts runtime deployment.

The AgentArts runtime exposes exactly one port per container and probes
``GET /ping`` on that port. Running three separate servers in one image (the
earlier 8100/8101/8102 design) cannot work behind that gateway. This module
registers all 17 business tools on a single FastMCP instance.

``MCP_SERVER`` selects the exposed tool set:
  * ``all`` (default)  - profile + graph + assessment, one endpoint
  * ``profile`` / ``graph`` / ``assessment`` - one subset (local debugging)

Export ``app`` so uvicorn can load ``mcp_servers.server:app`` directly.
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from mcp_servers import assessment_server, graph_server, profile_server, runtime

_MODULES = (profile_server, graph_server, assessment_server)


def build_unified_server() -> FastMCP:
    mcp = FastMCP(
        "zhixing-learning-mcp",
        stateless_http=True,
        streamable_http_path="/mcp",
        transport_security=runtime.AGENTARTS_TRANSPORT_SECURITY,
    )
    for module in _MODULES:
        for name, impl in module.TOOL_IMPLS.items():
            mcp.tool(name=name)(impl)
    return mcp


def resolve_server() -> FastMCP:
    which = os.getenv("MCP_SERVER", "all").strip().lower()
    if which == "all":
        return build_unified_server()
    lookup = {
        "profile": profile_server.mcp,
        "graph": graph_server.mcp,
        "assessment": assessment_server.mcp,
    }
    if which not in lookup:
        raise ValueError(f"unknown MCP_SERVER={which!r}; expected all/profile/graph/assessment")
    return lookup[which]


mcp = resolve_server()
app = runtime.build_asgi_app(mcp)


if __name__ == "__main__":
    runtime.run_server(mcp, default_port=8080)
