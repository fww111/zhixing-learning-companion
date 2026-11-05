import json, httpx
URL = "http://127.0.0.1:8101/mcp"
H = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
def parse(resp):
    if "text/event-stream" in resp.headers.get("content-type", ""):
        for line in resp.text.splitlines():
            if line.startswith("data:"): return json.loads(line[5:].strip())
    return json.loads(resp.text)
def call(i, name, args):
    r = httpx.post(URL, headers=H, timeout=30, json={"jsonrpc":"2.0","id":i,"method":"tools/call",
        "params":{"name":name,"arguments":args}})
    return json.loads(parse(r)["result"]["content"][0]["text"])

g = call(1, "get_course_graph", {"user_id":3,"course_id":3})
print("graph ok=", g["ok"], "nodes=", len(g.get("nodes",[])), "edges=", len(g.get("edges",[])))
node = g["nodes"][1]
nid = str(node["id"])
print("sample node:", nid, node["name"])
ev = call(2, "get_knowledge_evidence", {"user_id":3,"course_id":3,"node_id":nid,"limit":3})
print("evidence ok=", ev["ok"], "node_name=", ev.get("node_name"), "count=", len(ev.get("evidence",[])))
for c in ev.get("evidence", [])[:3]:
    print("  chunk", c["chunk_id"], c["heading"], "|", c["content"][:45])