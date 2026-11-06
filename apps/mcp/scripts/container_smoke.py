import json
import os
import httpx

URL = os.getenv("MCP_SMOKE_URL", "http://127.0.0.1:8080/mcp")
H = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


def parse(resp):
    if "text/event-stream" in resp.headers.get("content-type", ""):
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
    return json.loads(resp.text)


def call(i, name, args=None):
    params = {"name": name}
    if args is not None:
        params["arguments"] = args
    r = httpx.post(URL, headers=H, timeout=30, json={
        "jsonrpc": "2.0", "id": i, "method": "tools/call", "params": params})
    out = parse(r)
    return json.loads(out["result"]["content"][0]["text"])


got1 = call(1, "get_student_profile", {"user_id": 1, "course_id": 1})
print("get#1:", got1["ok"], "exists=", got1["exists"])
saved = call(2, "save_student_profile", {
    "user_id": 1, "course_id": 1,
    "profile": {"major": "计算机科学与技术", "grade": "大二",
                "learning_goal": "4周掌握Python基础",
                "time_preference": "每天晚间45分钟"}})
print("save:", saved["ok"], "created=", saved["created"], "completion=", saved["completion_score"])
got2 = call(3, "get_student_profile", {"user_id": 1, "course_id": 1})
assert got2["exists"] and got2["profile"]["grade"] == "大二"
print("get#2: exists=True, student_id=", got2["student_id"])
print("CONTAINER TOOL CALLS PASSED")