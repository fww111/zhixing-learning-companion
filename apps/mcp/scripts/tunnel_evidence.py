import json, httpx
def parse(resp):
    if "text/event-stream" in resp.headers.get("content-type", ""):
        for line in resp.text.splitlines():
            if line.startswith("data:"): return json.loads(line[5:].strip())
    return json.loads(resp.text)
base = "https://elementary-county-vendors-acquire.trycloudflare.com"
def call(i, name, args):
    r = httpx.post(f"{base}/mcp", headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream"},
        timeout=45, json={"jsonrpc":"2.0","id":i,"method":"tools/call","params":{"name":name,"arguments":args}})
    return json.loads(parse(r)["result"]["content"][0]["text"])

ev = call(1, "get_knowledge_evidence", {"user_id":3,"course_id":3,"node_id":"outline-chapter-1","limit":3})
print("ok=", ev["ok"], "node_name=", ev.get("node_name"), "evidence_count=", len(ev.get("evidence",[])))
for c in ev.get("evidence",[])[:2]:
    print("  chunk", c["chunk_id"], c["heading"], "|", c["content"][:45])
print("PUBLIC TUNNEL EVIDENCE OK" if ev["ok"] else "FAILED")