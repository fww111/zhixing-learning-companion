"""Local MCP protocol smoke test — no cloud server required.

Reproduces the official AgentArts runtime curl checks
(highcode-agentarts/agentarts_10_080 + _10_067) against the real ASGI app in a
real subprocess over HTTP:

  1. GET /ping                      health probe
  2. POST /mcp initialize           handshake, protocolVersion 2025-03-26
  3. POST /mcp tools/list           17 registered tools
  4. POST /mcp tools/call           real tool execution against a temp sqlite DB
  5. missing Accept header          406 as mandated by Streamable HTTP
  6. gateway headers                Host / Origin / Mcp-Session-Id / platform apikey

Run:  cd apps/mcp && uv run python scripts/protocol_smoke.py
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MCP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MCP_ROOT / "src"))
sys.path.insert(0, str(MCP_ROOT.parent / "api"))

_TMP = tempfile.mkdtemp(prefix="zhixing-mcp-smoke-")
_DB = (Path(_TMP) / "smoke.db").as_posix()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["MOCK_LLM"] = "true"
os.environ["MCP_AUTH_MODE"] = "platform"
os.environ.setdefault("MCP_ACCESS_TOKEN", "")

# Seed one course so get_student_profile passes the ownership check.
from app.db import SessionLocal, init_db  # noqa: E402
from app.models.course import Course  # noqa: E402
from app.models.user import User  # noqa: E402

init_db()
with SessionLocal() as session:
    session.add(User(id=1, username="smoke", email="smoke@example.com", password_hash="x"))
    session.commit()
with SessionLocal() as session:
    session.add(Course(id=1, user_id=1, name="C++算法学习", status="active"))
    session.commit()

import httpx  # noqa: E402


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


PORT = free_port()
BASE = f"http://127.0.0.1:{PORT}"
GW_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "Host": "zhixing.agentarts.example.com",
    "Origin": "https://console.huaweicloud.com",
    "Mcp-Session-Id": "smoke-session-0001",
    "X-Hw-Agentarts-Session-Id": "smoke-session-0001",
    "Authorization": "Bearer platform-api-key",
}

env = os.environ.copy()
env["PYTHONPATH"] = str(MCP_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
env["PORT"] = str(PORT)
env["MCP_HOST"] = "127.0.0.1"

proc = subprocess.Popen(
    [sys.executable, "-m", "mcp_servers.server"],
    cwd=MCP_ROOT,
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    encoding="utf-8",
    errors="replace",
)


def wait_ready(timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            if httpx.get(f"{BASE}/ping", timeout=1.0).status_code == 200:
                return True
        except Exception:
            time.sleep(0.2)
    return False


def rpc(payload: dict, headers: dict | None = None):
    resp = httpx.post(f"{BASE}/mcp", json=payload, headers=headers or GW_HEADERS, timeout=15.0)
    return resp


def parse_body(resp: httpx.Response):
    """Streamable HTTP may return plain JSON or an SSE ``data:`` frame."""
    text = resp.text.strip()
    for line in text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    return json.loads(text) if text else {}


RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str) -> None:
    RESULTS.append((name, bool(passed), detail))
    print(f"[{'PASS' if passed else 'FAIL'}] {name}: {detail}")


try:
    ready = wait_ready()
    if not ready:
        out = ""
        if proc.stdout:
            proc.terminate()
            out = proc.stdout.read()[-2000:]
        print("server failed to start:\n" + out)
        sys.exit(1)

    # 1. health probe must be public (the gateway calls it without credentials)
    r = httpx.get(f"{BASE}/ping", headers={"Host": "zhixing.agentarts.example.com"}, timeout=5.0)
    check("GET /ping", r.status_code == 200 and r.json().get("status") == "ok", f"HTTP {r.status_code} {r.text[:120]}")

    # 2. initialize, with gateway-style Host/Origin/session headers
    r = rpc({
        "jsonrpc": "2.0", "id": 0, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                   "clientInfo": {"name": "agentarts-smoke", "version": "1.0.0"}},
    })
    body = parse_body(r) if r.status_code == 200 else {}
    check("initialize / gateway headers", r.status_code == 200 and "result" in body,
          f"HTTP {r.status_code} protocolVersion={body.get('result', {}).get('protocolVersion')}")

    # 3. tools/list
    r = rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    body = parse_body(r) if r.status_code == 200 else {}
    tools = body.get("result", {}).get("tools", [])
    check("tools/list = 17", r.status_code == 200 and len(tools) == 17,
          f"HTTP {r.status_code} count={len(tools)} names={','.join(t['name'] for t in tools[:4])}...")

    # 4. real tool call (DB-backed, ownership check passes)
    r = rpc({
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "get_student_profile", "arguments": {"user_id": 1, "course_id": 1}},
    })
    body = parse_body(r) if r.status_code == 200 else {}
    content = body.get("result", {}).get("content", [])
    text = content[0].get("text", "") if content else ""
    check("tools/call get_student_profile", r.status_code == 200 and '"ok": true' in text.replace("'", '"'),
          f"HTTP {r.status_code} {text[:160]}")

    # 4b. cross-user isolation: user 2 must not read user 1's course
    r = rpc({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "get_student_profile", "arguments": {"user_id": 2, "course_id": 1}},
    })
    body = parse_body(r) if r.status_code == 200 else {}
    content = body.get("result", {}).get("content", [])
    text = content[0].get("text", "") if content else ""
    check("cross-user isolation", "course_not_found" in text, text[:160])

    # 5. Streamable HTTP requires both media types in Accept
    bad = dict(GW_HEADERS)
    bad["Accept"] = "application/json"
    r = rpc({"jsonrpc": "2.0", "id": 4, "method": "tools/list"}, headers=bad)
    check("Accept rule (406)", r.status_code == 406, f"HTTP {r.status_code}")

finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()

failed = [name for name, ok_, _ in RESULTS if not ok_]
print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
if failed:
    print("failed: " + ", ".join(failed))
sys.exit(1 if failed else 0)
