import json
import sys
from pathlib import Path
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))

URL = "http://127.0.0.1:8100/mcp"
HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


def parse(resp):
    text = resp.text
    if "text/event-stream" in resp.headers.get("content-type", ""):
        for line in text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
    return json.loads(text)


def call(rpc_id, method, params=None):
    payload = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
    if params is not None:
        payload["params"] = params
    r = httpx.post(URL, headers=HEADERS, json=payload, timeout=30)
    print(f"-- {method} -> HTTP {r.status_code}")
    return parse(r)


# 1. initialize
init = call(1, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                              "clientInfo": {"name": "smoke", "version": "1.0"}})
print("server:", init["result"]["serverInfo"])

# 2. seed user + course directly through the API models
from app.db import SessionLocal
from app.models.user import User
from app.models.course import Course

with SessionLocal() as db:
    user = db.query(User).filter_by(username="smoke_user").first()
    if user is None:
        user = User(username="smoke_user", email="smoke@example.com", password_hash="x")
        db.add(user)
        db.flush()
    course = db.query(Course).filter_by(user_id=user.id, name="Python程序设计").first()
    if course is None:
        course = Course(user_id=user.id, name="Python程序设计", major="计算机",
                        level="本科", status="ready")
        db.add(course)
        db.flush()
    db.commit()
    uid, cid = user.id, course.id

# 3. get -> not exists
got = call(2, "tools/call", {"name": "get_student_profile",
                             "arguments": {"user_id": uid, "course_id": cid}})
print("get#1:", got["result"]["content"][0]["text"][:120])

# 4. save profile
saved = call(3, "tools/call", {"name": "save_student_profile", "arguments": {
    "user_id": uid, "course_id": cid,
    "profile": {"major": "计算机科学与技术", "grade": "大二",
                "learning_goal": "4周内掌握Python基础",
                "time_preference": "每天晚间45分钟"}}})
print("save:", saved["result"]["content"][0]["text"][:160])

# 5. get again -> exists
got2 = call(4, "tools/call", {"name": "get_student_profile",
                              "arguments": {"user_id": uid, "course_id": cid}})
data = json.loads(got2["result"]["content"][0]["text"])
assert data["ok"] is True and data["exists"] is True and data["profile"]["grade"] == "大二"
print("get#2 OK: exists=True, student_id=", data["student_id"])
print("SMOKE PASSED")